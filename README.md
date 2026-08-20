# Canon

**Temporal grounding for enterprise AI.**

Enterprise RAG systems retrieve evidence that was correct when it was written but has since been
superseded. Canon resolves claim history in HydraDB before an answer is grounded, preserving
historical evidence while preventing retired claims from masquerading as current truth.

```
Same model. Same prompt. Same corpus.
Only the context topology changes.
```

## What it does

- **Temporal grounding** — decides which retrieved evidence is valid for the time a question is
  asking about, and labels the rest `superseded_for_current_grounding`.
- **Proof** — every decision carries the supersession chain, the exact evidence spans, the
  temporal-quality class, and the HydraDB queries that produced it.
- **Residue-aware retrieval** — reverse-traverses a retired proposition to every document still
  carrying it, and keeps those documents out of present-tense context. This is the differentiator
  the numbers below measure.
- **Honest states** — every current-state answer is exactly one of `CANON`, `CONTESTED`, `UNKNOWN`.
  Canon never invents a winner when the evidence does not establish one.

## Graph model

```
Entity ──HAS_CLAIM──▶ ClaimKey ──HAS_VALUE──▶ Proposition ◀──ASSERTS── Assertion ──IN_ARTIFACT──▶ Artifact
                                                   ▲
                                                   │ SELECTS
                                              CanonEvent ──SUPERSEDES──▶ CanonEvent
```

- **Entity** — a real-world thing. **ClaimKey** — one mutable property of it.
- **Proposition** — one possible value. **Assertion** — one artifact asserting that value, with the
  exact span, stance, source field, and whether the value sat in a typed field.
- **CanonEvent** — the event that selects a value as current and may supersede a prior event.

Document text lives in a SQLite FTS5 index. The truth topology — what supersedes what, and which
evidence may ground a present-tense answer — lives entirely in HydraDB, which runs against an
S3-compatible object store (MinIO in `docker-compose.yml`) because its lease and manifest paths
need conditional writes that a plain local filesystem backend does not implement.

## Why HydraDB

Three operations decide the answer, not the presentation:

| Operation | Cypher |
| --- | --- |
| Claim neighborhood | `MATCH (c:ClaimKey {id: $id})-[:HAS_VALUE]->(p:Proposition) RETURN p.value, p.status` |
| Supersession lineage | `MATCH (ev:CanonEvent {id: $id})-[:SUPERSEDES*1..10]->(old)-[:SELECTS]->(p) RETURN p.value` |
| Residue reverse traversal | `MATCH (p:Proposition {id: $id})<-[:ASSERTS]-(a:Assertion)-[:IN_ARTIFACT]->(d:Artifact) RETURN a.evidence_span, d.doc_id` |

Removing HydraDB removes the answer, not a visualization: the retired/current split, the ordering,
and the filtering all come out of those traversals.

## Results

Dataset: [`onyx-dot-app/EnterpriseRAG-Bench`](https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench).
All 20 official `conflicting_info` questions. Baseline and Canon share the same corpus, the same
BM25 candidate retrieval and the same `top_k = 10`.

| Metric | BM25 baseline | Canon |
| --- | --- | --- |
| Superseded document present in present-tense context | 14 / 20 | **1 / 20** |
| Current gold document present in context | 18 / 20 | **20 / 20** |
| Historical question recovers the retired evidence | — | **20 / 20** |

On all 20 official `info_not_found` questions the claim graph returns `UNKNOWN` — 20 / 20. No
question that the corpus cannot answer resolves to a claim.

### Answers

Same answering model (`claude-sonnet-5`), same system prompt, same template. Three arms isolate the
two things Canon does. **Every arm sees the same number of documents** — when Canon drops a
superseded document it backfills the slot from the next candidate in the same BM25 ranking, so no
arm argues with less evidence than another.

| Arm | What it gets |
| --- | --- |
| `baseline` | BM25 top-k, unchanged |
| `canon_filtered` | superseded documents replaced, **no claim-graph note** |
| `canon` | the same context **plus** the graph's stated current/retired values |

