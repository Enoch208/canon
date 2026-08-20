#!/usr/bin/env python3
import json
import sys
from pathlib import Path

from canon_extraction.conflicts import load_inventory

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "evidence" / "seed.json"
INVENTORY = ROOT / "research" / "conflict_inventory.json"
OUT = ROOT / "eval" / "residue_bench.jsonl"


def main() -> int:
    if not SEED.exists():
        print(f"{SEED} missing; run `make seed`")
        return 2
    seed = json.loads(SEED.read_text())
    records = {record.question_id: record for record in load_inventory(INVENTORY).records}
    rows: list[dict[str, object]] = []
    for claim in seed["claims"]:
        residue = claim["residue"]
        record = records[claim["question_id"]]
        recorded = residue["recorded"] if residue else []
        rows.append(
            {
                "question_id": claim["question_id"],
                "claim_key": claim["claim_key"],
                "retired_value": claim["retired_values"][0] if claim["retired_values"] else None,
                "current_value": claim["current_value"],
                "old_gold_doc": record.old_doc_id,
                "new_gold_doc": record.new_doc_id,
                "temporal_quality": claim["temporal_quality"],
                "transition": claim["transition"],
                "verified_structured_residue_ids": [
                    row["doc_id"]
                    for row in recorded
                    if row["residue_class"] == "VERIFIED_STRUCTURED"
                ],
                "lexical_restatement_ids": [
                    row["doc_id"]
                    for row in recorded
                    if row["residue_class"] == "LEXICAL_RESTATEMENT"
                ],
                "derived_residue_ids": [
                    row["doc_id"] for row in recorded if row["residue_class"] == "DERIVED_FREE_TEXT"
                ],
                "resurrection_ids": [],
                "evidence_spans": [
                    {
                        "doc_id": row["doc_id"],
                        "source_type": row["source_type"],
                        "span": row["evidence_span"],
                    }
                    for row in recorded
                ],
                "corpus_scanned": residue is not None,
                "fts_query": residue["fts_query"] if residue else None,
            }
        )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(row) + "\n" for row in rows))
    totals = {
        "rows": len(rows),
        "verified_structured": sum(len(row["verified_structured_residue_ids"]) for row in rows),
        "lexical_restatement": sum(len(row["lexical_restatement_ids"]) for row in rows),
        "resurrection": 0,
    }
    print(json.dumps(totals, indent=2))
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
