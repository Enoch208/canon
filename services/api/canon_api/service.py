import json
import time
from pathlib import Path

from canon_api.cache import TimedCache
from canon_api.models import (
    AliasCandidateModel,
    AliasModel,
    AskResponse,
    CanonEventModel,
    ConflictSummaryModel,
    DashboardModel,
    EvidenceModel,
    GroundedDocModel,
    IdentityReportModel,
    OfficialEvalModel,
    QueryCardModel,
    ResidueReportModel,
    ResidueRowModel,
    TruthChangeModel,
)
from canon_api.stats import GraphStats, load_graph_stats
from canon_extraction.conflicts import ConflictInventory, load_inventory, split_claim_key
from canon_graph.grounding import Grounding, GroundingMode, ground
from canon_graph.hydra import HydraClient
from canon_graph.queries import (
    ALIASES_BY_RESOLUTION,
    COUNT_ALIASES_BY_RESOLUTION,
    PEOPLE_FOR_ALIAS,
)
from canon_graph.querycard import HydraQueryCard
from canon_graph.resolve import EvidenceRow, GraphReader, Resolution
from canon_graph.schema import CanonEvent, Discovery, EdgeType, NodeKind, ResidueClass, TruthState
from canon_retrieval.dataset import corpus_db_path
from canon_retrieval.store import CorpusStore

CANON_NAMESPACE = "canon"
GRAPH_STATS = Path("evidence") / "graph_stats.json"
CLAIM_NODE_KINDS = (
    NodeKind.ENTITY,
    NodeKind.CLAIM_KEY,
    NodeKind.PROPOSITION,
    NodeKind.ASSERTION,
    NodeKind.CANON_EVENT,
    NodeKind.ARTIFACT,
)
CLAIM_EDGE_TYPES = (
    EdgeType.HAS_CLAIM,
    EdgeType.HAS_VALUE,
    EdgeType.ASSERTS,
    EdgeType.IN_ARTIFACT,
    EdgeType.SELECTS,
    EdgeType.SUPERSEDES,
)
RESOLUTION_DEFINITIONS = {
    "RESOLVED": (
        "An email address bound to exactly one person by an explicit Name <email> line in a "
        "source document."
    ),
    "PROBABLE": (
        "A name spelling or email local part that maps to exactly one person, inferred from the "
        "bindings rather than stated directly."
    ),
    "AMBIGUOUS": (
        "The alias maps to more than one person, usually the same name at different "
        "organisations. Canon keeps them separate and never merges them."
    ),
}
IDENTITY_NOTE = (
    "Aliases are extracted from real Name <email> bindings in the corpus. The graph materialises a "
    "stratified sample, so the counts here are smaller than the corpus totals; both are reported."
)
RESIDUE_DEFINITIONS = {
    "VERIFIED_STRUCTURED": (
        "The retired value sits in a typed field line of a structured source (jira, linear, "
        "hubspot). Provable without a model. Zero on this corpus: retired values live in prose, "
        "not typed fields, so the count is reported as zero rather than loosened."
    ),
    "LEXICAL_RESTATEMENT": (
        "The retired value appears verbatim and the containing line carries no historical or "
        "rejected marker. Stance is not proven."
    ),
    "DERIVED_FREE_TEXT": (
        "A stance model judged the free text to assert the retired value as current. Requires an "
        "answer model; not run without credentials."
    ),
    "HISTORICAL_REFERENCE": "The line marks the value as previous, outdated, or original.",
    "REJECTED_REFERENCE": "The line states the value was changed, replaced, or is no longer used.",
    "NOT_AN_ASSERTION": "The matched line is a question, not a claim.",
}
RESURRECTION_NOTE = (
    "Verified structured resurrection requires a retired value reasserted in a structured field "
    "after a reliable supersession time. The EnterpriseRAG-Bench documents carry no metadata "
    "timestamps, so no candidate can be ordered against the supersession time and the verified "
    "count is 0."
)


