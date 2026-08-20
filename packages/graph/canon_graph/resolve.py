from dataclasses import dataclass, field, replace

from canon_graph import queries
from canon_graph.hydra import HydraClient, Param, Row
from canon_graph.querycard import HydraQueryCard, card_for
from canon_graph.schema import (
    Assertion,
    CanonEvent,
    ClaimKey,
    Discovery,
    Entity,
    ExtractionMethod,
    Proposition,
    PropositionStatus,
    ResidueClass,
    Stance,
    TemporalQuality,
    Transition,
    TruthState,
)


@dataclass(frozen=True, slots=True)
class EvidenceRow:
    assertion: Assertion
    title: str


@dataclass(frozen=True, slots=True)
class Resolution:
    claim_key: ClaimKey
    entity: Entity | None
    state: TruthState
    temporal_quality: TemporalQuality
    transition: Transition
    current: Proposition | None
    retired: tuple[Proposition, ...]
    contested: tuple[Proposition, ...]
    events: tuple[CanonEvent, ...]
    current_evidence: tuple[EvidenceRow, ...]
    retired_evidence: tuple[EvidenceRow, ...]
    query_cards: tuple[HydraQueryCard, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ArtifactClaim:
    assertion_id: int
    claim_key_id: int
    key: str
    proposition_id: int
    value: str
    status: PropositionStatus
    stance: Stance
    residue_class: ResidueClass | None
    evidence_span: str


def _text(row: Row, name: str) -> str:
    value = row.get(name)
    return "" if value is None else str(value)


def _optional_text(row: Row, name: str) -> str | None:
    value = row.get(name)
    return None if value is None else str(value)


def _int(row: Row, name: str) -> int:
    value = row.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"expected integer column {name}, got {value!r}")
    return value


def _optional_int(row: Row, name: str) -> int | None:
    value = row.get(name)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def claim_key_from_row(row: Row) -> ClaimKey:
    return ClaimKey(
        id=_int(row, "id"),
        entity_id=_int(row, "entity_id"),
        key=_text(row, "key"),
        predicate=_text(row, "predicate"),
        question_id=_text(row, "question_id"),
    )


def assertion_from_row(row: Row) -> Assertion:
    residue = _optional_text(row, "residue_class")
    return Assertion(
        id=_int(row, "id"),
        proposition_id=_int(row, "proposition_id"),
        artifact_id=_int(row, "artifact_id"),
        doc_id=_text(row, "doc_id"),
        source_type=_text(row, "source_type"),
        evidence_span=_text(row, "evidence_span"),
        stance=Stance(_text(row, "stance")),
        extraction_method=ExtractionMethod(_text(row, "extraction_method")),
        structured=bool(row.get("structured")),
        discovery=Discovery(_text(row, "discovery") or Discovery.CONFLICT_PAIR),
        asserted_at=_optional_text(row, "asserted_at"),
        source_field=_optional_text(row, "source_field"),
        residue_class=ResidueClass(residue) if residue else None,
    )


def event_from_row(row: Row) -> CanonEvent:
    return CanonEvent(
        id=_int(row, "id"),
        claim_key_id=_int(row, "claim_key_id"),
        selects_proposition_id=_int(row, "selects_proposition_id"),
        supersedes_event_id=None,
        transition=Transition(_text(row, "transition")),
        temporal_quality=TemporalQuality(_text(row, "temporal_quality")),
        evidence_doc_id=_text(row, "evidence_doc_id"),
        occurred_at=_optional_text(row, "occurred_at"),
    )