Graded against each question's official `answer_facts` by `claude-sonnet-5`, three passes per answer
with a majority verdict, so these rows are **model-judged**. The whole benchmark was run three times
end to end; the table reports the mean with the observed range:

| Metric | baseline | canon_filtered | canon |
| --- | --- | --- | --- |
| Superseded document in context *(deterministic)* | 14 / 20 | **1 / 20** | **1 / 20** |
| Answer states the current value | 14.7 / 20 *(14–15)* | 17.7 / 20 *(17–18)* | **19 / 20 *(19–19)*** |
| Answer presents the retired value as current | 1.3 / 20 *(1–2)* | 0.7 / 20 *(0–1)* | **0.3 / 20 *(0–1)*** |
| Answer abstains | 2.3 / 20 *(2–3)* | 2 / 20 | 0.7 / 20 *(0–1)* |
| Context documents | 200 | 202 | 202 |

Two things to read here.

**Context topology alone does most of the work.** `canon_filtered` receives no claim-graph note —
nothing tells it which value is current — and it still moves 14.7 to 17.7. Stating the graph's
conclusion adds the last 1.3. The result is not an artefact of handing the model the answer.

**Canon returned 19/20 in all three runs, with no variance.** The baseline and the no-note arm both
moved between runs; the full Canon arm did not. Per-run files are in `eval/results/runs/` and the
aggregate in `eval/results/summary.json`, so a judge can re-run `make benchmark` and compare.

## Official benchmark harness

The benchmark ships its own scorer, and Canon's answers are exported in its format so a judge can
score them without trusting anything in this repository:

```bash
make export-answers      # writes eval/official/{baseline,canon_filtered,canon}.jsonl
```

