from dataclasses import dataclass

from canon_extraction.structured import match_at
from canon_extraction.values import find_all, normalize, value_variants
from canon_graph.schema import ResidueClass
from canon_retrieval.store import STOPWORDS, TOKEN, CorpusStore, Document, fts_phrase

MAX_CANDIDATES = 500
MIN_ANCHOR_CHARS = 3
SPECIFIC_ANCHOR_MAX_SHARE = 0.02
SPECIFIC_ANCHOR_MIN_DF = 50
MIN_PREDICATE_HITS_WITHOUT_ENTITY = 2


@dataclass(frozen=True, slots=True)
class ResidueCandidate:
    doc_id: str
    source_type: str
    title: str
    matched_variant: str
    entity_anchors_matched: tuple[str, ...]
    predicate_anchors_in_line: tuple[str, ...]
    line_no: int
    line: str
    field_name: str | None
    structured: bool
    residue_class: ResidueClass


@dataclass(frozen=True, slots=True)
class ResidueScan:
    value: str
    variants: tuple[str, ...]
    entity_anchors: tuple[str, ...]
    predicate_anchors: tuple[str, ...]
    fts_query: str
    fts_hits: int
    rejected_for_anchoring: int
    candidates: tuple[ResidueCandidate, ...]

    def count(self, residue_class: ResidueClass) -> int:
        return sum(1 for candidate in self.candidates if candidate.residue_class is residue_class)


def anchor_terms(text: str) -> tuple[str, ...]:
    terms: dict[str, None] = {}
    for token in normalize(text.replace("_", " ")).lower().split(" "):
        cleaned = token.strip(".,;:()[]\"'")
        if len(cleaned) >= MIN_ANCHOR_CHARS and cleaned not in STOPWORDS:
            terms.setdefault(cleaned, None)
    return tuple(terms)


def specific_anchors(store: CorpusStore, anchors: tuple[str, ...]) -> tuple[str, ...]:
    threshold = max(SPECIFIC_ANCHOR_MIN_DF, int(store.count() * SPECIFIC_ANCHOR_MAX_SHARE))
    specific: list[str] = []
    for anchor in anchors:
        pieces = TOKEN.findall(anchor)
        if not pieces:
            continue
        frequency = min(store.document_frequency(piece) for piece in pieces)
        if frequency <= threshold:
            specific.append(anchor)
    return tuple(specific)


def residue_fts_query(
    variants: tuple[str, ...], entity_anchors: tuple[str, ...], predicate_anchors: tuple[str, ...]
) -> str:
    value_part = " OR ".join(fts_phrase(variant) for variant in variants)
    entity_part = " OR ".join(fts_phrase(anchor) for anchor in entity_anchors)
    predicate_part = " OR ".join(fts_phrase(anchor) for anchor in predicate_anchors)
    parts = [f"({value_part})"]
    if entity_part:
        parts.append(f"({entity_part})")
    if predicate_part:
        parts.append(f"({predicate_part})")
    return " AND ".join(parts)


def anchors_present(text: str, anchors: tuple[str, ...]) -> tuple[str, ...]:
    lowered = text.lower()
    return tuple(anchor for anchor in anchors if anchor in lowered)


def first_match(document: Document, variants: tuple[str, ...]) -> tuple[str, int] | None:
    for variant in variants:
        positions = find_all(document.content, variant)
        if positions:
            return variant, positions[0]
    return None


def anchored(
    document: Document,
    line: str,
    entity_anchors: tuple[str, ...],
    predicate_anchors: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    entity_hits = anchors_present(f"{document.title}\n{document.content}", entity_anchors)
    line_hits = anchors_present(line, predicate_anchors)
    if len(entity_hits) < len(entity_anchors):
        return None
    if not entity_anchors and len(line_hits) < MIN_PREDICATE_HITS_WITHOUT_ENTITY:
        return None
    if predicate_anchors and not line_hits:
        return None
    return entity_hits, line_hits


def scan_residue(
    store: CorpusStore, value: str, entity: str, predicate: str, k: int = MAX_CANDIDATES
) -> ResidueScan:
    variants = value_variants(value)
    entity_anchors = specific_anchors(store, anchor_terms(entity))
    predicate_anchors = anchor_terms(predicate)
    match = residue_fts_query(variants, entity_anchors, predicate_anchors)
    hits = store.rank_match(match, k)
    candidates: list[ResidueCandidate] = []
    rejected = 0
    for hit in hits:
        document = store.document(hit.doc_id)
        if document is None:
            continue
        found = first_match(document, variants)
        if found is None:
            continue
        variant, position = found
        line = match_at(document.source_type, document.content, position)
        anchoring = anchored(document, line.line, entity_anchors, predicate_anchors)
        if anchoring is None:
            rejected += 1
            continue
        entity_hits, line_hits = anchoring
        candidates.append(
            ResidueCandidate(
                doc_id=document.doc_id,
                source_type=document.source_type,
                title=document.title,
                matched_variant=variant,
                entity_anchors_matched=entity_hits,
                predicate_anchors_in_line=line_hits,
                line_no=line.line_no,
                line=line.line,
                field_name=line.field_name,
                structured=line.structured,
                residue_class=line.residue_class,
            )
        )
    return ResidueScan(
        value=value,
        variants=variants,
        entity_anchors=entity_anchors,
        predicate_anchors=predicate_anchors,
        fts_query=match,
        fts_hits=len(hits),
        rejected_for_anchoring=rejected,
        candidates=tuple(candidates),
    )
