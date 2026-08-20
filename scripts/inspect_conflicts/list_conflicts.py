#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = ROOT / "eval" / "questions.jsonl"


def main() -> None:
    rows = []
    with QUESTIONS.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    conflicts = [row for row in rows if row.get("question_type") == "conflicting_info"]
    print(f"{len(conflicts)} conflicting_info questions")
    for row in conflicts:
        docs = list(dict.fromkeys(row.get("expected_doc_ids") or []))
        print(row["question_id"])
        print(" ".join(row.get("source_types") or []))
        print(row["question"])
        print("gold_docs " + " ".join(docs))
        print(row.get("gold_answer") or "")
        print()


if __name__ == "__main__":
    main()
