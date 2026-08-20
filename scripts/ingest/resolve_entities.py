#!/usr/bin/env python3
import argparse
import json
import sys
import time
from pathlib import Path

from canon_extraction.entities import Resolution, extract_bindings, resolve
from canon_graph.hydra import HydraClient
from canon_graph.ingest import MAX_ALIAS_CANDIDATES, GraphWriter
from canon_graph.queries import COUNT_ALIASES_BY_RESOLUTION
from canon_retrieval.dataset import corpus_db_path
from canon_retrieval.store import CorpusStore

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "entities.json"
BINDING_SOURCES = ("gmail",)


def graph_alias_states() -> dict[str, int]:
    client = HydraClient.from_env()
    if not client.healthy():
        return {}
    counts: dict[str, int] = {}
    for state in Resolution:
        result = client.run(
            COUNT_ALIASES_BY_RESOLUTION, {"namespace": "canon", "resolution": str(state)}
        )
        counts[str(state)] = int(result.scalar() or 0)
    return counts


def stratified(aliases: tuple, limit: int) -> list:
    per_state = max(1, limit // len(Resolution))
    chosen: list = []
    for state in Resolution:
        ranked = sorted(
            (a for a in aliases if a.resolution is state), key=lambda a: (-a.support, a.value)
        )
        chosen.extend(ranked[:per_state])
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve people and aliases from the corpus")
    parser.add_argument("--limit", type=int, default=None, help="scan only the first N documents")
    parser.add_argument(
        "--write-limit", type=int, default=300, help="max aliases materialised in HydraDB"
    )
    parser.add_argument(
        "--no-write", action="store_true", help="extract and report without writing"
    )
    args = parser.parse_args()

    db_path = corpus_db_path(ROOT)
    if not db_path.exists():
        print(f"corpus store {db_path} missing; run `make index`")
        return 2
    store = CorpusStore(db_path)

    placeholders = ",".join("?" for _ in BINDING_SOURCES)
    sql = (
        f"SELECT doc_id, source_type, content FROM documents WHERE source_type IN ({placeholders})"
    )
    if args.limit is not None:
        sql += f" LIMIT {int(args.limit)}"
    started = time.perf_counter()
    rows = store.fetch(sql, BINDING_SOURCES)
    bindings = []
    for doc_id, source_type, content in rows:
        bindings.extend(extract_bindings(str(doc_id), str(source_type), str(content)))
    identity = resolve(bindings, documents_scanned=len(rows))
    extraction_seconds = time.perf_counter() - started

    selected = stratified(identity.aliases, args.write_limit)
    written_states: dict[str, int] = {}
    written = 0
    if not args.no_write:
        client = HydraClient.from_env()
        if not client.healthy():
            print(f"HydraDB unreachable at {client.base_url}; run `make hydra-up`")
            return 2
        writer = GraphWriter(client)
        for alias in selected:
            writer.write_identity(
                alias.value,
                str(alias.alias_type),
                str(alias.resolution),
                alias.support,
                alias.evidence_doc_id,
                alias.evidence_span,
                [(p.key, p.name, p.organization) for p in alias.candidates],
            )
            written += 1
            state = str(alias.resolution)
            written_states[state] = written_states.get(state, 0) + 1

    counts = identity.counts()
    graph_counts = graph_alias_states()
    report = {
        "documents_scanned": identity.documents_scanned,
        "source_types": list(BINDING_SOURCES),
        "bindings_found": identity.bindings_found,
        "people": len(identity.people),
        "aliases": len(identity.aliases),
        "alias_states": counts,
        "aliases_written_to_hydradb": written,
        "alias_states_in_hydradb": graph_counts,
        "written_alias_states": written_states,
        "write_selection": "stratified: top aliases by supporting-binding count per state",
        "candidate_edges_capped_at": MAX_ALIAS_CANDIDATES,
        "write_limit": args.write_limit,
        "extraction_seconds": round(extraction_seconds, 1),
        "ambiguous_examples": [
            {
                "alias": alias.value,
                "alias_type": str(alias.alias_type),
                "candidates": [p.key for p in alias.candidates],
                "evidence_doc_id": alias.evidence_doc_id,
                "evidence_span": alias.evidence_span,
            }
            for alias in identity.aliases
            if alias.resolution is Resolution.AMBIGUOUS
        ][:10],
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "ambiguous_examples"}, indent=2))
    print(f"evidence: {EVIDENCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