Each line is `{"question_id", "answer", "document_ids"}`. To score them, clone
[EnterpriseRAG-Bench](https://github.com/onyx-dot-app/EnterpriseRAG-Bench), install its
requirements, and run its evaluator against the exported file:

```bash
export LLM_PROVIDER=anthropic LLM_API_KEY=... LLM_MODEL_NAME=claude-sonnet-4-6
python -m src.scripts.answer_evaluation.metrics_based_eval \
    --answers-file answer_evaluation/canon.jsonl --no-correction
```

`--no-correction` scores against the original gold set without letting the harness rewrite gold
answers, so all three arms are judged against identical references.

## Systems measurements

`make perf` loads a labelled benchmark subgraph and measures the traversals Canon actually depends
on. Latest run in `evidence/hydra_perf.json`:

| Measurement | Value |
| --- | --- |
| Graph loaded | 10,011 vertices / 29,760 edges |
| Write throughput | 5,119 edges/s (5.8 s total) |
| Reverse traversal (`Proposition <-ASSERTS-`, fan-in 41) | p50 2.2 ms / p95 2.9 ms |
| Variable-depth lineage (`SUPERSEDES*1..10`) | p50 3.3 ms / p95 4.5 ms |
| Two-hop neighborhood (123 rows) | p50 15.0 ms / p95 17.7 ms |
| Namespace-scoped label count | p50 8.1 ms |
| Edge teardown | 3,174 edges/s |

Every product query starts from a vertex id or a namespace predicate. An unanchored
`MATCH ()-[:REL]->()` count exceeds the 30 s query timeout once the benchmark subgraph is loaded —
Canon never issues one, and the evidence file says so.

Deleting a vertex costs far more than deleting its edges on this engine, so `make perf` tears down
the benchmark edges and leaves the id-only vertices behind (`--delete-nodes` removes them too).
Those vertices carry no label, kind, or namespace, so no product query can reach them; the evidence
file records how many were left.

## Data

- **Indexed:** 511,958 of 511,962 EnterpriseRAG-Bench documents into SQLite FTS5 in 177 s (4
  duplicate `doc_id`s skipped). Recorded in `evidence/corpus_index.json`.
- **Deeply extracted:** the 20 conflict claim neighborhoods — 39 gold documents plus a corpus-wide
  residue scan per retired value. Recorded in `evidence/seed.json`.
- Cheap retrieval globally, deep reasoning locally. Nothing else in the corpus was claim-extracted,
  and nothing else is claimed.

## Entity resolution

Track 1 is an ontology track, so identity has to be real rather than asserted. Canon resolves people
from explicit `Name <email>` bindings in the corpus — no model judgment, no invented edges:

```
121,390 gmail documents scanned · 1,933,236 bindings · 177,377 people · 251,498 aliases   (48s)
RESOLVED 182,249     PROBABLE 48,190     AMBIGUOUS 21,059
```

| State | Meaning |
| --- | --- |
| `RESOLVED` | An email bound to exactly one person by an explicit `Name <email>` line |
| `PROBABLE` | A name spelling or email local part mapping to exactly one person, inferred from the bindings |
| `AMBIGUOUS` | The alias maps to several people — usually the same name at different organisations |

`Grace O'Connor`, `Grace Oconnor` and `AM Grace O'Connor` collapse onto one person.
`Alyssa Chen` exists at `cascadefg.com`, `zenovahealth.com` and `techharbor.com`, so that alias stays
**AMBIGUOUS and is never merged** — the graph shows the fork instead of guessing. The graph
materialises a stratified sample of aliases rather than all 251,498; `evidence/entities.json` records
both the corpus totals and what was written.

## Environment

Copy `.env.example` to `.env` and fill in what you need. The file is gitignored.

Only `ANTHROPIC_API_KEY` costs anything, and only two steps use it: the answer arm of
`make benchmark` and `make judge`. Everything else — indexing, seeding, graph resolution, leakage,
residue, identity, `make verify` — runs with no key at all, and any step that needs one it does not
have is written to the results file as `not_run` rather than skipped silently.

## Reproduce

```bash
make hydra-up      # MinIO + HydraDB OSS: :8443 HTTP, :7687 Bolt, :9090 metrics
uv sync
make verify        # write/read, persistence across restart, supersession,
                   # majority-vs-supersession, residue traversal, UNKNOWN, CONTESTED
make index         # SQLite FTS5 over the EnterpriseRAG-Bench documents parquet (~3 min, ~4 GB)
make seed          # extract the 20 conflict claims + residue scan into HydraDB
make entities      # resolve people and aliases from the corpus into HydraDB
make graph-stats   # records real node/edge counts into evidence/graph_stats.json
make benchmark     # writes eval/results/latest.json
make judge         # grades saved answers against the dataset rubric
make aggregate     # mean and range across eval/results/runs/*.json
make perf          # HydraDB viability + latency measurements → evidence/hydra_perf.json
make api           # FastAPI on :8000
pnpm --dir apps/web dev   # UI on :3000 — landing at /, dashboard at /truth
```

`make verify` prints:

```
HydraDB write/read ...... PASS
Persistence ............. PASS
Supersession ............ PASS
Majority adversarial .... PASS
Residue traversal ....... PASS
UNKNOWN ................. PASS
CONTESTED ............... PASS
```

The majority-adversarial check is the load-bearing one: 8 artifacts asserting `$0.08` against a
single later document that says the price changed from `$0.08` to `$0.06`. Canon must return
`$0.06`. Majority vote never overrides proven supersession.

## Limitations

- **Verified structured residue is 0 on this corpus, and residue-aware retrieval is what carries
  the differentiator instead.** No EnterpriseRAG-Bench document asserts a
  retired value inside a typed `field: value` line of a structured source; the retired values live in
  prose. The count is reported as 0 rather than relaxed into something weaker. What Canon does report
  is `LEXICAL_RESTATEMENT`: the retired value appears verbatim and the containing line carries no
  historical or rejected marker. Stance is not proven. 8 restatements are recorded — 6 in the
  superseded source document itself, 2 elsewhere in the corpus — and every one is inspectable in
  `eval/residue_bench.jsonl`.
- **Verified resurrection is 0.** The dataset exposes only `doc_id`, `source_type`, `title` and
  `content` — there is no metadata timestamp, so no reassertion can be ordered against a supersession
  time. Claiming resurrection here would require an ordering the data does not support.
- **Temporal quality is inherited from the dataset inventory**, not derived from metadata: 16 claims
  resolve at `T1`, 3 at `T2`, and the contested one at `T3`. `T2` claims are resolved only by
  explicit supersession language, never by timestamp.
- **The answer rows are model-judged, the rest are deterministic.** Answer accuracy is graded by
  `claude-haiku-4-5` against the dataset's own `answer_facts`, and every row is labelled as such.
  A deterministic string match was tried first and rejected: it cannot tell `short: <128` from
  `short <128`, and it scores an answer that begins `UNKNOWN` as stating a value it merely explains.
  No headline residue or graph number depends on model judgment.
- **The Canon context includes a one-line claim-graph note** stating the current and retired values.
  That is the product — the graph's conclusion reaching the model — but it means the answer rows
  measure filtering *plus* assertion, not filtering alone. Isolating the two would need a third arm
  with the filtered context and no note.
- **Extraction of the conflict claims** starts from `research/conflict_inventory.json`, a
  human-inspected inventory of the 20 official conflict pairs. The spans, values and documents in it
  are real benchmark content; the claim keys are hand-normalized.
- **Entity resolution covers people, not the claim subjects.** Aliases are resolved from real
  `Name <email>` bindings in the corpus; the entities that own ClaimKeys are still derived by
  normalising the claim key itself. Linking a claim's author to a resolved person is not wired up.
- **A question reaches a claim by lexical overlap** with the claim key: at least 3 shared terms and
  at least half the claim key's terms. Measured on all 40 evaluated questions, that resolves 20/20
  conflict questions to the right claim and 0/20 `info_not_found` questions to any claim; a looser
  rule (2 shared terms) falsely matched 4 of them. Embedding-based claim matching would scale
  better and is not implemented.
- Candidate retrieval is lexical BM25. Semantic retrieval would change recall, not the temporal
  argument.

## Attribution

Canon is built on other people's work. Everything below is used under its own licence.

**Database** — [HydraDB OSS](https://github.com/hydra-db/hydradb) (AGPL-3.0), run from the
published `ghcr.io/hydra-db/hydradb` image with MinIO as the S3-compatible backend.

**Datasets** — [EnterpriseRAG-Bench](https://huggingface.co/datasets/onyx-dot-app/EnterpriseRAG-Bench)
by Onyx: 511,962 documents and 500 questions. Documents, questions, gold answers and the
per-question `answer_facts` rubric all come from that dataset and are unmodified. The
[benchmark repository](https://github.com/onyx-dot-app/EnterpriseRAG-Bench) also publishes an
answer-evaluation harness.

**Python** — `pyarrow` (Apache-2.0) to read the documents parquet, `huggingface_hub` (Apache-2.0)
to fetch it, `fastapi` + `uvicorn` (MIT/BSD-3) for the service, `anthropic` (MIT) for the answer and
judge models, `python-dotenv` (BSD-3), `pytest` and `ruff` (MIT) for the quality gate. SQLite FTS5
ships with Python.

**Web** — `next` (MIT), `react` (MIT), `tailwindcss` (MIT), `@iconify/react` with the
[Hugeicons](https://hugeicons.com) icon set (MIT).

**Models** — `claude-sonnet-5` and `claude-haiku-4-5` via the Anthropic API for answer generation
and judging; Qwen3 via an OpenAI-compatible local endpoint for offline runs. Every result file
records which model produced it.

No code was copied from another project. The lexical store, claim graph, canonization order,
residue sweep, identity resolution and evaluation harness in this repository are original.

## License

MIT
