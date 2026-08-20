#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from canon_evaluation.answering import load_answer_model, load_env_file
from canon_evaluation.context import baseline_context, canon_context
from canon_evaluation.runner import BACKFILL_RESERVE, TOP_K
from canon_extraction.conflicts import load_inventory
from canon_graph.grounding import ground
from canon_graph.hydra import HydraClient
from canon_graph.resolve import GraphReader
from canon_retrieval.dataset import corpus_db_path
from canon_retrieval.store import CorpusStore

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "eval" / "official"
EVIDENCE = ROOT / "evidence" / "second_model.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Answer the 20 conflict questions with a second model, baseline vs Temporal Cut"
    )
    parser.add_argument("--model", default="claude-haiku-4-5")
    args = parser.parse_args()

    load_env_file(ROOT)
    client = HydraClient.from_env()
    if not client.healthy():
        print("HydraDB unreachable; run `make hydra-up`")
        return 2
    store = CorpusStore(corpus_db_path(ROOT))
    reader = GraphReader(client)
    model, reason = load_answer_model(args.model)
    if model is None:
        print(f"not run: {reason}")
        return 2

    records = load_inventory(ROOT / "research" / "conflict_inventory.json").records
    rows: dict[str, list[dict[str, object]]] = {"baseline": [], "canon_filtered": []}
    for record in records:
        hits = store.search(record.question, k=TOP_K + BACKFILL_RESERVE)
        top, backfill = hits[:TOP_K], hits[TOP_K:]
        grounding = ground(
            reader, record.question, tuple(h.doc_id for h in top), pin_graph_evidence=True
        )
        base = baseline_context(store, top, record.question)
        cut = canon_context(
            store,
            grounding,
            record.question,
            include_note=False,
            backfill=backfill,
            target_docs=len(base.docs),
        )
        for arm, context in (("baseline", base), ("canon_filtered", cut)):
            answer = model.answer(record.question, context.text)
            rows[arm].append(
                {
                    "question_id": record.question_id,
                    "answer": answer.text if answer else "",
                    "document_ids": list(context.doc_ids),
                }
            )
        print(f"{record.question_id}  answered both arms")

    for arm, arm_rows in rows.items():
        path = OUT_DIR / f"second_model_{arm}.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in arm_rows))
        print(f"wrote {path.relative_to(ROOT)}")
    EVIDENCE.write_text(
        json.dumps(
            {
                "measured_at": datetime.now(UTC).isoformat(),
                "answer_model": model.name,
                "questions": len(records),
                "arms": sorted(rows),
                "design": (
                    "Same 20 conflict questions, same BM25 ranking, same 10-document budget, "
                    "same prompt template as the primary model. Only the answering model and "
                    "the context topology change. Scored by the official harness separately."
                ),
                "official_scores": "pending harness run",
            },
            indent=2,
        )
        + "\n"
    )
    if model.failure is not None:
        print(f"model failure after {model.answered}: {model.failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