class GraphReader:
    def __init__(self, client: HydraClient) -> None:
        self.client = client
        self.cards: list[HydraQueryCard] = []

    def _run(self, query: queries.NamedQuery, params: dict[str, Param]) -> tuple[Row, ...]:
        result = self.client.run(query, params)
        self.cards.append(card_for(result, params))
        return result.rows

    def cards_since(self, start: int) -> tuple[HydraQueryCard, ...]:
        return tuple(self.cards[start:])

    def take_cards(self) -> tuple[HydraQueryCard, ...]:
        cards = tuple(self.cards)
        self.cards.clear()
        return cards

    def claim_key(self, key: str) -> ClaimKey | None:
        rows = self._run(queries.CLAIM_KEY_BY_KEY, {"key": key})
        return claim_key_from_row(rows[0]) if rows else None

    def claim_keys_for_question(self, question_id: str) -> tuple[ClaimKey, ...]:
        rows = self._run(queries.CLAIM_KEYS_BY_QUESTION, {"question_id": question_id})
        return tuple(claim_key_from_row(row) for row in rows)

    def all_claim_keys(self, namespace: str = "canon") -> tuple[ClaimKey, ...]:
        rows = self._run(queries.ALL_CLAIM_KEYS, {})
        return tuple(
            claim_key_from_row(row) for row in rows if _text(row, "namespace") == namespace
        )

    def entity(self, claim_key_id: int) -> Entity | None:
        rows = self._run(queries.ENTITY_OF_CLAIM_KEY, {"claim_key_id": claim_key_id})
        if not rows:
            return None
        row = rows[0]
        return Entity(_int(row, "id"), _text(row, "name"), _text(row, "entity_type"))

    def propositions(self, claim_key_id: int) -> tuple[Proposition, ...]:
        rows = self._run(queries.CLAIM_PROPOSITIONS, {"claim_key_id": claim_key_id})
        return tuple(
            Proposition(
                _int(row, "id"),
                claim_key_id,
                _text(row, "value"),
                PropositionStatus(_text(row, "status")),
            )
            for row in rows
        )

    def events(self, claim_key_id: int) -> tuple[tuple[CanonEvent, int | None], ...]:
        rows = self._run(queries.CLAIM_EVENTS, {"claim_key_id": claim_key_id})
        return tuple((event_from_row(row), _optional_int(row, "superseded_by")) for row in rows)

    def supersession_chain(self, event_id: int) -> tuple[Row, ...]:
        return self._run(queries.SUPERSESSION_CHAIN, {"event_id": event_id})

    def evidence(self, proposition_id: int) -> tuple[EvidenceRow, ...]:
        rows = self._run(queries.PROPOSITION_ASSERTIONS, {"proposition_id": proposition_id})
        return tuple(EvidenceRow(assertion_from_row(row), _text(row, "title")) for row in rows)

    def residue(self, proposition_id: int) -> tuple[EvidenceRow, ...]:
        return tuple(
            row for row in self.evidence(proposition_id) if row.assertion.residue_class is not None
        )

    def artifact_claims(self, doc_id: str) -> tuple[ArtifactClaim, ...]:
        rows = self._run(queries.ARTIFACT_CLAIMS, {"doc_id": doc_id})
        claims: list[ArtifactClaim] = []
        for row in rows:
            residue = _optional_text(row, "residue_class")
            claims.append(
                ArtifactClaim(
                    assertion_id=_int(row, "assertion_id"),
                    claim_key_id=_int(row, "claim_key_id"),
                    key=_text(row, "key"),
                    proposition_id=_int(row, "proposition_id"),
                    value=_text(row, "value"),
                    status=PropositionStatus(_text(row, "status")),
                    stance=Stance(_text(row, "stance")),
                    residue_class=ResidueClass(residue) if residue else None,
                    evidence_span=_text(row, "evidence_span"),
                )
            )
        return tuple(claims)

    def proof_path(self, assertion_id: int) -> tuple[Row, ...]:
        return self._run(queries.PROOF_PATH, {"assertion_id": assertion_id})

    def resolve(self, claim_key: ClaimKey) -> Resolution:
        first_card = len(self.cards)
        entity = self.entity(claim_key.id)
        propositions = self.propositions(claim_key.id)
        by_id = {proposition.id: proposition for proposition in propositions}
        events = self.events(claim_key.id)
        current_events = [event for event, superseded_by in events if superseded_by is None]
        if not propositions:
            return self._resolution(
                claim_key, entity, TruthState.UNKNOWN, None, (), (), (), first_card
            )
        if len(current_events) != 1:
            contested = tuple(p for p in propositions if p.status is PropositionStatus.CONTESTED)
            return self._resolution(
                claim_key,
                entity,
                TruthState.CONTESTED,
                None,
                (),
                contested or propositions,
                (),
                first_card,
            )
        head = current_events[0]
        current = by_id[head.selects_proposition_id]
        chain = self.supersession_chain(head.id)
        retired = tuple(by_id[_int(row, "proposition_id")] for row in chain)
        ordered_events = tuple(_ordered_events(events, head))
        return self._resolution(
            claim_key, entity, TruthState.CANON, current, retired, (), ordered_events, first_card
        )

    def _resolution(
        self,
        claim_key: ClaimKey,
        entity: Entity | None,
        state: TruthState,
        current: Proposition | None,
        retired: tuple[Proposition, ...],
        contested: tuple[Proposition, ...],
        events: tuple[CanonEvent, ...],
        first_card: int,
    ) -> Resolution:
        current_evidence = self.evidence(current.id) if current else ()
        retired_evidence = tuple(row for p in retired for row in self.evidence(p.id))
        head = events[-1] if events else None
        return Resolution(
            claim_key=claim_key,
            entity=entity,
            state=state,
            temporal_quality=head.temporal_quality if head else TemporalQuality.T3,
            transition=head.transition if head else Transition.NONE,
            current=current,
            retired=retired,
            contested=contested,
            events=events,
            current_evidence=current_evidence,
            retired_evidence=retired_evidence,
            query_cards=self.cards_since(first_card),
        )


def _ordered_events(
    events: tuple[tuple[CanonEvent, int | None], ...], head: CanonEvent
) -> list[CanonEvent]:
    by_id = {event.id: event for event, _ in events}
    predecessor = {
        superseded_by: event.id for event, superseded_by in events if superseded_by is not None
    }
    ordered = [replace(head, supersedes_event_id=predecessor.get(head.id))]
    while ordered[0].supersedes_event_id is not None and len(ordered) <= len(events):
        older = by_id[ordered[0].supersedes_event_id]
        ordered.insert(0, replace(older, supersedes_event_id=predecessor.get(older.id)))
    return ordered