class CanonService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.client = HydraClient.from_env()
        self.reader = GraphReader(self.client)
        self._stats: GraphStats | None = None
        self._dashboard_cache: TimedCache[DashboardModel] = TimedCache()
        self._conflicts_cache: TimedCache[list[ConflictSummaryModel]] = TimedCache()
        self._entities_cache: TimedCache[IdentityReportModel] = TimedCache()
        self._residue_cache: TimedCache[ResidueReportModel] = TimedCache()
        self.store = CorpusStore(corpus_db_path(root))
        self.inventory: ConflictInventory = load_inventory(
            root / "research" / "conflict_inventory.json"
        )

    def healthy(self) -> bool:
        return self.client.healthy()

    def _resolution_for(self, question_id: str) -> Resolution | None:
        keys = self.reader.claim_keys_for_question(question_id)
        return self.reader.resolve(keys[0]) if keys else None

    def _residue(self, resolution: Resolution) -> tuple[EvidenceRow, ...]:
        return tuple(
            row for proposition in resolution.retired for row in self.reader.residue(proposition.id)
        )

    def _graph_stats(self) -> GraphStats:
        if self._stats is None:
            self._stats = load_graph_stats(self.root / GRAPH_STATS)
        return self._stats

    def _conflict_pair_evidence(self, rows: tuple[EvidenceRow, ...]) -> tuple[EvidenceRow, ...]:
        return tuple(row for row in rows if row.assertion.discovery is Discovery.CONFLICT_PAIR)

    def dashboard(self) -> DashboardModel:
        return self._dashboard_cache.get(self._build_dashboard)

    def _build_dashboard(self) -> DashboardModel:
        claim_keys = self.reader.all_claim_keys()
        canon = 0
        contested = 0
        verified = 0
        derived = 0
        lexical = 0
        for claim_key in claim_keys:
            resolution = self.reader.resolve(claim_key)
            if resolution.state is TruthState.CANON:
                canon += 1
            elif resolution.state is TruthState.CONTESTED:
                contested += 1
            for row in self._residue(resolution):
                if row.assertion.residue_class is ResidueClass.VERIFIED_STRUCTURED:
                    verified += 1
                elif row.assertion.residue_class is ResidueClass.DERIVED_FREE_TEXT:
                    derived += 1
                elif row.assertion.residue_class is ResidueClass.LEXICAL_RESTATEMENT:
                    lexical += 1
        stats = self._graph_stats()
        self.reader.take_cards()
        return DashboardModel(
            corpus_documents=self.store.count(),
            claim_keys=len(claim_keys),
            current_conflicts=canon,
            contested_claims=contested,
            verified_residue=verified,
            derived_residue=derived,
            lexical_restatement_residue=lexical,
            verified_resurrections=0,
            resurrection_note=RESURRECTION_NOTE,
            graph_counts=stats.counts,
            graph_counts_measured_at=stats.measured_at,
        )

    def conflicts(self) -> list[ConflictSummaryModel]:
        return self._conflicts_cache.get(self._build_conflicts)

    def _build_conflicts(self) -> list[ConflictSummaryModel]:
        summaries: list[ConflictSummaryModel] = []
        for record in self.inventory.records:
            resolution = self._resolution_for(record.question_id)
            if resolution is None:
                continue
            residue = self._residue(resolution)
            entity, predicate = split_claim_key(record.claim_key)
            summaries.append(
                ConflictSummaryModel(
                    question_id=record.question_id,
                    claim_key=record.claim_key,
                    entity=entity,
                    predicate=predicate,
                    state=resolution.state,
                    current_value=resolution.current.value if resolution.current else None,
                    retired_values=[p.value for p in resolution.retired],
                    transition=resolution.transition,
                    temporal_quality=resolution.temporal_quality,
                    verified_structured_residue=_count(residue, ResidueClass.VERIFIED_STRUCTURED),
                    derived_free_text_residue=_count(residue, ResidueClass.DERIVED_FREE_TEXT),
                    lexical_restatement_residue=_count(residue, ResidueClass.LEXICAL_RESTATEMENT),
                )
            )
        self.reader.take_cards()
        return summaries

    def identity_report(self, per_state: int = 12) -> IdentityReportModel:
        return self._entities_cache.get(lambda: self._build_identity_report(per_state))

    def _build_identity_report(self, per_state: int) -> IdentityReportModel:
        evidence_file = self.root / "evidence" / "entities.json"
        corpus = json.loads(evidence_file.read_text()) if evidence_file.exists() else {}
        materialised: dict[str, int] = {}
        aliases: list[AliasModel] = []
        for state in ("RESOLVED", "PROBABLE", "AMBIGUOUS"):
            count = self.client.run(
                COUNT_ALIASES_BY_RESOLUTION, {"namespace": CANON_NAMESPACE, "resolution": state}
            )
            materialised[state] = int(count.scalar() or 0)
            rows = self.client.run(
                ALIASES_BY_RESOLUTION,
                {"namespace": CANON_NAMESPACE, "resolution": state, "limit": per_state},
            )
            for row in rows.rows:
                people = self.client.run(PEOPLE_FOR_ALIAS, {"alias_id": row["id"]})
                aliases.append(
                    AliasModel(
                        value=str(row["value"]),
                        alias_type=str(row["alias_type"]),
                        resolution=str(row["resolution"]),
                        support=int(row["support"] or 0),
                        candidate_count=int(row["candidate_count"] or 0),
                        candidates=[
                            AliasCandidateModel(
                                name=str(p["name"]), organization=str(p["organization"])
                            )
                            for p in people.rows
                        ],
                        evidence_doc_id=str(row["evidence_doc_id"]),
                        evidence_span=str(row["evidence_span"]),
                    )
                )
        return IdentityReportModel(
            definition=RESOLUTION_DEFINITIONS,
            corpus={
                "documents_scanned": int(corpus.get("documents_scanned", 0)),
                "bindings_found": int(corpus.get("bindings_found", 0)),
                "people": int(corpus.get("people", 0)),
                "aliases": int(corpus.get("aliases", 0)),
            },
            materialised=materialised,
            note=IDENTITY_NOTE,
            aliases=aliases,
        )

    def official_eval(self) -> OfficialEvalModel | None:
        path = self.root / "evidence" / "official_eval.json"
        if not path.exists():
            return None
        return OfficialEvalModel.model_validate_json(path.read_text())

    def residue_report(self) -> ResidueReportModel:
        return self._residue_cache.get(self._build_residue_report)

    def _build_residue_report(self) -> ResidueReportModel:
        rows: list[ResidueRowModel] = []
        for record in self.inventory.records:
            resolution = self._resolution_for(record.question_id)
            if resolution is None:
                continue
            entity, _ = split_claim_key(record.claim_key)
            for row in self._residue(resolution):
                assertion = row.assertion
                if assertion.residue_class is None:
                    continue
                rows.append(
                    ResidueRowModel(
                        question_id=record.question_id,
                        claim_key=record.claim_key,
                        entity=entity,
                        retired_value=record.old_value,
                        current_value=resolution.current.value if resolution.current else None,
                        residue_class=assertion.residue_class,
                        discovery=str(assertion.discovery),
                        doc_id=assertion.doc_id,
                        source_type=assertion.source_type,
                        title=row.title,
                        evidence_span=assertion.evidence_span,
                        source_field=assertion.source_field,
                    )
                )
        self.reader.take_cards()
        counts = {
            str(residue_class): sum(1 for row in rows if row.residue_class is residue_class)
            for residue_class in ResidueClass
        }
        return ResidueReportModel(definition=RESIDUE_DEFINITIONS, counts=counts, rows=rows)

    def truth_change(self, question_id: str) -> TruthChangeModel | None:
        first_card = len(self.reader.cards)
        resolution = self._resolution_for(question_id)
        if resolution is None:
            return None
        residue = self._residue(resolution)
        entity, predicate = split_claim_key(resolution.claim_key.key)
        model = TruthChangeModel(
            question_id=question_id,
            claim_key=resolution.claim_key.key,
            entity=entity,
            predicate=predicate,
            state=resolution.state,
            current_value=resolution.current.value if resolution.current else None,
            retired_values=[p.value for p in resolution.retired],
            contested_values=[p.value for p in resolution.contested],
            transition=resolution.transition,
            temporal_quality=resolution.temporal_quality,
            events=[_event(event, resolution) for event in resolution.events],
            current_evidence=[
                _evidence(row) for row in self._conflict_pair_evidence(resolution.current_evidence)
            ],
            retired_evidence=[
                _evidence(row) for row in self._conflict_pair_evidence(resolution.retired_evidence)
            ],
            residue=[_evidence(row) for row in residue],
            query_cards=[_card(card) for card in self.reader.cards_since(first_card)],
        )
        self.reader.take_cards()
        return model

    def ask(self, question: str, mode: GroundingMode, top_k: int) -> AskResponse:
        started = time.perf_counter()
        hits = self.store.search(question, k=top_k)
        retrieval_ms = (time.perf_counter() - started) * 1000
        ranks = {hit.doc_id: hit.rank for hit in hits}
        started = time.perf_counter()
        grounding = ground(
            self.reader,
            question,
            tuple(hit.doc_id for hit in hits),
            mode=mode,
            pin_graph_evidence=True,
        )
        grounding_ms = (time.perf_counter() - started) * 1000
        self.reader.take_cards()
        return _ask_response(
            question, mode, grounding, ranks, self.store, retrieval_ms, grounding_ms
        )


