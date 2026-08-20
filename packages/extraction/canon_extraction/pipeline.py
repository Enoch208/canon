from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from canon_extraction.conflicts import ConflictInventory, ConflictRecord, bundle_for, span_line
from canon_extraction.residue import ResidueCandidate, ResidueScan, scan_residue
from canon_graph.canonize import AssertionInput, CanonDecision, ClaimBundle, canonize
from canon_graph.ingest import GraphWriter
from canon_graph.resolve import EvidenceRow, GraphReader
from canon_graph.schema import Discovery, ExtractionMethod, ResidueClass, Stance
from canon_retrieval.store import CorpusStore


@dataclass(frozen=True, slots=True)
class RecordedResidue:
    doc_id: str
    source_type: str
    title: str
    residue_class: str
    source_field: str | None
    evidence_span: str


@dataclass(frozen=True, slots=True)
class ResidueSummary:
    question_id: str
    claim_key: str
    retired_value: str
    entity_anchors: tuple[str, ...]
    predicate_anchors: tuple[str, ...]
    fts_query: str
    fts_hits: int
    rejected_for_anchoring: int
    verified_structured: int
    derived_free_text: int
    historical_reference: int
    rejected_reference: int
    lexical_restatement: int
    not_an_assertion: int
    recorded: tuple[RecordedResidue, ...]
    candidates: tuple[ResidueCandidate, ...]


@dataclass(frozen=True, slots=True)
class ClaimSeedResult:
    question_id: str
    claim_key: str
    state: str
    current_value: str | None
    retired_values: tuple[str, ...]
    transition: str
    temporal_quality: str
    why: str
    residue: ResidueSummary | None


@dataclass(slots=True)
class SeedReport:
    started_at: str
    corpus_documents: int
    claims: list[ClaimSeedResult] = field(default_factory=list)
    nodes_created: int = 0
    edges_created: int = 0
    skipped_existing: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "started_at": self.started_at,
            "corpus_documents": self.corpus_documents,
            "claims": [asdict(claim) for claim in self.claims],
            "nodes_created": self.nodes_created,
            "edges_created": self.edges_created,
            "skipped_existing": self.skipped_existing,
            "verified_structured_residue_total": sum(
                c.residue.verified_structured for c in self.claims if c.residue
            ),
            "derived_free_text_residue_total": sum(
                c.residue.derived_free_text for c in self.claims if c.residue
            ),
            "not_an_assertion_total": sum(
                c.residue.not_an_assertion for c in self.claims if c.residue
            ),
            "lexical_restatement_total": sum(
                c.residue.lexical_restatement for c in self.claims if c.residue
            ),
            "historical_reference_total": sum(
                c.residue.historical_reference for c in self.claims if c.residue
            ),
            "rejected_reference_total": sum(
                c.residue.rejected_reference for c in self.claims if c.residue
            ),
        }


def gold_residue_classes(
    bundle: ClaimBundle, decision: CanonDecision, store: CorpusStore
) -> dict[str, ResidueClass]:
    classes: dict[str, ResidueClass] = {}
    for assertion in bundle.assertions:
        if assertion.value not in decision.retired_values:
            continue
        document = store.document(assertion.doc_id)
        if document is None:
            continue
        line = span_line(document, assertion.value, assertion.evidence_span)
        if line is not None:
            classes[assertion.doc_id] = line.residue_class
    return classes


def residue_assertion(candidate: ResidueCandidate, value: str) -> AssertionInput:
    return AssertionInput(
        doc_id=candidate.doc_id,
        source_type=candidate.source_type,
        value=value,
        evidence_span=candidate.line[:500],
        stance=Stance.CURRENT if candidate.structured else Stance.UNCERTAIN,
        structured=candidate.structured,
        extraction_method=ExtractionMethod.STRUCTURED_FIELD
        if candidate.structured
        else ExtractionMethod.LEXICAL_SPAN,
        source_field=candidate.field_name,
    )


