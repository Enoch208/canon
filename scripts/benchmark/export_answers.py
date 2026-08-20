#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "eval" / "results" / "latest.json"
OUT_DIR = ROOT / "eval" / "official"
ARMS = ("baseline", "canon_filtered", "canon")


def rows_for(results: dict, arm: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for conflict in results["conflicts"]:
        answer = conflict[arm].get("answer")
        rows.append(
            {
                "question_id": conflict["question_id"],
                "answer": answer or "",
                "document_ids": list(conflict[arm]["doc_ids"]),
            }
        )
    for abstention in results["abstentions"]:
        key = "baseline_answer" if arm == "baseline" else "canon_answer"
        answer = abstention.get(key)
        if answer is None:
            continue
        rows.append(
            {
                "question_id": abstention["question_id"],
                "answer": answer,
                "document_ids": list(abstention.get(f"{arm}_doc_ids", []) or []),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export answers in EnterpriseRAG-Bench official JSONL format"
    )
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    if not args.results.exists():
        print(f"results file {args.results} missing; run `make benchmark`")
        return 2
    results = json.loads(args.results.read_text())
    if not results.get("answers_completed"):
        print(f"{args.results.name} holds no generated answers; run `make benchmark` with a model")
        return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for arm in ARMS:
        rows = rows_for(results, arm)
        answered = sum(1 for row in rows if row["answer"])
        path = args.out_dir / f"{arm}.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        print(f"{path.relative_to(ROOT)}  {len(rows)} rows, {answered} with an answer")
    print("\nscore with the official harness (from a clone of the benchmark repo):")
    print("  python -m src.scripts.answer_evaluation.metrics_based_eval \\")
    print(
        f"      --answers-file {(args.out_dir / 'canon.jsonl').relative_to(ROOT)} --no-correction"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