def _count(rows: tuple[EvidenceRow, ...], residue_class: ResidueClass) -> int:
    return sum(1 for row in rows if row.assertion.residue_class is residue_class)


def _evidence(row: EvidenceRow) -> EvidenceModel:
    assertion = row.assertion
    return EvidenceModel(
        doc_id=assertion.doc_id,
        discovery=str(assertion.discovery),
        source_type=assertion.source_type,
        title=row.title,
        evidence_span=assertion.evidence_span,
        stance=str(assertion.stance),
        structured=assertion.structured,
        source_field=assertion.source_field,
        asserted_at=assertion.asserted_at,
        residue_class=assertion.residue_class,
    )


def _event(event: CanonEvent, resolution: Resolution) -> CanonEventModel:
    values = {
        p.id: p.value
        for p in (*resolution.retired, *([resolution.current] if resolution.current else []))
    }
    return CanonEventModel(
        id=event.id,
        selects_value=values.get(event.selects_proposition_id, ""),
        supersedes_event_id=event.supersedes_event_id,
        transition=event.transition,
        temporal_quality=event.temporal_quality,
        evidence_doc_id=event.evidence_doc_id,
        occurred_at=event.occurred_at,
    )


def _card(card: HydraQueryCard) -> QueryCardModel:
    return QueryCardModel(**card.as_dict())


