import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from canon_evaluation.answering import UNKNOWN_TOKEN, Answer, GuardedAnswerModel
from canon_evaluation.context import BuiltContext, baseline_context, canon_context
from canon_evaluation.metrics import (
    AnswerMetrics,
    ContextMetrics,
    answer_metrics,
    context_metrics,
    rate,
)
from canon_evaluation.questions import BenchQuestion
from canon_extraction.conflicts import ConflictRecord
from canon_graph.grounding import GroundingMode, ground
from canon_graph.resolve import GraphReader
from canon_graph.schema import TruthState
from canon_retrieval.store import CorpusStore

TOP_K = 10
BACKFILL_RESERVE = 6


@dataclass(frozen=True, slots=True)
class Timing:
    retrieval_ms: float
    grounding_ms: float


@dataclass(frozen=True, slots=True)
class ArmResult:
    arm: str
    doc_ids: tuple[str, ...]
    metrics: ContextMetrics
    answer: str | None
    answer_metrics: AnswerMetrics | None


@dataclass(frozen=True, slots=True)
class ConflictResult:
    question_id: str
    question: str
    claim_key: str
    old_value: str
    new_value: str
    old_doc_id: str
    new_doc_id: str
    graph_state: str
    graph_current_value: str | None
    graph_transition: str
    temporal_quality: str
    dropped_doc_ids: tuple[str, ...]
    graph_pinned_doc_ids: tuple[str, ...]
    baseline: ArmResult
    canon_filtered: ArmResult
    canon: ArmResult
    historical_keeps_retired_gold: bool
    historical_drops_current_gold: bool
    timing: Timing
    hydra_query_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AbstentionResult:
    question_id: str
    question: str
    graph_state: str
    baseline_answer: str | None
    baseline_abstained: bool | None
    canon_answer: str | None
    canon_abstained: bool | None
    canon_docs: int