def summarize(
    question_id: str, claim_key: str, scan: ResidueScan, recorded: tuple[EvidenceRow, ...]
) -> ResidueSummary:
    counts = Counter(row.assertion.residue_class for row in recorded)
    return ResidueSummary(
        question_id=question_id,
        claim_key=claim_key,
        retired_value=scan.value,
        entity_anchors=scan.entity_anchors,
        predicate_anchors=scan.predicate_anchors,
        fts_query=scan.fts_query,
        fts_hits=scan.fts_hits,
        rejected_for_anchoring=scan.rejected_for_anchoring,
        verified_structured=counts[ResidueClass.VERIFIED_STRUCTURED],
        derived_free_text=counts[ResidueClass.DERIVED_FREE_TEXT],
        historical_reference=counts[ResidueClass.HISTORICAL_REFERENCE],
        rejected_reference=counts[ResidueClass.REJECTED_REFERENCE],
        lexical_restatement=counts[ResidueClass.LEXICAL_RESTATEMENT],
        not_an_assertion=counts[ResidueClass.NOT_AN_ASSERTION],
        recorded=tuple(
            RecordedResidue(
                doc_id=row.assertion.doc_id,
                source_type=row.assertion.source_type,
                title=row.title,
                residue_class=str(row.assertion.residue_class),
                source_field=row.assertion.source_field,
                evidence_span=row.assertion.evidence_span,
            )
            for row in recorded
        ),
        candidates=scan.candidates,
    )


def write_residue(
    writer: GraphWriter,
    claim_key: str,
    proposition_id: int,
    value: str,
    scan: ResidueScan,
    gold_doc_ids: frozenset[str],
) -> None:
    for candidate in scan.candidates:
        if candidate.doc_id in gold_doc_ids:
            continue
        writer.write_assertion(
            claim_key,
            proposition_id,
            residue_assertion(candidate, value),
            candidate.title,
            candidate.residue_class,
            Discovery.CORPUS_SCAN,
        )


def seed_conflicts(
    inventory: ConflictInventory,
    store: CorpusStore,
    writer: GraphWriter,
    scan_corpus: bool = True,
) -> SeedReport:
    report = SeedReport(datetime.now(UTC).isoformat(), store.count())
    titles: dict[str, str] = {}
    for record in inventory.records:
        bundle = bundle_for(record, store)
        for assertion in bundle.assertions:
            document = store.document(assertion.doc_id)
            titles[assertion.doc_id] = document.title if document else ""
        decision = canonize(bundle)
        gold_classes = gold_residue_classes(bundle, decision, store)
        _, propositions = writer.write_claim(bundle, decision, titles, residue_classes=gold_classes)
        residue = None
        if scan_corpus and decision.retired_values:
            residue = _scan_and_write(
                writer, record, bundle.entity_name, bundle.predicate, decision, propositions, store
            )
        report.claims.append(
            ClaimSeedResult(
                question_id=record.question_id,
                claim_key=record.claim_key,
                state=str(decision.state),
                current_value=decision.current_value,
                retired_values=decision.retired_values,
                transition=str(decision.transition),
                temporal_quality=str(decision.temporal_quality),
                why=decision.why,
                residue=residue,
            )
        )
    report.nodes_created = writer.report.nodes_created
    report.edges_created = writer.report.edges_created
    report.skipped_existing = writer.report.skipped_existing
    return report


def _scan_and_write(
    writer: GraphWriter,
    record: ConflictRecord,
    entity: str,
    predicate: str,
    decision: CanonDecision,
    propositions: dict[str, int],
    store: CorpusStore,
) -> ResidueSummary:
    retired_value = decision.retired_values[0]
    proposition_id = propositions[retired_value]
    scan = scan_residue(store, retired_value, entity, predicate)
    write_residue(
        writer,
        record.claim_key,
        proposition_id,
        retired_value,
        scan,
        frozenset({record.old_doc_id, record.new_doc_id}),
    )
    recorded = GraphReader(writer.client).residue(proposition_id)
    return summarize(record.question_id, record.claim_key, scan, recorded)
