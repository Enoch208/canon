import time
from dataclasses import dataclass

from canon_evaluation.questions import BenchQuestion
from canon_evaluation.runner import TOP_K
from canon_graph.grounding import ground
from canon_graph.resolve import GraphReader
from canon_retrieval.store import CorpusStore


@dataclass(frozen=True, slots=True)
class EnvelopeRow:
    question_id: str
    question_type: str
    known_conflict: bool
    context_docs: int
    dropped_doc_ids: tuple[str, ...]
    pinned_doc_ids: tuple[str, ...]
    expected_docs_dropped: tuple[str, ...]
    graph_state: str
    grounding_ms: float


@dataclass(frozen=True, slots=True)
class EnvelopeReport:
    rows: tuple[EnvelopeRow, ...]

    def summary(self) -> dict[str, object]:
        known = [r for r in self.rows if r.known_conflict]
        other = [r for r in self.rows if not r.known_conflict]
        other_touched = [r for r in other if r.dropped_doc_ids or r.pinned_doc_ids]
        other_harmed = [r for r in other if r.expected_docs_dropped]
        return {
            "questions": len(self.rows),
            "known_conflict_questions": len(known),
            "known_conflict_interventions": sum(
                1 for r in known if r.dropped_doc_ids or r.pinned_doc_ids
            ),
            "other_questions": len(other),
            "other_questions_context_changed": len(other_touched),
            "other_questions_context_unchanged": len(other) - len(other_touched),
            "other_questions_expected_doc_dropped": len(other_harmed),
            "other_changed_question_ids": sorted(r.question_id for r in other_touched),
            "other_harmed_question_ids": sorted(r.question_id for r in other_harmed),
            "documents_dropped_total": sum(len(r.dropped_doc_ids) for r in self.rows),
            "documents_pinned_total": sum(len(r.pinned_doc_ids) for r in self.rows),
            "other_documents_dropped": sum(len(r.dropped_doc_ids) for r in other),
            "other_documents_pinned": sum(len(r.pinned_doc_ids) for r in other),
            "by_question_type": self._by_type(),
        }

    def _by_type(self) -> dict[str, dict[str, int]]:
        grouped: dict[str, dict[str, int]] = {}
        for row in self.rows:
            bucket = grouped.setdefault(
                row.question_type, {"questions": 0, "context_changed": 0, "expected_doc_dropped": 0}
            )
            bucket["questions"] += 1
            if row.dropped_doc_ids or row.pinned_doc_ids:
                bucket["context_changed"] += 1
            if row.expected_docs_dropped:
                bucket["expected_doc_dropped"] += 1
        return grouped


def sweep(
    questions: tuple[BenchQuestion, ...],
    conflict_question_ids: frozenset[str],
    store: CorpusStore,
    reader: GraphReader,
    top_k: int = TOP_K,
) -> EnvelopeReport:
    rows: list[EnvelopeRow] = []
    for question in questions:
        hits = store.search(question.question, k=top_k)
        doc_ids = tuple(hit.doc_id for hit in hits)
        started = time.perf_counter()
        grounding = ground(reader, question.question, doc_ids, pin_graph_evidence=True)
        elapsed = (time.perf_counter() - started) * 1000
        dropped = grounding.dropped_doc_ids
        expected = frozenset(question.expected_doc_ids)
        rows.append(
            EnvelopeRow(
                question_id=question.question_id,
                question_type=question.question_type,
                known_conflict=question.question_id in conflict_question_ids,
                context_docs=len(doc_ids),
                dropped_doc_ids=dropped,
                pinned_doc_ids=grounding.pinned_doc_ids,
                expected_docs_dropped=tuple(d for d in dropped if d in expected),
                graph_state=str(grounding.state),
                grounding_ms=round(elapsed, 2),
            )
        )
    return EnvelopeReport(tuple(rows))


def trace_interventions(
    report: EnvelopeReport,
    retired_gold: dict[str, str],
    current_gold: dict[str, str],
) -> dict[str, dict[str, str]]:
    traced: dict[str, dict[str, str]] = {}
    for row in report.rows:
        if row.known_conflict:
            continue
        for doc_id in row.dropped_doc_ids:
            origin = retired_gold.get(doc_id)
            traced[f"{row.question_id}:dropped:{doc_id}"] = {
                "kind": "dropped",
                "origin": f"retired gold of {origin}" if origin else "outside the gold set",
            }
        for doc_id in row.pinned_doc_ids:
            origin = current_gold.get(doc_id)
            traced[f"{row.question_id}:pinned:{doc_id}"] = {
                "kind": "pinned",
                "origin": f"current gold of {origin}" if origin else "outside the gold set",
            }
    return traced
