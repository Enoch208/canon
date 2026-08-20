import re
from dataclasses import dataclass

from canon_evaluation.context import BuiltContext
from canon_extraction.values import find_all, item_variants, normalize, value_variants

EMPHASIS = re.compile(r"[*_`]+")
WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ContextMetrics:
    arm: str
    context_docs: int
    current_gold_in_context: bool
    retired_gold_in_context: bool
    retired_value_in_context: bool
    current_value_in_context: bool

    @property
    def leaked(self) -> bool:
        return self.retired_gold_in_context


@dataclass(frozen=True, slots=True)
class AnswerMetrics:
    states_current_value: bool
    states_retired_value: bool
    abstained: bool

    @property
    def prefers_retired_value(self) -> bool:
        return self.states_retired_value and not self.states_current_value and not self.abstained

    @property
    def answers_with_current_value(self) -> bool:
        return self.states_current_value and not self.abstained


def plain_text(text: str) -> str:
    return normalize(WHITESPACE.sub(" ", EMPHASIS.sub("", text)))


def contains_any(text: str, value: str) -> bool:
    return any(find_all(text, variant) for variant in value_variants(value))


def states_value(text: str, value: str) -> bool:
    normalized = plain_text(text)
    items = item_variants(value)
    if not items:
        return contains_any(normalized, value)
    return all(contains_any(normalized, item) for item in items)


def context_metrics(
    context: BuiltContext,
    old_doc_id: str,
    new_doc_id: str,
    old_value: str,
    new_value: str,
) -> ContextMetrics:
    doc_ids = set(context.doc_ids)
    doc_text = "\n\n".join(doc.text for doc in context.docs)
    return ContextMetrics(
        arm=context.arm,
        context_docs=len(context.docs),
        current_gold_in_context=new_doc_id in doc_ids,
        retired_gold_in_context=old_doc_id in doc_ids,
        retired_value_in_context=states_value(doc_text, old_value),
        current_value_in_context=states_value(doc_text, new_value),
    )


def answer_metrics(answer_text: str, old_value: str, new_value: str, unknown: str) -> AnswerMetrics:
    stripped = answer_text.strip()
    abstained = plain_text(stripped).upper().startswith(unknown)
    return AnswerMetrics(
        states_current_value=states_value(stripped, new_value),
        states_retired_value=states_value(stripped, old_value),
        abstained=abstained,
    )


def rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0