@dataclass(slots=True)
class BenchmarkReport:
    measured_at: str
    corpus_documents: int
    top_k: int
    answer_model: str | None
    not_run: list[str] = field(default_factory=list)
    answers_completed: int | None = None
    conflicts: list[ConflictResult] = field(default_factory=list)
    abstentions: list[AbstentionResult] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        total = len(self.conflicts)
        baseline_leak = sum(1 for c in self.conflicts if c.baseline.metrics.leaked)
        canon_leak = sum(1 for c in self.conflicts if c.canon.metrics.leaked)
        filtered_leak = sum(1 for c in self.conflicts if c.canon_filtered.metrics.leaked)
        pinned = sum(1 for c in self.conflicts if c.graph_pinned_doc_ids)
        baseline_retired_doc = sum(
            1 for c in self.conflicts if c.baseline.metrics.retired_gold_in_context
        )
        canon_retired_doc = sum(
            1 for c in self.conflicts if c.canon.metrics.retired_gold_in_context
        )
        baseline_current_doc = sum(
            1 for c in self.conflicts if c.baseline.metrics.current_gold_in_context
        )
        canon_current_doc = sum(
            1 for c in self.conflicts if c.canon.metrics.current_gold_in_context
        )
        summary: dict[str, object] = {
            "conflict_questions": total,
            "canon_filtered_retired_gold_doc_in_context": filtered_leak,
            "baseline_retired_gold_doc_in_context": baseline_retired_doc,
            "canon_retired_gold_doc_in_context": canon_retired_doc,
            "baseline_retired_value_string_in_context": sum(
                1 for c in self.conflicts if c.baseline.metrics.retired_value_in_context
            ),
            "canon_retired_value_string_in_context": sum(
                1 for c in self.conflicts if c.canon.metrics.retired_value_in_context
            ),
            "baseline_current_gold_doc_in_context": baseline_current_doc,
            "canon_current_gold_doc_in_context": canon_current_doc,
            "baseline_leakage_rate": rate(baseline_leak, total),
            "canon_leakage_rate": rate(canon_leak, total),
            "graph_canon_states": sum(
                1 for c in self.conflicts if c.graph_state == str(TruthState.CANON)
            ),
            "graph_contested_states": sum(
                1 for c in self.conflicts if c.graph_state == str(TruthState.CONTESTED)
            ),
            "canon_questions_with_graph_pinned_docs": pinned,
            "historical_keeps_retired_gold": sum(
                1 for c in self.conflicts if c.historical_keeps_retired_gold
            ),
            "abstention_questions": len(self.abstentions),
            "abstention_graph_returns_unknown": sum(
                1 for a in self.abstentions if a.graph_state == str(TruthState.UNKNOWN)
            ),
        }
        answered = [c for c in self.conflicts if c.canon.answer_metrics is not None]
        if answered:
            summary["baseline_answer_states_current_value"] = sum(
                1 for c in answered if c.baseline.answer_metrics.states_current_value
            )
            summary["canon_answer_states_current_value"] = sum(
                1 for c in answered if c.canon.answer_metrics.states_current_value
            )
            summary["baseline_answer_states_retired_value"] = sum(
                1 for c in answered if c.baseline.answer_metrics.states_retired_value
            )
            summary["canon_answer_states_retired_value"] = sum(
                1 for c in answered if c.canon.answer_metrics.states_retired_value
            )
        abstained = [a for a in self.abstentions if a.canon_abstained is not None]
        if abstained:
            summary["baseline_abstained"] = sum(1 for a in abstained if a.baseline_abstained)
            summary["canon_abstained"] = sum(1 for a in abstained if a.canon_abstained)
        latencies = sorted(c.timing.grounding_ms for c in self.conflicts)
        retrievals = sorted(c.timing.retrieval_ms for c in self.conflicts)
        if latencies:
            summary["grounding_ms_p50"] = percentile(latencies, 0.5)
            summary["grounding_ms_p95"] = percentile(latencies, 0.95)
            summary["retrieval_ms_p50"] = percentile(retrievals, 0.5)
            summary["retrieval_ms_p95"] = percentile(retrievals, 0.95)
        return summary

    def as_dict(self) -> dict[str, object]:
        return {
            "measured_at": self.measured_at,
            "corpus_documents": self.corpus_documents,
            "top_k": self.top_k,
            "answer_model": self.answer_model,
            "answers_completed": self.answers_completed,
            "not_run": self.not_run,
            "summary": self.summary(),
            "conflicts": [asdict(result) for result in self.conflicts],
            "abstentions": [asdict(result) for result in self.abstentions],
        }


def percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, int(round(fraction * (len(sorted_values) - 1))))
    return round(sorted_values[index], 2)


def build_arm(
    context: BuiltContext,
    record: ConflictRecord,
    model: GuardedAnswerModel | None,
) -> ArmResult:
    metrics = context_metrics(
        context, record.old_doc_id, record.new_doc_id, record.old_value, record.new_value
    )
    answer: Answer | None = model.answer(record.question, context.text) if model else None
    return ArmResult(
        arm=context.arm,
        doc_ids=context.doc_ids,
        metrics=metrics,
        answer=answer.text if answer else None,
        answer_metrics=(
            answer_metrics(answer.text, record.old_value, record.new_value, UNKNOWN_TOKEN)
            if answer
            else None
        ),
    )


