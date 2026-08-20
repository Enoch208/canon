import json
from dataclasses import dataclass
from typing import Protocol

import anthropic

from canon_evaluation.answering import supports_effort

DEFAULT_JUDGE_MODEL = "claude-sonnet-5"
JUDGE_EFFORT = "low"
JUDGE_SYSTEM = (
    "You grade one answer against a rubric of required facts taken from a benchmark. "
    "Work through the rubric fact by fact, then output JSON only, no prose, with exactly these "
    'keys: {"satisfied_facts": int, "total_facts": int, "states_current_value": bool, '
    '"presents_retired_as_current": bool, "abstains": bool}.\n'
    "states_current_value is true when the answer conveys the current value the rubric asks for, "
    "even if it is worded differently, formatted as a list, or accompanied by extra context. "
    "Rubric facts that merely permit or require mentioning the older value do not make it false.\n"
    "presents_retired_as_current is true only when the answer offers the outdated value as the "
    "present-tense answer. If the answer labels the old value as previous, retired, superseded, "
    "outdated, or still-supported-during-migration, it is false.\n"
    "abstains is true only when the answer declines to give an answer at all, for example a bare "
    "UNKNOWN. An answer that says UNKNOWN but then supplies the value is not an abstention."
)


@dataclass(frozen=True, slots=True)
class Verdict:
    satisfied_facts: int
    total_facts: int
    states_current_value: bool
    presents_retired_as_current: bool
    abstains: bool
    judge_model: str


class AnswerJudge(Protocol):
    @property
    def name(self) -> str: ...

    def judge(self, question: str, answer_facts: tuple[str, ...], answer: str) -> Verdict: ...


def judge_prompt(question: str, answer_facts: tuple[str, ...], answer: str) -> str:
    rubric = "\n".join(f"- {fact}" for fact in answer_facts)
    return (
        f"Question: {question}\n\nRubric of required facts:\n{rubric}\n\n"
        f"Answer to grade:\n{answer}\n\nJSON verdict:"
    )


class AnthropicJudge:
    def __init__(self, model: str = DEFAULT_JUDGE_MODEL, max_tokens: int = 2048) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._client = anthropic.Anthropic()
        self._effort = JUDGE_EFFORT if supports_effort(model) else None

    @property
    def name(self) -> str:
        return self._model

    def judge(self, question: str, answer_facts: tuple[str, ...], answer: str) -> Verdict:
        options: dict[str, object] = {}
        if self._effort is not None:
            options["output_config"] = {"effort": self._effort}
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": judge_prompt(question, answer_facts, answer)}],
            **options,
        )
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        return parse_verdict(text, response.model)


def majority(verdicts: list[Verdict]) -> tuple[Verdict, bool]:
    def vote(field: str) -> bool:
        return sum(1 for v in verdicts if getattr(v, field)) * 2 > len(verdicts)

    fields = ("states_current_value", "presents_retired_as_current", "abstains")
    unanimous = all(len({getattr(v, field) for v in verdicts}) == 1 for field in fields)
    middle = sorted(verdicts, key=lambda v: v.satisfied_facts)[len(verdicts) // 2]
    return (
        Verdict(
            satisfied_facts=middle.satisfied_facts,
            total_facts=middle.total_facts,
            states_current_value=vote("states_current_value"),
            presents_retired_as_current=vote("presents_retired_as_current"),
            abstains=vote("abstains"),
            judge_model=verdicts[0].judge_model,
        ),
        unanimous,
    )


def parse_verdict(text: str, judge_model: str) -> Verdict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"judge did not return JSON: {text[:200]}")
    payload = json.loads(text[start : end + 1])
    return Verdict(
        satisfied_facts=int(payload.get("satisfied_facts", 0)),
        total_facts=int(payload.get("total_facts", 0)),
        states_current_value=bool(payload["states_current_value"]),
        presents_retired_as_current=bool(payload["presents_retired_as_current"]),
        abstains=bool(payload["abstains"]),
        judge_model=judge_model,
    )
