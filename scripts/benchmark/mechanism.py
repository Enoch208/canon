#!/usr/bin/env python3
import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from canon_evaluation.answering import load_answer_model, load_env_file
from canon_evaluation.context import BuiltContext, load_docs, render
from canon_evaluation.runner import BACKFILL_RESERVE, TOP_K
from canon_extraction.conflicts import load_inventory
from canon_graph.grounding import ground
from canon_graph.hydra import HydraClient
from canon_graph.resolve import GraphReader
from canon_retrieval.dataset import corpus_db_path
from canon_retrieval.store import CorpusStore, Hit

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "eval" / "official"
EVIDENCE = ROOT / "evidence" / "mechanism.json"


@dataclass(frozen=True, slots=True)
class Arm:
    name: str
    cut: bool
    pin: bool


ARMS = (
    Arm("mechanism_cut_only", cut=True, pin=False),
    Arm("mechanism_pin_only", cut=False, pin=True),
)


def compose(
    arm: Arm,
    kept: tuple[str, ...],
    dropped: tuple[str, ...],
    pinned: tuple[str, ...],
    backfill: list[Hit],
    target: int,
) -> tuple[str, ...]:
    doc_ids = list(kept) if arm.cut else list(kept) + [d for d in dropped if d not in kept]
    extra = [p for p in pinned if p not in doc_ids] if arm.pin else []
    if extra:
        doc_ids = doc_ids[: max(0, target - len(extra))] + extra
    blocked = set(dropped) if arm.cut else set()
    for hit in backfill:
        if len(doc_ids) >= target:
            break
        if hit.doc_id in doc_ids or hit.doc_id in blocked:
            continue
        doc_ids.append(hit.doc_id)
    return tuple(doc_ids[:target])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Decompose the Temporal Cut into cut-only and pin-only arms"
    )
    parser.add_argument("--model", default="claude-sonnet-5")
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
    rows: dict[str, list[dict[str, object]]] = {arm.name: [] for arm in ARMS}
    composition: list[dict[str, object]] = []
    for record in records:
        hits = store.search(record.question, k=TOP_K + BACKFILL_RESERVE)
        top, backfill = hits[:TOP_K], hits[TOP_K:]
        doc_ids = tuple(hit.doc_id for hit in top)
        grounding = ground(reader, record.question, doc_ids, pin_graph_evidence=True)
        target = len(doc_ids)
        entry: dict[str, object] = {
            "question_id": record.question_id,
            "dropped": list(grounding.dropped_doc_ids),
            "pinned": list(grounding.pinned_doc_ids),
        }
        for arm in ARMS:
            selected = compose(
                arm,
                grounding.kept_doc_ids,
                grounding.dropped_doc_ids,
                grounding.pinned_doc_ids,
                backfill,
                target,
            )
            docs = load_docs(store, selected, {}, record.question)
            context = BuiltContext(arm.name, docs, "", render(docs, ""))
            answer = model.answer(record.question, context.text)
            rows[arm.name].append(
                {
                    "question_id": record.question_id,
                    "answer": answer.text if answer else "",
                    "document_ids": list(context.doc_ids),
                }
            )
            entry[f"{arm.name}_docs"] = len(context.doc_ids)
            entry[f"{arm.name}_retired_gold_in_context"] = record.old_doc_id in context.doc_ids
            entry[f"{arm.name}_current_gold_in_context"] = record.new_doc_id in context.doc_ids
        composition.append(entry)
        print(f"{record.question_id}  answered {len(ARMS)} arms")

    for name, arm_rows in rows.items():
        path = OUT_DIR / f"{name}.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in arm_rows))
        print(f"wrote {path.relative_to(ROOT)}")

    summary = {
        arm.name: {
            "retired_gold_doc_in_context": sum(
                1 for c in composition if c[f"{arm.name}_retired_gold_in_context"]
            ),
            "current_gold_doc_in_context": sum(
                1 for c in composition if c[f"{arm.name}_current_gold_in_context"]
            ),
            "context_documents": sum(int(c[f"{arm.name}_docs"]) for c in composition),
        }
        for arm in ARMS
    }
    EVIDENCE.write_text(
        json.dumps(
            {
                "measured_at": datetime.now(UTC).isoformat(),
                "answer_model": model.name,
                "design": (
                    "Decomposition of the Temporal Cut. cut_only removes documents proven "
                    "superseded and backfills from the same ranking but never pins graph "
                    "evidence; pin_only leaves every retrieved document in place and only adds "
                    "current evidence the retriever missed, evicting the lowest rank. Same 20 "
                    "questions, same 10-document budget, same model and prompt as every other arm."
                ),
                "questions": len(records),
                "summary": summary,
                "per_question": composition,
                "official_scores": "pending harness run",
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(summary, indent=2))
    if model.failure is not None:
        print(f"model failure after {model.answered}: {model.failure}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
