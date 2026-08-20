import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from canon_extraction.structured import LineMatch, match_at
from canon_extraction.values import find_all, normalize, value_variants
from canon_graph.canonize import AssertionInput, ClaimBundle, SupersessionSignal
from canon_graph.schema import ExtractionMethod, Stance, TemporalQuality
from canon_retrieval.store import Document

ISO_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


class DocumentSource(Protocol):
    def document(self, doc_id: str) -> Document | None: ...


@dataclass(frozen=True, slots=True)
class ConflictRecord:
    question_id: str
    question: str
    claim_key: str
    old_value: str
    new_value: str
    old_doc_id: str
    new_doc_id: str
    old_span: str
    new_span: str
    explicit_supersession: bool
    temporal_quality: TemporalQuality
    gold_answer: str
    demo_score: int


@dataclass(frozen=True, slots=True)
class ConflictInventory:
    dataset: str
    records: tuple[ConflictRecord, ...]
    primary_demo_question_id: str
    ranked_question_ids: tuple[str, ...]


def load_inventory(path: Path) -> ConflictInventory:
    raw = json.loads(path.read_text())
    records = tuple(
        ConflictRecord(
            question_id=item["question_id"],
            question=item["question"],
            claim_key=item["claim_key"],
            old_value=normalize(item["old_proposition"]),
            new_value=normalize(item["new_proposition"]),
            old_doc_id=item["old_doc_id"],
            new_doc_id=item["new_doc_id"],
            old_span=item["old_span"],
            new_span=item["new_span"],
            explicit_supersession=bool(item.get("explicit_supersession_in_text")),
            temporal_quality=TemporalQuality(item["timestamp_quality"]),
            gold_answer=item.get("gold_answer", ""),
            demo_score=int(item.get("demo_score", 0)),
        )
        for item in raw["conflicts"]
    )
    return ConflictInventory(
        dataset=raw["dataset"],
        records=records,
        primary_demo_question_id=raw["primary_demo_question_id"],
        ranked_question_ids=tuple(raw["ranked_question_ids"]),
    )


def split_claim_key(claim_key: str) -> tuple[str, str]:
    entity, _, predicate = claim_key.rpartition(".")
    if not entity:
        return claim_key, "value"
    return entity, predicate


def date_in(text: str) -> str | None:
    match = ISO_DATE.search(text)
    return match.group(1) if match else None


def span_line(document: Document, value: str, span: str) -> LineMatch | None:
    positions = find_all(document.content, span[:80])
    if not positions:
        for variant in value_variants(value):
            positions = find_all(document.content, variant)
            if positions:
                break
    if not positions:
        return None
    return match_at(document.source_type, document.content, positions[0])


def span_assertion(document: Document, value: str, span: str, stance: Stance) -> AssertionInput:
    line = span_line(document, value, span)
    structured = line.structured if line else False
    source_field = line.field_name if line else None
    return AssertionInput(
        doc_id=document.doc_id,
        source_type=document.source_type,
        value=value,
        evidence_span=span,
        stance=stance,
        structured=structured,
        extraction_method=ExtractionMethod.STRUCTURED_FIELD
        if structured
        else ExtractionMethod.INVENTORY,
        asserted_at=date_in(span),
        source_field=source_field,
    )


def bundle_for(record: ConflictRecord, documents: DocumentSource) -> ClaimBundle:
    old_doc = documents.document(record.old_doc_id)
    new_doc = documents.document(record.new_doc_id)
    if old_doc is None or new_doc is None:
        missing = record.old_doc_id if old_doc is None else record.new_doc_id
        raise FileNotFoundError(f"{record.question_id}: gold document {missing} not available")
    entity, predicate = split_claim_key(record.claim_key)
    assertions = (
        span_assertion(old_doc, record.old_value, record.old_span, Stance.CURRENT),
        span_assertion(new_doc, record.new_value, record.new_span, Stance.CURRENT),
    )
    supersessions: tuple[SupersessionSignal, ...] = ()
    if record.explicit_supersession:
        supersessions = (
            SupersessionSignal(
                doc_id=record.new_doc_id,
                from_value=record.old_value,
                to_value=record.new_value,
                evidence_span=record.new_span,
                occurred_at=date_in(record.new_span),
            ),
        )
    return ClaimBundle(
        entity_name=entity,
        entity_type="enterprise_object",
        key=record.claim_key,
        predicate=predicate,
        question_id=record.question_id,
        assertions=assertions,
        supersessions=supersessions,
        temporal_quality=record.temporal_quality,
    )
