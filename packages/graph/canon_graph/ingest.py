from collections.abc import Sequence
from dataclasses import dataclass, field

from canon_graph import ids, queries
from canon_graph.canonize import AssertionInput, CanonDecision, ClaimBundle
from canon_graph.hydra import HydraClient, HydraError, Param
from canon_graph.schema import (
    Discovery,
    EdgeType,
    NodeKind,
    PropositionStatus,
    ResidueClass,
    TruthState,
)

BATCH_LIMIT = 1024
MAX_ALIAS_CANDIDATES = 12


@dataclass(slots=True)
class WriteReport:
    nodes_created: int = 0
    edges_created: int = 0
    skipped_existing: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)

    def created(self, kind: NodeKind, edges: int = 1) -> None:
        self.nodes_created += 1
        self.edges_created += edges
        self.by_kind[kind] = self.by_kind.get(kind, 0) + 1


class GraphWriter:
    def __init__(self, client: HydraClient, namespace: ids.Namespace = ids.Namespace.CANON) -> None:
        self.client = client
        self.namespace = namespace
        self.report = WriteReport()

    def delete_nodes(self, node_ids: Sequence[int], batch_size: int = BATCH_LIMIT) -> int:
        deleted = 0
        start = 0
        size = min(batch_size, BATCH_LIMIT)
        while start < len(node_ids):
            batch = node_ids[start : start + size]
            try:
                self.client.run(
                    queries.UNWIND_DELETE_NODES, {"rows": [{"id": value} for value in batch]}
                )
            except HydraError as error:
                if error.code != "query_timeout" or size == 1:
                    raise
                size = max(1, size // 4)
                continue
            deleted += len(batch)
            start += len(batch)
        return deleted

    def delete_edges(self, edge: EdgeType, pairs: Sequence[tuple[int, int]]) -> int:
        query = queries.unwind_delete_edges(edge)
        deleted = 0
        for start in range(0, len(pairs), BATCH_LIMIT):
            batch = pairs[start : start + BATCH_LIMIT]
            self.client.run(
                query, {"rows": [{"s": source, "t": target} for source, target in batch]}
            )
            deleted += len(batch)
        return deleted

    def purge_namespace(self) -> int:
        deleted = 0
        for kind in NodeKind:
            result = self.client.run(
                queries.ids_by_namespace(kind), {"namespace": self.namespace.name.lower()}
            )
            ids = [value for value in result.column("id") if isinstance(value, int)]
            deleted += self.delete_nodes(ids)
        return deleted

    def exists(self, node_id: int) -> bool:
        result = self.client.run(queries.NODE_KIND, {"id": node_id})
        return result.scalar() is not None

    def edge_exists(self, source_id: int, edge: EdgeType, target_id: int) -> bool:
        result = self.client.run(
            queries.edge_exists(edge), {"source_id": source_id, "target_id": target_id}
        )
        return bool(result.scalar())

    def _base(self, kind: NodeKind, node_id: int) -> dict[str, Param]:
        return {"id": node_id, "kind": str(kind), "namespace": self.namespace.name.lower()}

    def _create_child(
        self,
        parent_kind: NodeKind,
        parent_id: int,
        edge: EdgeType,
        child_kind: NodeKind,
        child_props: dict[str, Param],
    ) -> bool:
        child_id = int(child_props["id"])
        if self.exists(child_id):
            self.report.skipped_existing += 1
            if not self.edge_exists(parent_id, edge, child_id):
                self.link(parent_kind, parent_id, edge, child_kind, child_id)
            return False
        names = tuple(name for name in child_props if name != "id")
        query = queries.create_child(parent_kind, edge, child_kind, names)
        self.client.run(query, {"parent_id": parent_id, **child_props})
        self.report.created(child_kind)
        return True

    def _create_source(
        self,
        source_kind: NodeKind,
        source_props: dict[str, Param],
        edge: EdgeType,
        target_kind: NodeKind,
        target_id: int,
    ) -> bool:
        source_id = int(source_props["id"])
        if self.exists(source_id):
            self.report.skipped_existing += 1
            if not self.edge_exists(source_id, edge, target_id):
                self.link(source_kind, source_id, edge, target_kind, target_id)
            return False
        names = tuple(name for name in source_props if name != "id")
        query = queries.create_source(source_kind, names, edge, target_kind)
        self.client.run(query, {"target_id": target_id, **source_props})
        self.report.created(source_kind)
        return True

    def link(
        self,
        source_kind: NodeKind,
        source_id: int,
        edge: EdgeType,
        target_kind: NodeKind,
        target_id: int,
    ) -> bool:
        if self.edge_exists(source_id, edge, target_id):
            return False
        self.client.run(
            queries.link(source_kind, edge, target_kind),
            {"source_id": source_id, "target_id": target_id},
        )
        self.report.edges_created += 1
        return True

    def write_entity_and_claim_key(self, bundle: ClaimBundle) -> tuple[int, int]:
        entity_id = ids.entity_id(bundle.entity_name, self.namespace)
        claim_key_id = ids.claim_key_id(bundle.key, self.namespace)
        claim_props: dict[str, Param] = {
            **self._base(NodeKind.CLAIM_KEY, claim_key_id),
            "entity_id": entity_id,
            "key": bundle.key,
            "predicate": bundle.predicate,
            "question_id": bundle.question_id,
        }
        if self.exists(entity_id):
            self._create_child(
                NodeKind.ENTITY, entity_id, EdgeType.HAS_CLAIM, NodeKind.CLAIM_KEY, claim_props
            )
            return entity_id, claim_key_id
        if self.exists(claim_key_id):
            self.report.skipped_existing += 1
            return entity_id, claim_key_id
        entity_props = {
            **self._base(NodeKind.ENTITY, entity_id),
            "name": bundle.entity_name,
            "entity_type": bundle.entity_type,
        }
        query = queries.create_parent_with_child(
            NodeKind.ENTITY,
            tuple(name for name in entity_props if name != "id"),
            EdgeType.HAS_CLAIM,
            NodeKind.CLAIM_KEY,
            tuple(name for name in claim_props if name != "id"),
        )
        params: dict[str, Param] = {f"parent_{name}": value for name, value in entity_props.items()}
        params.update(claim_props)
        self.client.run(query, params)
        self.report.created(NodeKind.ENTITY, edges=0)
        self.report.created(NodeKind.CLAIM_KEY)
        return entity_id, claim_key_id

    def write_proposition(
        self, claim_key_id: int, key: str, value: str, status: PropositionStatus
    ) -> int:
        proposition_id = ids.proposition_id(key, value, self.namespace)
        props: dict[str, Param] = {
            **self._base(NodeKind.PROPOSITION, proposition_id),
            "claim_key_id": claim_key_id,
            "value": value,
            "status": str(status),
        }
        if not self._create_child(
            NodeKind.CLAIM_KEY, claim_key_id, EdgeType.HAS_VALUE, NodeKind.PROPOSITION, props
        ):
            self.client.run(
                queries.set_property(NodeKind.PROPOSITION, "status"),
                {"id": proposition_id, "value": str(status)},
            )
        return proposition_id

    def write_assertion(
        self,
        key: str,
        proposition_id: int,
        assertion: AssertionInput,
        title: str,
        residue_class: ResidueClass | None = None,
        discovery: Discovery = Discovery.CONFLICT_PAIR,
    ) -> int:
        artifact_id = ids.artifact_id(assertion.doc_id, self.namespace)
        assertion_id = ids.assertion_id(
            key, assertion.value, assertion.doc_id, assertion.evidence_span, self.namespace
        )
        props: dict[str, Param] = {
            **self._base(NodeKind.ASSERTION, assertion_id),
            "proposition_id": proposition_id,
            "artifact_id": artifact_id,
            "doc_id": assertion.doc_id,
            "source_type": assertion.source_type,
            "evidence_span": assertion.evidence_span,
            "stance": str(assertion.stance),
            "extraction_method": str(assertion.extraction_method),
            "structured": assertion.structured,
            "discovery": str(discovery),
        }
        if assertion.asserted_at is not None:
            props["asserted_at"] = assertion.asserted_at
        if assertion.source_field is not None:
            props["source_field"] = assertion.source_field
        if residue_class is not None:
            props["residue_class"] = str(residue_class)
        created = self._create_source(
            NodeKind.ASSERTION, props, EdgeType.ASSERTS, NodeKind.PROPOSITION, proposition_id
        )
        if created:
            self._attach_artifact(assertion_id, artifact_id, assertion, title)
        return assertion_id

    def _attach_artifact(
        self, assertion_id: int, artifact_id: int, assertion: AssertionInput, title: str
    ) -> None:
        artifact_props: dict[str, Param] = {
            **self._base(NodeKind.ARTIFACT, artifact_id),
            "doc_id": assertion.doc_id,
            "source_type": assertion.source_type,
            "title": title,
        }
        self._create_child(
            NodeKind.ASSERTION,
            assertion_id,
            EdgeType.IN_ARTIFACT,
            NodeKind.ARTIFACT,
            artifact_props,
        )

    def write_events(
        self, bundle: ClaimBundle, decision: CanonDecision, claim_key_id: int
    ) -> list[int]:
        event_ids: list[int] = []
        previous_event: int | None = None
        for plan in decision.events:
            proposition_id = ids.proposition_id(bundle.key, plan.value, self.namespace)
            event_id = ids.canon_event_id(
                bundle.key, plan.value, plan.evidence_doc_id, self.namespace
            )
            props: dict[str, Param] = {
                **self._base(NodeKind.CANON_EVENT, event_id),
                "claim_key_id": claim_key_id,
                "selects_proposition_id": proposition_id,
                "transition": str(decision.transition),
                "temporal_quality": str(decision.temporal_quality),
                "evidence_doc_id": plan.evidence_doc_id,
            }
            if plan.occurred_at is not None:
                props["occurred_at"] = plan.occurred_at
            self._create_source(
                NodeKind.CANON_EVENT, props, EdgeType.SELECTS, NodeKind.PROPOSITION, proposition_id
            )
            if previous_event is not None:
                self.link(
                    NodeKind.CANON_EVENT,
                    event_id,
                    EdgeType.SUPERSEDES,
                    NodeKind.CANON_EVENT,
                    previous_event,
                )
            event_ids.append(event_id)
            previous_event = event_id
        return event_ids

    def write_identity(
        self,
        alias_value: str,
        alias_type: str,
        resolution: str,
        support: int,
        evidence_doc_id: str,
        evidence_span: str,
        people: Sequence[tuple[str, str, str]],
    ) -> int:
        alias_node = ids.alias_id(alias_value, alias_type, self.namespace)
        alias_props: dict[str, Param] = {
            **self._base(NodeKind.ALIAS, alias_node),
            "value": alias_value,
            "alias_type": alias_type,
            "resolution": resolution,
            "support": support,
            "candidate_count": len(people),
            "evidence_doc_id": evidence_doc_id,
            "evidence_span": evidence_span,
        }
        for key, name, organization in people[:MAX_ALIAS_CANDIDATES]:
            person_node = ids.person_id(key, self.namespace)
            person_props: dict[str, Param] = {
                **self._base(NodeKind.PERSON, person_node),
                "name": name,
                "organization": organization,
                "person_key": key,
            }
            if self.exists(person_node):
                self.report.skipped_existing += 1
            if self.exists(alias_node):
                self.report.skipped_existing += 1
                if not self.edge_exists(alias_node, EdgeType.RESOLVES_TO, person_node):
                    self._create_child(
                        NodeKind.ALIAS,
                        alias_node,
                        EdgeType.RESOLVES_TO,
                        NodeKind.PERSON,
                        person_props,
                    )
                continue
            query = queries.create_parent_with_child(
                NodeKind.ALIAS,
                tuple(name for name in alias_props if name != "id"),
                EdgeType.RESOLVES_TO,
                NodeKind.PERSON,
                tuple(name for name in person_props if name != "id"),
            )
            params: dict[str, Param] = {
                f"parent_{key_name}": value for key_name, value in alias_props.items()
            }
            params.update(person_props)
            self.client.run(query, params)
            self.report.created(NodeKind.ALIAS, edges=0)
            self.report.created(NodeKind.PERSON)
        return alias_node

    def write_claim(
        self,
        bundle: ClaimBundle,
        decision: CanonDecision,
        titles: dict[str, str],
        residue_classes: dict[str, ResidueClass] | None = None,
    ) -> tuple[int, dict[str, int]]:
        _, claim_key_id = self.write_entity_and_claim_key(bundle)
        proposition_ids: dict[str, int] = {}
        for value in _all_values(bundle):
            status = proposition_status(decision, value)
            proposition_ids[value] = self.write_proposition(claim_key_id, bundle.key, value, status)
        classes = residue_classes or {}
        for assertion in bundle.assertions:
            self.write_assertion(
                bundle.key,
                proposition_ids[assertion.value],
                assertion,
                titles.get(assertion.doc_id, ""),
                classes.get(assertion.doc_id),
            )
        self.write_events(bundle, decision, claim_key_id)
        return claim_key_id, proposition_ids


def proposition_status(decision: CanonDecision, value: str) -> PropositionStatus:
    if decision.state is TruthState.CANON:
        if value == decision.current_value:
            return PropositionStatus.CURRENT
        if value in decision.retired_values:
            return PropositionStatus.RETIRED
        return PropositionStatus.UNRESOLVED
    if decision.state is TruthState.CONTESTED and value in decision.contested_values:
        return PropositionStatus.CONTESTED
    return PropositionStatus.UNRESOLVED


def _all_values(bundle: ClaimBundle) -> tuple[str, ...]:
    ordered: dict[str, None] = {}
    for assertion in bundle.assertions:
        ordered.setdefault(assertion.value, None)
    return tuple(ordered)