def run_conflict(
    record: ConflictRecord,
    store: CorpusStore,
    reader: GraphReader,
    model: GuardedAnswerModel | None,
    top_k: int = TOP_K,
) -> ConflictResult:
    started = time.perf_counter()
    deep_hits = store.search(record.question, k=top_k + BACKFILL_RESERVE)
    retrieval_ms = (time.perf_counter() - started) * 1000
    hits = deep_hits[:top_k]
    backfill = deep_hits[top_k:]
    doc_ids = tuple(hit.doc_id for hit in hits)

    started = time.perf_counter()
    grounding = ground(reader, record.question, doc_ids, pin_graph_evidence=True)
    grounding_ms = (time.perf_counter() - started) * 1000
    historical = ground(
        reader,
        record.question,
        doc_ids,
        mode=GroundingMode.HISTORICAL,
        pin_graph_evidence=True,
    )

    baseline_built = baseline_context(store, hits, record.question)
    target_docs = len(baseline_built.docs)
    baseline = build_arm(baseline_built, record, model)
    canon_filtered = build_arm(
        canon_context(
            store,
            grounding,
            record.question,
            include_note=False,
            backfill=backfill,
            target_docs=target_docs,
        ),
        record,
        model,
    )
    canon = build_arm(
        canon_context(
            store,
            grounding,
            record.question,
            backfill=backfill,
            target_docs=target_docs,
        ),
        record,
        model,
    )
    primary = grounding.primary
    return ConflictResult(
        question_id=record.question_id,
        question=record.question,
        claim_key=record.claim_key,
        old_value=record.old_value,
        new_value=record.new_value,
        old_doc_id=record.old_doc_id,
        new_doc_id=record.new_doc_id,
        graph_state=str(grounding.state),
        graph_current_value=primary.current.value if primary and primary.current else None,
        graph_transition=str(primary.transition) if primary else "NONE",
        temporal_quality=str(primary.temporal_quality) if primary else "T3",
        dropped_doc_ids=grounding.dropped_doc_ids,
        graph_pinned_doc_ids=grounding.pinned_doc_ids,
        baseline=baseline,
        canon_filtered=canon_filtered,
        canon=canon,
        historical_keeps_retired_gold=(
            record.old_doc_id in historical.kept_doc_ids + historical.pinned_doc_ids
        ),
        historical_drops_current_gold=record.new_doc_id not in historical.kept_doc_ids,
        timing=Timing(round(retrieval_ms, 2), round(grounding_ms, 2)),
        hydra_query_names=tuple(dict.fromkeys(card.query_name for card in grounding.query_cards)),
    )


def run_abstention(
    question: BenchQuestion,
    store: CorpusStore,
    reader: GraphReader,
    model: GuardedAnswerModel | None,
    top_k: int = TOP_K,
) -> AbstentionResult:
    hits = store.search(question.question, k=top_k)
    grounding = ground(reader, question.question, tuple(hit.doc_id for hit in hits))
    baseline = baseline_context(store, hits, question.question)
    canon = canon_context(store, grounding, question.question)
    baseline_answer = model.answer(question.question, baseline.text) if model else None
    canon_answer = model.answer(question.question, canon.text) if model else None
    return AbstentionResult(
        question_id=question.question_id,
        question=question.question,
        graph_state=str(grounding.state),
        baseline_answer=baseline_answer.text if baseline_answer else None,
        baseline_abstained=(
            baseline_answer.text.strip().upper().startswith(UNKNOWN_TOKEN)
            if baseline_answer
            else None
        ),
        canon_answer=canon_answer.text if canon_answer else None,
        canon_abstained=(
            canon_answer.text.strip().upper().startswith(UNKNOWN_TOKEN) if canon_answer else None
        ),
        canon_docs=len(canon.docs),
    )


def run_benchmark(
    records: tuple[ConflictRecord, ...],
    abstention_questions: tuple[BenchQuestion, ...],
    store: CorpusStore,
    reader: GraphReader,
    model: GuardedAnswerModel | None,
    model_note: str,
    top_k: int = TOP_K,
) -> BenchmarkReport:
    report = BenchmarkReport(
        measured_at=datetime.now(UTC).isoformat(),
        corpus_documents=store.count(),
        top_k=top_k,
        answer_model=model.name if model else None,
    )
    if model is None:
        report.not_run.append(f"answer generation and answer-level metrics: {model_note}")
    for record in records:
        report.conflicts.append(run_conflict(record, store, reader, model, top_k))
    for question in abstention_questions:
        report.abstentions.append(run_abstention(question, store, reader, model, top_k))
    if model is not None:
        report.answers_completed = model.answered
        if model.failure is not None:
            report.not_run.append(
                f"answer generation stopped after {model.answered} calls: {model.failure}"
            )
    return report
