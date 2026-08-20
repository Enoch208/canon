from collections.abc import Sequence
from dataclasses import dataclass

from canon_graph.grounding import DocDisposition, Grounding
from canon_graph.schema import TruthState
from canon_retrieval.store import CorpusStore, Hit, query_terms

MAX_DOC_CHARS = 4000
WINDOW_STEP_DIVISOR = 4


@dataclass(frozen=True, slots=True)
class ContextDoc:
    doc_id: str
    source_type: str
    title: str
    text: str
    disposition: DocDisposition | None


@dataclass(frozen=True, slots=True)
class BuiltContext:
    arm: str
    docs: tuple[ContextDoc, ...]
    graph_note: str
    text: str

    @property
    def doc_ids(self) -> tuple[str, ...]:
        return tuple(doc.doc_id for doc in self.docs)


def relevant_window(content: str, question: str, max_chars: int = MAX_DOC_CHARS) -> str:
    if len(content) <= max_chars:
        return content
    terms = query_terms(question)
    if not terms:
        return content[:max_chars]
    lowered = content.lower()
    step = max(1, max_chars // WINDOW_STEP_DIVISOR)
    best_start = 0
    best_score = -1
    for start in range(0, max(1, len(content) - max_chars + step), step):
        window = lowered[start : start + max_chars]
        score = sum(window.count(term) for term in terms)
        if score > best_score:
            best_score = score
            best_start = start
    return content[best_start : best_start + max_chars]


def render(docs: tuple[ContextDoc, ...], graph_note: str) -> str:
    parts: list[str] = []
    if graph_note:
        parts.append(graph_note)
    for index, doc in enumerate(docs, start=1):
        parts.append(
            f"[Document {index}] source={doc.source_type} id={doc.doc_id}\n"
            f"Title: {doc.title}\n{doc.text}"
        )
    return "\n\n".join(parts)


def load_docs(
    store: CorpusStore,
    doc_ids: tuple[str, ...],
    dispositions: dict[str, DocDisposition],
    question: str,
) -> tuple[ContextDoc, ...]:
    docs: list[ContextDoc] = []
    for doc_id in doc_ids:
        document = store.document(doc_id)
        if document is None:
            continue
        docs.append(
            ContextDoc(
                doc_id=doc_id,
                source_type=document.source_type,
                title=document.title,
                text=relevant_window(document.content, question),
                disposition=dispositions.get(doc_id),
            )
        )
    return tuple(docs)


def baseline_context(store: CorpusStore, hits: list[Hit], question: str) -> BuiltContext:
    docs = load_docs(store, tuple(hit.doc_id for hit in hits), {}, question)
    return BuiltContext("baseline", docs, "", render(docs, ""))


def graph_note(grounding: Grounding) -> str:
    primary = grounding.primary
    if primary is None or primary.state is TruthState.UNKNOWN:
        return ""
    if primary.state is TruthState.CONTESTED:
        values = ", ".join(p.value for p in primary.contested)
        return (
            f"[Canon claim graph] {primary.claim_key.key}: CONTESTED between {values}; "
            "evidence does not establish which value is current."
        )
    current = primary.current.value if primary.current else ""
    retired = ", ".join(p.value for p in primary.retired)
    return (
        f"[Canon claim graph] {primary.claim_key.key}: current value {current}; "
        f"retired value(s) {retired} superseded via {primary.transition} "
        f"(temporal quality {primary.temporal_quality}). Documents asserting the retired value "
        "as current were excluded from this context."
    )


def backfilled_doc_ids(
    grounding: Grounding, backfill: Sequence[Hit], target_docs: int
) -> tuple[str, ...]:
    dropped = set(grounding.dropped_doc_ids)
    doc_ids = list(grounding.kept_doc_ids + grounding.pinned_doc_ids)
    for hit in backfill:
        if len(doc_ids) >= target_docs:
            break
        if hit.doc_id in doc_ids or hit.doc_id in dropped:
            continue
        doc_ids.append(hit.doc_id)
    return tuple(doc_ids)


def canon_context(
    store: CorpusStore,
    grounding: Grounding,
    question: str,
    include_note: bool = True,
    backfill: Sequence[Hit] = (),
    target_docs: int = 0,
) -> BuiltContext:
    dispositions = {doc.doc_id: doc.disposition for doc in grounding.docs}
    doc_ids = backfilled_doc_ids(grounding, backfill, target_docs)
    docs = load_docs(store, doc_ids, dispositions, question)
    note = graph_note(grounding) if include_note else ""
    arm = "canon" if include_note else "canon_filtered"
    return BuiltContext(arm, docs, note, render(docs, note))
