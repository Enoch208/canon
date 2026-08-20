#!/usr/bin/env python3
import hashlib
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

from canon_evaluation.answering import load_answer_model, load_env_file
from canon_evaluation.context import baseline_context
from canon_evaluation.questions import load_question_ids, load_questions
from canon_extraction.conflicts import load_inventory
from canon_graph.grounding import ground
from canon_graph.hydra import HydraClient
from canon_graph.resolve import GraphReader
from canon_retrieval.dataset import corpus_db_path
from canon_retrieval.store import CorpusStore

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "eval" / "official" / "random_filter.jsonl"
EVIDENCE = ROOT / "evidence" / "random_control.json"
TOP_K = 10
RESERVE = 6


def rng_for(question_id: str) -> random.Random:
    seed = int.from_bytes(hashlib.blake2b(question_id.encode(), digest_size=8).digest(), "big")
    return random.Random(seed)


def main() -> int:
    load_env_file(ROOT)
    client = HydraClient.from_env()
    if not client.healthy():
        print("HydraDB unreachable")
        return 2
    store = CorpusStore(corpus_db_path(ROOT))
    reader = GraphReader(client)
    model, note = load_answer_model("claude-sonnet-5")
    if model is None:
        print(f"answer model unavailable: {note}")
        return 2

    records = {
        r.question_id: r
        for r in load_inventory(ROOT / "research" / "conflict_inventory.json").records
    }
    ids = load_question_ids(ROOT / "eval" / "question_ids.json")
    questions = load_questions(ROOT / "eval" / "questions.jsonl")

    rows = []
    stats = []
    for qid in [*ids["conflicting_info"], *ids["info_not_found"]]:
        question = records[qid].question if qid in records else questions[qid].question
        deep = store.search(question, k=TOP_K + RESERVE)
        hits = deep[:TOP_K]
        reserve = deep[TOP_K:]
        grounding = ground(reader, question, tuple(h.doc_id for h in hits), pin_graph_evidence=True)
        removals = len(grounding.dropped_doc_ids)
        rng = rng_for(qid)
        removed = set(rng.sample(range(len(hits)), min(removals, len(hits)))) if removals else set()
        kept = [hit for index, hit in enumerate(hits) if index not in removed]
        removed_ids = {hits[index].doc_id for index in removed}
        for hit in reserve:
            if len(kept) >= len(hits):
                break
            if hit.doc_id not in removed_ids and all(k.doc_id != hit.doc_id for k in kept):
                kept.append(hit)
        context = baseline_context(store, kept, question)
        answer = model.answer(question, context.text)
        if answer is None:
            print(f"answer generation died at {qid}: {model.failure}")
            return 1
        superseded = records[qid].old_doc_id if qid in records else None
        stats.append(
            {
                "question_id": qid,
                "removals": removals,
                "random_removed_superseded": bool(superseded and superseded in removed_ids),
                "superseded_in_final_context": bool(
                    superseded and any(k.doc_id == superseded for k in kept)
                ),
            }
        )
        rows.append(
            {"question_id": qid, "answer": answer.text, "document_ids": [k.doc_id for k in kept]}
        )
        hit = stats[-1]["random_removed_superseded"]
        print(f"  {qid} removals={removals} random_hit_superseded={hit}")

    OUT.write_text("".join(json.dumps(row) + "\n" for row in rows))
    conflict_stats = [s for s in stats if s["question_id"] in records]
    EVIDENCE.write_text(
        json.dumps(
            {
                "measured_at": datetime.now(UTC).isoformat(),
                "design": (
                    "Remove the same number of documents Canon removes per question, chosen "
                    "uniformly at random (seeded by question id), backfill from the same ranking. "
                    "Same model, same prompt, same document count as every other arm."
                ),
                "answer_model": model.name,
                "questions": len(rows),
                "conflict_questions_where_random_hit_superseded": sum(
                    1 for s in conflict_stats if s["random_removed_superseded"]
                ),
                "conflict_questions_superseded_in_context": sum(
                    1 for s in conflict_stats if s["superseded_in_final_context"]
                ),
                "per_question": stats,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {OUT.relative_to(ROOT)} and {EVIDENCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
