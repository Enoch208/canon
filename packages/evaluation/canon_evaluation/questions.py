import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BenchQuestion:
    question_id: str
    question_type: str
    question: str
    expected_doc_ids: tuple[str, ...]
    gold_answer: str
    answer_facts: tuple[str, ...]


def load_questions(path: Path) -> dict[str, BenchQuestion]:
    questions: dict[str, BenchQuestion] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        questions[row["question_id"]] = BenchQuestion(
            question_id=row["question_id"],
            question_type=row["question_type"],
            question=row["question"],
            expected_doc_ids=tuple(row.get("expected_doc_ids") or []),
            gold_answer=row.get("gold_answer") or "",
            answer_facts=tuple(row.get("answer_facts") or []),
        )
    return questions


def load_question_ids(path: Path) -> dict[str, tuple[str, ...]]:
    raw = json.loads(path.read_text())
    return {category: tuple(ids) for category, ids in raw.items()}
