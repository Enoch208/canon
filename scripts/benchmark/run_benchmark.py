#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from canon_evaluation.answering import DEFAULT_MODEL, load_answer_model, load_env_file
from canon_evaluation.questions import load_question_ids, load_questions
from canon_evaluation.runner import TOP_K, run_benchmark
from canon_extraction.conflicts import load_inventory
from canon_graph.hydra import HydraClient
from canon_graph.resolve import GraphReader
from canon_retrieval.dataset import corpus_db_path
from canon_retrieval.store import CorpusStore

ROOT = Path(__file__).resolve().parents[2]


def relative(path: Path) -> Path:
    resolved = path.resolve()
    return resolved.relative_to(ROOT) if resolved.is_relative_to(ROOT) else resolved


INVENTORY = ROOT / "research" / "conflict_inventory.json"
QUESTIONS = ROOT / "eval" / "questions.jsonl"
QUESTION_IDS = ROOT / "eval" / "question_ids.json"
RESULTS = ROOT / "eval" / "results" / "latest.json"
PARTIAL_RESULTS = ROOT / "eval" / "results" / "partial.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Baseline vs Canon benchmark")
    parser.add_argument("--top-k", type=int, default=TOP_K)
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="claude-* uses the Anthropic API; any other id is served by CANON_LOCAL_ENDPOINT",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="only the first N questions per set"
    )
    parser.add_argument("--no-answers", action="store_true", help="skip answer generation")
    parser.add_argument("--results-out", type=Path, default=None, help="override the results path")
    args = parser.parse_args()

    load_env_file(ROOT)
    client = HydraClient.from_env()
    if not client.healthy():
        print(f"HydraDB unreachable at {client.base_url}; run `make hydra-up`")
        return 2
    db_path = corpus_db_path(ROOT)
    if not db_path.exists():
        print(f"corpus store {db_path} missing; run `make index`")
        return 2

    store = CorpusStore(db_path)
    reader = GraphReader(client)
    if not reader.all_claim_keys():
        print("no claim keys in HydraDB; run `make seed`")
        return 2

    ids = load_question_ids(QUESTION_IDS)
    questions = load_questions(QUESTIONS)
    records = load_inventory(INVENTORY).records
    abstention = tuple(questions[qid] for qid in ids["info_not_found"])
    partial = args.limit is not None
    if partial:
        records = records[: args.limit]
        abstention = abstention[: args.limit]

    model, note = (
        (None, "disabled with --no-answers") if args.no_answers else load_answer_model(args.model)
    )
    destination = args.results_out or (PARTIAL_RESULTS if partial else RESULTS)
    if destination.exists() and model is None:
        existing = json.loads(destination.read_text())
        if existing.get("answers_completed"):
            print(
                f"refusing to overwrite {destination.name}: it holds "
                f"{existing['answers_completed']} graded answers and this run generated none. "
                "Re-run with an answer model, or pass --results-out to write elsewhere."
            )
            return 1
    destination.parent.mkdir(parents=True, exist_ok=True)

    report = run_benchmark(records, abstention, store, reader, model, note, args.top_k)

    payload = report.as_dict()
    payload["partial_run"] = partial
    payload["question_ids"] = {
        "conflicting_info": [record.question_id for record in records],
        "info_not_found": [question.question_id for question in abstention],
    }
    destination.write_text(json.dumps(payload, indent=2) + "\n")

    print(json.dumps(report.summary(), indent=2))
    for entry in report.not_run:
        print(f"not run: {entry}")
    if partial:
        print(f"partial run of {len(records)} questions per set; latest.json left untouched")
    print(f"results: {relative(destination)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
