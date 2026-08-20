from dataclasses import dataclass, field
from enum import StrEnum


class TruthState(StrEnum):
    CANON = "CANON"
    CONTESTED = "CONTESTED"
    UNKNOWN = "UNKNOWN"


class TemporalQuality(StrEnum):
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class PropositionStatus(StrEnum):
    CURRENT = "current"
    RETIRED = "retired"
    CONTESTED = "contested"
    UNRESOLVED = "unresolved"


class Stance(StrEnum):
    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"
    PROPOSED = "PROPOSED"
    REJECTED = "REJECTED"
    UNCERTAIN = "UNCERTAIN"


class ResidueClass(StrEnum):
    VERIFIED_STRUCTURED = "VERIFIED_STRUCTURED"
    DERIVED_FREE_TEXT = "DERIVED_FREE_TEXT"
    HISTORICAL_REFERENCE = "HISTORICAL_REFERENCE"
    REJECTED_REFERENCE = "REJECTED_REFERENCE"
    LEXICAL_RESTATEMENT = "LEXICAL_RESTATEMENT"
    NOT_AN_ASSERTION = "NOT_AN_ASSERTION"


class Transition(StrEnum):
    EXPLICIT_SUPERSESSION = "EXPLICIT_SUPERSESSION"
    STRUCTURED_TRANSITION = "STRUCTURED_TRANSITION"
    TEMPORAL_ORDER = "TEMPORAL_ORDER"
    CORROBORATION_TIEBREAK = "CORROBORATION_TIEBREAK"
    NONE = "NONE"


class Discovery(StrEnum):
    CONFLICT_PAIR = "conflict_pair"
    CORPUS_SCAN = "corpus_scan"


class ExtractionMethod(StrEnum):
    STRUCTURED_FIELD = "structured_field"
    LEXICAL_SPAN = "lexical_span"
    LLM = "llm"
    INVENTORY = "inventory"


class NodeKind(StrEnum):
    ENTITY = "Entity"
    PERSON = "Person"
    ALIAS = "Alias"
    CLAIM_KEY = "ClaimKey"
    PROPOSITION = "Proposition"
    ASSERTION = "Assertion"
    CANON_EVENT = "CanonEvent"
    ARTIFACT = "Artifact"


class EdgeType(StrEnum):
    HAS_CLAIM = "HAS_CLAIM"
    RESOLVES_TO = "RESOLVES_TO"
    HAS_VALUE = "HAS_VALUE"
    ASSERTS = "ASSERTS"
    IN_ARTIFACT = "IN_ARTIFACT"
    SELECTS = "SELECTS"
    SUPERSEDES = "SUPERSEDES"


EDGE_ENDPOINTS: dict["EdgeType", tuple["NodeKind", "NodeKind"]] = {}


@dataclass(frozen=True, slots=True)
class Entity:
    id: int
    name: str
    entity_type: str


@dataclass(frozen=True, slots=True)
class ClaimKey:
    id: int
    entity_id: int
    key: str
    predicate: str
    question_id: str


@dataclass(frozen=True, slots=True)
class Proposition:
    id: int
    claim_key_id: int
    value: str
    status: PropositionStatus


@dataclass(frozen=True, slots=True)
class Artifact:
    id: int
    doc_id: str
    source_type: str
    title: str


@dataclass(frozen=True, slots=True)
class Assertion:
    id: int
    proposition_id: int
    artifact_id: int
    doc_id: str
    source_type: str
    evidence_span: str
    stance: Stance
    extraction_method: ExtractionMethod
    structured: bool
    discovery: Discovery
    asserted_at: str | None = None
    source_field: str | None = None
    residue_class: ResidueClass | None = None


@dataclass(frozen=True, slots=True)
class CanonEvent:
    id: int
    claim_key_id: int
    selects_proposition_id: int
    supersedes_event_id: int | None
    transition: Transition
    temporal_quality: TemporalQuality
    evidence_doc_id: str
    occurred_at: str | None = None


@dataclass(frozen=True, slots=True)
class Person:
    id: int
    name: str
    organization: str


@dataclass(frozen=True, slots=True)
class Alias:
    id: int
    value: str
    alias_type: str
    resolution: str
    support: int
    candidate_count: int
    evidence_doc_id: str
    evidence_span: str


@dataclass(frozen=True, slots=True)
class ClaimGraph:
    entity: Entity
    claim_key: ClaimKey
    propositions: tuple[Proposition, ...]
    artifacts: tuple[Artifact, ...]
    assertions: tuple[Assertion, ...]
    events: tuple[CanonEvent, ...]
    state: TruthState
    temporal_quality: TemporalQuality
    residue: tuple[Assertion, ...] = field(default_factory=tuple)


EDGE_ENDPOINTS.update(
    {
        EdgeType.HAS_CLAIM: (NodeKind.ENTITY, NodeKind.CLAIM_KEY),
        EdgeType.RESOLVES_TO: (NodeKind.ALIAS, NodeKind.PERSON),
        EdgeType.HAS_VALUE: (NodeKind.CLAIM_KEY, NodeKind.PROPOSITION),
        EdgeType.ASSERTS: (NodeKind.ASSERTION, NodeKind.PROPOSITION),
        EdgeType.IN_ARTIFACT: (NodeKind.ASSERTION, NodeKind.ARTIFACT),
        EdgeType.SELECTS: (NodeKind.CANON_EVENT, NodeKind.PROPOSITION),
        EdgeType.SUPERSEDES: (NodeKind.CANON_EVENT, NodeKind.CANON_EVENT),
    }
)
