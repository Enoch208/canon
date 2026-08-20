#!/usr/bin/env python3
import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "eval" / "results" / "runs"
OUT = ROOT / "eval" / "results" / "summary.json"
ARMS = ("baseline", "canon_filtered", "canon")
METRICS = (
    ("Superseded document in context", "retired_gold_doc_in_context", "deterministic"),
    ("Answer states the current value", "judged_states_current_value", "model-judged"),
    ("Answer presents retired as current", "judged_presents_retired_as_current", "model-judged"),
    ("Answer abstains", "judged_abstains", "model-judged"),
)


def spread(values: list[int]) -> dict[str, float]:
    return {
        "mean": round(statistics.mean(values), 2),
        "min": min(values),
        "max": max(values),
        "runs": len(values),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate repeated benchmark runs")
    parser.add_argument("--runs", type=Path, default=RUNS)
    args = parser.parse_args()

    files = sorted(args.runs.glob("run-*.json"))
    if not files:
        print(f"no run files in {args.runs}")
        return 2
    payloads = [json.loads(f.read_text()) for f in files]
    summaries = [p["summary"] for p in payloads]
    total = summaries[0]["conflict_questions"]

    aggregate: dict[str, dict[str, dict[str, float]]] = {}
    for _, key, _ in METRICS:
        aggregate[key] = {}
        for arm in ARMS:
            values = [s[f"{arm}_{key}"] for s in summaries if f"{arm}_{key}" in s]
            if values:
                aggregate[key][arm] = spread(values)

    payload = {
        "runs": [f.name for f in files],
        "run_count": len(files),
        "conflict_questions": total,
        "answer_model": payloads[0].get("answer_model"),
        "judge_model": summaries[0].get("judge_model"),
        "metrics": aggregate,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"{len(files)} runs: {', '.join(f.name for f in files)}")
    print(f"answer model {payload['answer_model']} | judge {payload['judge_model']}\n")
    print(f"{'metric':<38}{'kind':<14}" + "".join(f"{a:>18}" for a in ARMS))
    for label, key, kind in METRICS:
        cells = ""
        for arm in ARMS:
            stats = aggregate[key].get(arm)
            if not stats:
                cells += f"{'-':>18}"
            elif stats["min"] == stats["max"]:
                cells += f"{f'{stats["min"]}/{total}':>18}"
            else:
                cells += f"{f'{stats["mean"]}/{total} ({stats["min"]}-{stats["max"]})':>18}"
        print(f"{label:<38}{kind:<14}{cells}")
    print(f"\nsummary: {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
