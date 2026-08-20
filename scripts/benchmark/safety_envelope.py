#!/usr/bin/env python3
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from canon_evaluation.answering import load_env_file
from canon_evaluation.envelope import sweep, trace_interventions
from canon_evaluation.questions import load_question_ids, load_questions
from canon_extraction.conflicts import load_inventory
from canon_graph.hydra import HydraClient
from canon_graph.resolve import GraphReader
from canon_retrieval.dataset import corpus_db_path
from canon_retrieval.store import CorpusStore

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evidence" / "safety_envelope.json"


def main() -> int:
    load_env_file(ROOT)
    client = HydraClient.from_env()
    if not client.healthy():
        print("HydraDB unreachable; run `make hydra-up`")
        return 2
    store = CorpusStore(corpus_db_path(ROOT))
    reader = GraphReader(client)
    questions = tuple(load_questions(ROOT / "eval" / "questions.jsonl").values())
    conflict_ids = frozenset(
        load_question_ids(ROOT / "eval" / "question_ids.json")["conflicting_info"]
    )
    report = sweep(questions, conflict_ids, store, reader)
    summary = report.summary()
    records = load_inventory(ROOT / "research" / "conflict_inventory.json").records
    traced = trace_interventions(
        report,
        {r.old_doc_id: r.question_id for r in records},
        {r.new_doc_id: r.question_id for r in records},
    )
    payload = {
        "measured_at": datetime.now(UTC).isoformat(),
        "design": (
            "Deterministic grounding sweep over every benchmark question: BM25 top-10, then the "
            "HydraDB temporal grounding layer. No model in the loop. Measures where Canon "
            "intervenes (drops or pins) and whether any expected document is ever dropped on a "
            "question outside the known supersession conflicts."
        ),
        "top_k": 10,
        "summary": summary,
        "interventions_outside_conflicts": traced,
        "rows": [asdict(row) for row in report.rows],
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    hidden = ("by_question_type", "other_changed_question_ids", "other_harmed_question_ids")
    for key, value in summary.items():
        if key not in hidden:
            print(f"{key}: {value}")
    print(f"changed elsewhere: {summary['other_changed_question_ids']}")
    for key, info in traced.items():
        print(f"  {key} — {info['origin']}")
    print(f"harmed elsewhere: {summary['other_harmed_question_ids']}")
    print(f"evidence: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