def _ask_response(
    question: str,
    mode: GroundingMode,
    grounding: Grounding,
    ranks: dict[str, int],
    store: CorpusStore,
    retrieval_ms: float,
    grounding_ms: float,
) -> AskResponse:
    primary = grounding.primary
    kept = set(grounding.kept_doc_ids)
    documents: list[GroundedDocModel] = []
    for doc in grounding.docs:
        document = store.document(doc.doc_id)
        documents.append(
            GroundedDocModel(
                doc_id=doc.doc_id,
                source_type=document.source_type if document else "",
                title=document.title if document else "",
                disposition=doc.disposition,
                rank=ranks.get(doc.doc_id),
                kept=doc.doc_id in kept,
            )
        )
    evidence: tuple[EvidenceRow, ...] = ()
    answer_value: str | None = None
    why = "No claim in the graph matches this question; Canon returns UNKNOWN."
    if primary is not None and primary.state is TruthState.CANON:
        historical = mode is GroundingMode.HISTORICAL
        evidence = primary.retired_evidence if historical else primary.current_evidence
        answer_value = (
            primary.retired[-1].value
            if historical and primary.retired
            else (primary.current.value if primary.current else None)
        )
        retired = ", ".join(p.value for p in primary.retired)
        why = (
            f"{primary.transition} of {retired} recorded in the claim graph "
            f"(temporal quality {primary.temporal_quality})."
        )
    elif primary is not None and primary.state is TruthState.CONTESTED:
        why = (
            "Multiple values conflict and no supersession or reliable ordering establishes "
            "which one is current."
        )
        evidence = primary.current_evidence + primary.retired_evidence
    return AskResponse(
        question=question,
        mode=mode,
        state=grounding.state,
        answer_value=answer_value,
        why=why,
        claim_key=primary.claim_key.key if primary else None,
        temporal_quality=primary.temporal_quality if primary else None,
        transition=primary.transition if primary else None,
        evidence=[
            _evidence(row) for row in evidence if row.assertion.discovery is Discovery.CONFLICT_PAIR
        ],
        retired_evidence_filtered=len(grounding.dropped_doc_ids),
        documents=documents,
        query_cards=[_card(card) for card in grounding.query_cards],
        retrieval_ms=round(retrieval_ms, 2),
        grounding_ms=round(grounding_ms, 2),
    )
