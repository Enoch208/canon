from pydantic import BaseModel

from canon_graph.grounding import DocDisposition, GroundingMode
from canon_graph.schema import ResidueClass, TemporalQuality, Transition, TruthState


class QueryCardModel(BaseModel):
    engine: str
    operation: str
    query_name: str
    cypher: str
    parameters: dict[str, object]
    result_count: int
    client_round_trip_ms: float
    query_id: str
    engine_rows_duration_us: float | None
    engine_ops_observed: int | None


class EvidenceModel(BaseModel):
    doc_id: str
    discovery: str
    source_type: str
    title: str
    evidence_span: str
    stance: str
    structured: bool
    source_field: str | None
    asserted_at: str | None
    residue_class: ResidueClass | None


class CanonEventModel(BaseModel):
    id: int
    selects_value: str
    supersedes_event_id: int | None
    transition: Transition
    temporal_quality: TemporalQuality
    evidence_doc_id: str
    occurred_at: str | None


class ConflictSummaryModel(BaseModel):
    question_id: str
    claim_key: str
    entity: str
    predicate: str
    state: TruthState
    current_value: str | None
    retired_values: list[str]
    transition: Transition
    temporal_quality: TemporalQuality
    verified_structured_residue: int
    derived_free_text_residue: int
    lexical_restatement_residue: int


class TruthChangeModel(BaseModel):
    question_id: str
    claim_key: str
    entity: str
    predicate: str
    state: TruthState
    current_value: str | None
    retired_values: list[str]
    contested_values: list[str]
    transition: Transition
    temporal_quality: TemporalQuality
    events: list[CanonEventModel]
    current_evidence: list[EvidenceModel]
    retired_evidence: list[EvidenceModel]
    residue: list[EvidenceModel]
    query_cards: list[QueryCardModel]


class ResidueRowModel(BaseModel):
    question_id: str
    claim_key: str
    entity: str
    retired_value: str
    current_value: str | None
    residue_class: ResidueClass
    discovery: str
    doc_id: str
    source_type: str
    title: str
    evidence_span: str
    source_field: str | None


class ResidueReportModel(BaseModel):
    definition: dict[str, str]
    counts: dict[str, int]
    rows: list[ResidueRowModel]


class AliasCandidateModel(BaseModel):
    name: str
    organization: str


class AliasModel(BaseModel):
    value: str
    alias_type: str
    resolution: str
    support: int
    candidate_count: int
    candidates: list[AliasCandidateModel]
    evidence_doc_id: str
    evidence_span: str


class IdentityReportModel(BaseModel):
    definition: dict[str, str]
    corpus: dict[str, int]
    materialised: dict[str, int]
    note: str
    aliases: list[AliasModel]


class DashboardModel(BaseModel):
    corpus_documents: int
    claim_keys: int
    current_conflicts: int
    contested_claims: int
    verified_residue: int
    derived_residue: int
    lexical_restatement_residue: int
    verified_resurrections: int
    resurrection_note: str
    graph_counts: dict[str, int]
    graph_counts_measured_at: str | None


class OfficialArmModel(BaseModel):
    label: str
    questions_scored: int
    correctness_pct: float
    completeness_pct: float
    combined_score: float
    document_recall_pct: float
    invalid_extra_docs: float
    by_question_type: dict[str, dict[str, int]]


class OfficialEvalModel(BaseModel):
    harness: str
    harness_repo: str
    judge_model: str
    measured_at: str
    arms: dict[str, OfficialArmModel]


class GroundedDocModel(BaseModel):
    doc_id: str
    source_type: str
    title: str
    disposition: DocDisposition
    rank: int | None
    kept: bool
    evidence_span: str | None = None


class EnvelopeModel(BaseModel):
    questions: int
    known_conflict_questions: int
    known_conflict_interventions: int
    other_questions: int
    other_questions_context_changed: int
    other_questions_context_unchanged: int
    other_questions_expected_doc_dropped: int
    documents_dropped_total: int
    documents_pinned_total: int
    other_documents_dropped: int
    other_documents_pinned: int


class AskRequest(BaseModel):
    question: str
    mode: GroundingMode = GroundingMode.CURRENT
    top_k: int = 10


class AskResponse(BaseModel):
    question: str
    mode: GroundingMode
    state: TruthState
    answer_value: str | None
    why: str
    claim_key: str | None
    temporal_quality: TemporalQuality | None
    transition: Transition | None
    evidence: list[EvidenceModel]
    retired_evidence_filtered: int
    documents: list[GroundedDocModel]
    backfill_doc_ids: list[str]
    query_cards: list[QueryCardModel]
    retrieval_ms: float
    grounding_ms: float


class CutReasonModel(BaseModel):
    doc_id: str
    claim_key: str | None
    transition: Transition | None
    temporal_quality: TemporalQuality | None
    evidence_span: str | None


class GroundResponse(BaseModel):
    state: TruthState
    mode: GroundingMode
    answer_value: str | None
    why: str
    input_ranking: list[str]
    current_evidence: list[str]
    suppressed_evidence: list[str]
    historical_evidence: list[str]
    backfill_evidence: list[str]
    cut: list[CutReasonModel]
    final_context: list[str]
    context_sha256: str
    hydra_query_ids: list[str]
    proof: list[QueryCardModel]
    retrieval_ms: float
    grounding_ms: float
