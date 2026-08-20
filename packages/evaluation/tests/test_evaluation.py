from pathlib import Path

import anthropic
import httpx

from canon_evaluation.answering import (
    UNKNOWN_TOKEN,
    Answer,
    GuardedAnswerModel,
    load_answer_model,
    prompt_for,
)
from canon_evaluation.context import (
    BuiltContext,
    ContextDoc,
    backfilled_doc_ids,
    relevant_window,
    render,
)
from canon_evaluation.metrics import (
    answer_metrics,
    contains_any,
    context_metrics,
    plain_text,
    rate,
    states_value,
)
from canon_evaluation.questions import load_question_ids, load_questions
from canon_evaluation.runner import percentile
from canon_graph.grounding import DocDisposition, DocGrounding, Grounding, GroundingMode
from canon_graph.schema import TruthState
from canon_retrieval.store import Hit

ROOT = Path(__file__).resolve().parents[3]


def context_of(*texts: str) -> BuiltContext:
    docs = tuple(
        ContextDoc(f"dsid_{index}", "jira", "t", text, None) for index, text in enumerate(texts)
    )
    return BuiltContext("test", docs, "", render(docs, ""))


def test_contains_any_matches_value_variants() -> None:
    assert contains_any("breaks at 100k, 1M, and 5M monthly tokens", "100k / 1M / 5M")
    assert contains_any("reserve 20 percent of credits", "20%")
    assert not contains_any("breaks at 250k, 2M, and 10M", "100k / 1M / 5M")


def test_context_metrics_track_gold_docs_and_values() -> None:
    context = context_of("volume breaks at 250k, 2M, and 10M monthly tokens")
    metrics = context_metrics(context, "dsid_9", "dsid_0", "100k / 1M / 5M", "250k / 2M / 10M")
    assert metrics.current_gold_in_context is True
    assert metrics.retired_gold_in_context is False
    assert metrics.retired_value_in_context is False
    assert metrics.current_value_in_context is True
    assert metrics.leaked is False


def test_leakage_is_defined_by_the_superseded_document() -> None:
    context = context_of("breaks at 100k, 1M, and 5M monthly tokens")
    metrics = context_metrics(context, "dsid_0", "dsid_9", "100k / 1M / 5M", "250k / 2M / 10M")
    assert metrics.retired_gold_in_context is True
    assert metrics.leaked is True


def test_answer_metrics_detect_values_and_abstention() -> None:
    metrics = answer_metrics(
        "The breakpoints are 250k, 2M, and 10M.", "100k / 1M / 5M", "250k / 2M / 10M", UNKNOWN_TOKEN
    )
    assert metrics.states_current_value is True
    assert metrics.states_retired_value is False
    assert metrics.abstained is False
    assert answer_metrics(UNKNOWN_TOKEN, "a", "b", UNKNOWN_TOKEN).abstained is True


def test_prompt_and_render_are_identical_across_arms() -> None:
    context = context_of("body text")
    assert "[Document 1] source=jira id=dsid_0" in context.text
    assert prompt_for("Q?", context.text).endswith("Question: Q?\n\nAnswer:")


def test_percentile_and_rate() -> None:
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.5) == 3.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 0.95) == 4.0
    assert percentile([], 0.5) == 0.0
    assert rate(1, 4) == 0.25
    assert rate(1, 0) == 0.0


def test_benchmark_question_ids_match_the_official_files() -> None:
    ids = load_question_ids(ROOT / "eval" / "question_ids.json")
    questions = load_questions(ROOT / "eval" / "questions.jsonl")
    assert len(ids["conflicting_info"]) == 20
    assert len(ids["info_not_found"]) == 20
    for qid in ids["conflicting_info"]:
        assert questions[qid].question_type == "conflicting_info"
    for qid in ids["info_not_found"]:
        assert questions[qid].question_type == "info_not_found"
        assert questions[qid].expected_doc_ids == ()


def test_states_value_survives_markdown_and_reordering() -> None:
    answer = "The breakpoints are **250k**, **2M**, and **10M** monthly tokens."
    assert states_value(answer, "250k / 2M / 10M") is True
    assert states_value(answer, "100k / 1M / 5M") is False
    assert states_value("Reserve `30%` of credits", "30%") is True
    assert states_value("The breakpoints are 250k and 2M only", "250k / 2M / 10M") is False
    assert plain_text("**bold**  and `code`") == "bold and code"


def test_abstention_detects_unknown_behind_markdown() -> None:
    assert answer_metrics("**UNKNOWN**", "a", "b", UNKNOWN_TOKEN).abstained is True
    assert answer_metrics("It is 30%.", "20%", "30%", UNKNOWN_TOKEN).abstained is False


class BrokenModel:
    name = "test-model"
    calls = 0

    def answer(self, question: str, context: str) -> Answer:
        BrokenModel.calls += 1
        if BrokenModel.calls > 1:
            raise anthropic.BadRequestError(
                "credit balance is too low",
                response=httpx.Response(400, request=httpx.Request("POST", "http://test")),
                body=None,
            )
        return Answer("30%", "test-model", 10, 5, "end_turn")


def test_guarded_model_keeps_earlier_answers_and_records_the_failure() -> None:
    BrokenModel.calls = 0
    guard = GuardedAnswerModel(BrokenModel())
    assert guard.answer("q", "c") is not None
    assert guard.answer("q", "c") is None
    assert guard.answer("q", "c") is None
    assert guard.answered == 1
    assert guard.available is False
    assert guard.failure is not None and "credit" in guard.failure
    assert BrokenModel.calls == 2


def test_model_id_selects_the_backend() -> None:
    local, note = load_answer_model("qwen/qwen3-14b")
    assert local is not None and note == ""
    assert "qwen/qwen3-14b @ http" in local.name


def test_relevant_window_centres_on_the_question_terms() -> None:
    filler = "unrelated boilerplate. " * 300
    content = filler + "Volume discounts: breaks at 250k, 2M, and 10M monthly tokens." + filler
    question = "What monthly token volume discount breakpoints apply?"
    assert "250k, 2M, and 10M" not in content[:400]
    assert "250k, 2M, and 10M" in relevant_window(content, question, max_chars=400)
    assert len(relevant_window(content, question, max_chars=400)) == 400
    assert relevant_window("short doc", question, max_chars=400) == "short doc"


def grounding_of(kept: int, pinned: tuple[str, ...]) -> "Grounding":
    docs = tuple(
        DocGrounding(f"dsid_kept{index}", DocDisposition.UNLINKED, ()) for index in range(kept)
    )
    return Grounding(
        mode=GroundingMode.CURRENT,
        state=TruthState.CANON,
        resolutions=(),
        docs=docs,
        pinned_doc_ids=pinned,
        claim_key_matches=(),
    )


def test_pinned_doc_evicts_lowest_rank_instead_of_growing_context() -> None:
    doc_ids = backfilled_doc_ids(grounding_of(10, ("dsid_pin",)), [], target_docs=10)
    assert len(doc_ids) == 10
    assert "dsid_pin" in doc_ids
    assert "dsid_kept9" not in doc_ids
    assert doc_ids[:9] == tuple(f"dsid_kept{i}" for i in range(9))


def test_backfill_still_fills_after_drop_with_pin() -> None:
    hits = [Hit(f"dsid_fill{i}", "jira", "t", 1.0, i) for i in range(3)]
    doc_ids = backfilled_doc_ids(grounding_of(8, ("dsid_pin",)), hits, target_docs=10)
    assert len(doc_ids) == 10
    assert doc_ids[-2:] == ("dsid_pin", "dsid_fill0")
