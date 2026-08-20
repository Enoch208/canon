#!/usr/bin/env python3
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from canon_extraction.conflicts import load_inventory
from canon_graph.grounding import ground
from canon_graph.hydra import HydraClient
from canon_graph.resolve import GraphReader
from canon_retrieval.dataset import corpus_db_path
from canon_retrieval.store import CorpusStore

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "topk_sweep.json"
KS = (5, 10, 20)


def main() -> int:
    client = HydraClient.from_env()
    if not client.healthy():
        print("HydraDB unreachable")
        return 2
    store = CorpusStore(corpus_db_path(ROOT))
    reader = GraphReader(client)
    records = load_inventory(ROOT / "research" / "conflict_inventory.json").records

    rows = []
    for k in KS:
        baseline_leak = 0
        canon_leak = 0
        current_in_baseline = 0
        current_in_canon = 0
        for record in records:
            hits = store.search(record.question, k=k)
            doc_ids = tuple(hit.doc_id for hit in hits)
            grounding = ground(reader, record.question, doc_ids, pin_graph_evidence=True)
            kept = set(grounding.kept_doc_ids) | set(grounding.pinned_doc_ids)
            if record.old_doc_id in doc_ids:
                baseline_leak += 1
            if record.old_doc_id in kept:
                canon_leak += 1
            if record.new_doc_id in doc_ids:
                current_in_baseline += 1
            if record.new_doc_id in kept:
                current_in_canon += 1
        rows.append(
            {
                "top_k": k,
                "questions": len(records),
                "baseline_superseded_in_context": baseline_leak,
                "canon_superseded_in_context": canon_leak,
                "baseline_current_gold_in_context": current_in_baseline,
                "canon_current_gold_in_context": current_in_canon,
            }
        )
        print(
            f"k={k:>2}  superseded: baseline {baseline_leak}/20 vs canon {canon_leak}/20"
            f"   current gold: baseline {current_in_baseline}/20 vs canon {current_in_canon}/20"
        )
    EVIDENCE.write_text(
        json.dumps(
            {"measured_at": datetime.now(UTC).isoformat(), "rows": rows}, indent=2, sort_keys=True
        )
        + "\n"
    )
    print(f"evidence: {EVIDENCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
