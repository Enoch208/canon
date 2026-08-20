#!/usr/bin/env python3
import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from canon_evaluation.answering import load_env_file
from canon_evaluation.judge import DEFAULT_JUDGE_MODEL, AnthropicJudge, majority
from canon_evaluation.questions import load_questions

ROOT = Path(__file__).resolve().parents[2]


def relative(path: Path) -> Path:
    resolved = path.resolve()
    return resolved.relative_to(ROOT) if resolved.is_relative_to(ROOT) else resolved


RESULTS = ROOT / "eval" / "results" / "latest.json"
QUESTIONS = ROOT / "eval" / "questions.jsonl"
ARMS = ("baseline", "canon_filtered", "canon")


def tally(results: list[dict[str, object]], arm: str, key: str) -> int:
    return sum(1 for row in results if (row[arm].get("verdict") or {}).get(key))


def main() -> int:
    parser = argparse.ArgumentParser(description="Grade saved answers against the benchmark rubric")
    parser.add_argument("--model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--repeats", type=int, default=3, help="judge passes per answer")
    args = parser.parse_args()

    load_env_file(ROOT)
    payload = json.loads(args.results.read_text())
    conflicts = payload["conflicts"]
    if not any(conflict[arm].get("answer") for conflict in conflicts for arm in ARMS):
        print(f"{args.results} has no answers to grade; run the benchmark with an answer model")
        return 2

    questions = load_questions(QUESTIONS)
    judge = AnthropicJudge(args.model)
    graded = 0
    unanimous_count = 0
    for conflict in conflicts:
        facts = questions[conflict["question_id"]].answer_facts
        for arm in ARMS:
            answer = conflict[arm].get("answer")
            if not answer:
                continue
            passes = [judge.judge(conflict["question"], facts, answer) for _ in range(args.repeats)]
            verdict, unanimous = majority(passes)
            conflict[arm]["verdict"] = {
                **asdict(verdict),
                "total_facts": len(facts),
                "satisfied_facts": min(verdict.satisfied_facts, len(facts)),
                "unanimous": unanimous,
            }
            graded += 1
            unanimous_count += int(unanimous)

    summary = payload["summary"]
    summary["judge_model"] = judge.name
    summary["judged_answers"] = graded
    summary["judge_passes_per_answer"] = args.repeats
    summary["judge_unanimous_answers"] = unanimous_count
    for arm in ARMS:
        verdicts = [c[arm]["verdict"] for c in conflicts if c[arm].get("verdict")]
        summary[f"{arm}_judged_rubric_facts_satisfied"] = sum(
            v["satisfied_facts"] for v in verdicts
        )
        summary[f"{arm}_judged_rubric_facts_total"] = sum(v["total_facts"] for v in verdicts)
        summary[f"{arm}_judged_states_current_value"] = tally(
            conflicts, arm, "states_current_value"
        )
        summary[f"{arm}_judged_presents_retired_as_current"] = tally(
            conflicts, arm, "presents_retired_as_current"
        )
        summary[f"{arm}_judged_abstains"] = tally(conflicts, arm, "abstains")
    args.results.write_text(json.dumps(payload, indent=2) + "\n")

    total = summary["conflict_questions"]
    print(f"judge: {judge.name} (model-judged, {graded} answers graded)\n")
    print(f"{'metric':<40}{'baseline':>11}{'filtered':>11}{'canon':>10}")
    for label, key in (
        ("Answer states the current value", "judged_states_current_value"),
        ("Answer presents the retired value as current", "judged_presents_retired_as_current"),
        ("Answer abstains", "judged_abstains"),
    ):
        base, canon = summary["baseline_" + key], summary["canon_" + key]
        print(f"{label:<42}{base:>7}/{total}{canon:>7}/{total}")
    print(
        f"\njudge agreement: {unanimous_count}/{graded} answers unanimous across "
        f"{args.repeats} passes"
    )
    print(f"results: {relative(args.results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
