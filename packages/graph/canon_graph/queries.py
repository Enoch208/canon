from canon_graph.hydra import NamedQuery
from canon_graph.schema import EDGE_ENDPOINTS, EdgeType, NodeKind

ASSERTION_FIELDS = (
    "a.id AS id",
    "a.doc_id AS doc_id",
    "a.source_type AS source_type",
    "a.evidence_span AS evidence_span",
    "a.stance AS stance",
    "a.extraction_method AS extraction_method",
    "a.structured AS structured",
    "a.discovery AS discovery",
    "a.asserted_at AS asserted_at",
    "a.source_field AS source_field",
    "a.residue_class AS residue_class",
    "a.proposition_id AS proposition_id",
    "a.artifact_id AS artifact_id",
)

EVENT_FIELDS = (
    "ev.id AS id",
    "ev.claim_key_id AS claim_key_id",
    "ev.selects_proposition_id AS selects_proposition_id",
    "ev.transition AS transition",
    "ev.temporal_quality AS temporal_quality",
    "ev.evidence_doc_id AS evidence_doc_id",
    "ev.occurred_at AS occurred_at",
)


def _returns(fields: tuple[str, ...]) -> str:
    return ", ".join(fields)


def create_child(
    parent_kind: NodeKind, edge: EdgeType, child_kind: NodeKind, child_props: tuple[str, ...]
) -> NamedQuery:
    props = ", ".join(f"{name}: ${name}" for name in ("id", *child_props))
    return NamedQuery(
        name=f"create_{child_kind.lower()}_via_{edge.lower()}",
        operation=f"CREATE {parent_kind} -{edge}-> {child_kind}",
        cypher=(
            f"CREATE (parent:{parent_kind} {{id: $parent_id}})"
            f"-[:{edge}]->(child:{child_kind} {{{props}}})"
        ),
    )


def create_parent_with_child(
    parent_kind: NodeKind,
    parent_props: tuple[str, ...],
    edge: EdgeType,
    child_kind: NodeKind,
    child_props: tuple[str, ...],
) -> NamedQuery:
    parent = ", ".join(f"{name}: $parent_{name}" for name in ("id", *parent_props))
    child = ", ".join(f"{name}: ${name}" for name in ("id", *child_props))
    return NamedQuery(
        name=f"create_{parent_kind.lower()}_and_{child_kind.lower()}",
        operation=f"CREATE {parent_kind} -{edge}-> {child_kind}",
        cypher=(
            f"CREATE (parent:{parent_kind} {{{parent}}})"
            f"-[:{edge}]->(child:{child_kind} {{{child}}})"
        ),
    )


def create_source(
    source_kind: NodeKind, source_props: tuple[str, ...], edge: EdgeType, target_kind: NodeKind
) -> NamedQuery:
    props = ", ".join(f"{name}: ${name}" for name in ("id", *source_props))
    return NamedQuery(
        name=f"create_{source_kind.lower()}_via_{edge.lower()}",
        operation=f"CREATE {source_kind} -{edge}-> {target_kind}",
        cypher=(
            f"CREATE (source:{source_kind} {{{props}}})"
            f"-[:{edge}]->(target:{target_kind} {{id: $target_id}})"
        ),
    )


def link(source_kind: NodeKind, edge: EdgeType, target_kind: NodeKind) -> NamedQuery:
    return NamedQuery(
        name=f"link_{edge.lower()}",
        operation=f"CREATE {source_kind} -{edge}-> {target_kind}",
        cypher=(
            f"CREATE (source:{source_kind} {{id: $source_id}})"
            f"-[:{edge}]->(target:{target_kind} {{id: $target_id}})"
        ),
    )


def edge_exists(edge: EdgeType) -> NamedQuery:
    return NamedQuery(
        name=f"edge_exists_{edge.lower()}",
        operation=f"MATCH -{edge}-> count",
        cypher=(
            f"MATCH (a {{id: $source_id}})-[:{edge}]->(b {{id: $target_id}}) RETURN count(*) AS n"
        ),
    )


def count_nodes(kind: NodeKind) -> NamedQuery:
    return NamedQuery(
        name=f"count_{kind.lower()}",
        operation=f"MATCH (:{kind}) count",
        cypher=f"MATCH (n:{kind}) RETURN count(*) AS n",
    )


def count_nodes_in_namespace(kind: NodeKind) -> NamedQuery:
    return NamedQuery(
        name=f"count_{kind.lower()}_in_namespace",
        operation=f"MATCH (:{kind}) count in namespace",
        cypher=f"MATCH (n:{kind} {{namespace: $namespace}}) RETURN count(*) AS n",
    )


def namespaces_of(kind: NodeKind) -> NamedQuery:
    return NamedQuery(
        name=f"namespaces_of_{kind.lower()}",
        operation=f"MATCH (:{kind}) namespaces",
        cypher=f"MATCH (n:{kind}) RETURN n.namespace AS namespace",
    )


def count_edges_in_namespace(edge: EdgeType) -> NamedQuery:
    source, target = EDGE_ENDPOINTS[edge]
    return NamedQuery(
        name=f"count_{edge.lower()}_in_namespace",
        operation=f"MATCH (:{source})-[:{edge}]->(:{target}) count in namespace",
        cypher=(
            f"MATCH (a:{source} {{namespace: $namespace}})-[:{edge}]->(b:{target}) "
            "RETURN count(*) AS n"
        ),
    )


def set_property(kind: NodeKind, prop: str) -> NamedQuery:
    return NamedQuery(
        name=f"set_{kind.lower()}_{prop}",
        operation=f"SET {kind}.{prop}",
        cypher=f"MATCH (n:{kind} {{id: $id}}) SET n.{prop} = $value",
    )


def ids_by_namespace(kind: NodeKind) -> NamedQuery:
    return NamedQuery(
        name=f"ids_{kind.lower()}_by_namespace",
        operation=f"MATCH (:{kind}) ids where namespace",
        cypher=f"MATCH (n:{kind} {{namespace: $namespace}}) RETURN n.id AS id",
    )


def unwind_delete_edges(edge: EdgeType) -> NamedQuery:
    return NamedQuery(
        name=f"unwind_delete_{edge.lower()}",
        operation=f"UNWIND batch DELETE -{edge}->",
        cypher=(
            f"UNWIND $rows AS row MATCH (a {{id: row.s}})-[r:{edge}]->(b {{id: row.t}}) DELETE r"
        ),
    )


UNWIND_DELETE_NODES = NamedQuery(
    name="unwind_delete_nodes",
    operation="UNWIND batch DETACH DELETE",
    cypher="UNWIND $rows AS row MATCH (n {id: row.id}) DETACH DELETE n",
)


def unwind_create_edges(edge: EdgeType) -> NamedQuery:
    return NamedQuery(
        name=f"unwind_create_{edge.lower()}",
        operation=f"UNWIND batch CREATE -{edge}->",
        cypher=f"UNWIND $rows AS row CREATE (a {{id: row.s}})-[:{edge}]->(b {{id: row.t}})",
    )


DETACH_DELETE_BY_ID = NamedQuery(
    name="detach_delete_by_id",
    operation="DETACH DELETE by id",
    cypher="MATCH (n {id: $id}) DETACH DELETE n",
)


NODE_KIND = NamedQuery(
    name="node_kind",
    operation="MATCH by id",
    cypher="MATCH (n {id: $id}) RETURN n.kind AS kind",
)

CLAIM_KEY_BY_KEY = NamedQuery(
    name="claim_key_by_key",
    operation="MATCH ClaimKey by key",
    cypher=(
        "MATCH (c:ClaimKey {key: $key}) "
        "RETURN c.id AS id, c.entity_id AS entity_id, c.key AS key, "
        "c.predicate AS predicate, c.question_id AS question_id"
    ),
)

CLAIM_KEYS_BY_QUESTION = NamedQuery(
    name="claim_keys_by_question",
    operation="MATCH ClaimKey by question_id",
    cypher=(
        "MATCH (c:ClaimKey {question_id: $question_id}) "
        "RETURN c.id AS id, c.entity_id AS entity_id, c.key AS key, "
        "c.predicate AS predicate, c.question_id AS question_id"
    ),
)

ALL_CLAIM_KEYS = NamedQuery(
    name="all_claim_keys",
    operation="MATCH ClaimKey by label",
    cypher=(
        "MATCH (c:ClaimKey) "
        "RETURN c.id AS id, c.entity_id AS entity_id, c.key AS key, c.predicate AS predicate, "
        "c.question_id AS question_id, c.namespace AS namespace ORDER BY c.key"
    ),
)

ENTITY_OF_CLAIM_KEY = NamedQuery(
    name="entity_of_claim_key",
    operation="MATCH Entity -HAS_CLAIM-> ClaimKey",
    cypher=(
        "MATCH (e:Entity)-[:HAS_CLAIM]->(c:ClaimKey {id: $claim_key_id}) "
        "RETURN e.id AS id, e.name AS name, e.entity_type AS entity_type"
    ),
)

CLAIM_PROPOSITIONS = NamedQuery(
    name="claim_neighborhood",
    operation="Claim neighborhood: ClaimKey -HAS_VALUE-> Proposition",
    cypher=(
        "MATCH (c:ClaimKey {id: $claim_key_id})-[:HAS_VALUE]->(p:Proposition) "
        "RETURN p.id AS id, p.value AS value, p.status AS status ORDER BY p.id"
    ),
)

CLAIM_EVENTS = NamedQuery(
    name="claim_events",
    operation="Canon events: ClaimKey -HAS_VALUE-> Proposition <-SELECTS- CanonEvent",
    cypher=(
        "MATCH (c:ClaimKey {id: $claim_key_id})-[:HAS_VALUE]->(p:Proposition)"
        "<-[:SELECTS]-(ev:CanonEvent) "
        "OPTIONAL MATCH (newer:CanonEvent)-[:SUPERSEDES]->(ev) "
        f"RETURN {_returns(EVENT_FIELDS)}, p.id AS proposition_id, newer.id AS superseded_by"
    ),
)

SUPERSESSION_CHAIN = NamedQuery(
    name="supersession_chain",
    operation=(
        "Supersession lineage: CanonEvent -SUPERSEDES*1..10-> CanonEvent -SELECTS-> Proposition"
    ),
    cypher=(
        "MATCH (ev:CanonEvent {id: $event_id})-[:SUPERSEDES*1..10]->(old:CanonEvent)"
        "-[:SELECTS]->(p:Proposition) "
        "RETURN old.id AS id, old.transition AS transition, "
        "old.temporal_quality AS temporal_quality, "
        "old.evidence_doc_id AS evidence_doc_id, old.occurred_at AS occurred_at, "
        "p.id AS proposition_id, p.value AS value"
    ),
)

PROPOSITION_ASSERTIONS = NamedQuery(
    name="residue_reverse_traversal",
    operation="Reverse traversal: Proposition <-ASSERTS- Assertion -IN_ARTIFACT-> Artifact",
    cypher=(
        "MATCH (p:Proposition {id: $proposition_id})<-[:ASSERTS]-(a:Assertion)"
        "-[:IN_ARTIFACT]->(d:Artifact) "
        f"RETURN {_returns(ASSERTION_FIELDS)}, d.title AS title ORDER BY a.doc_id"
    ),
)

ARTIFACT_CLAIMS = NamedQuery(
    name="artifact_claims",
    operation=(
        "Grounding: Artifact <-IN_ARTIFACT- Assertion -ASSERTS-> Proposition <-HAS_VALUE- ClaimKey"
    ),
    cypher=(
        "MATCH (d:Artifact {doc_id: $doc_id})<-[:IN_ARTIFACT]-(a:Assertion)-[:ASSERTS]->"
        "(p:Proposition)<-[:HAS_VALUE]-(c:ClaimKey) "
        "RETURN a.id AS assertion_id, a.stance AS stance, a.residue_class AS residue_class, "
        "a.evidence_span AS evidence_span, p.id AS proposition_id, p.value AS value, "
        "p.status AS status, c.id AS claim_key_id, c.key AS key"
    ),
)

ARTIFACT_BY_DOC = NamedQuery(
    name="artifact_by_doc",
    operation="MATCH Artifact by doc_id",
    cypher=(
        "MATCH (d:Artifact {doc_id: $doc_id}) "
        "RETURN d.id AS id, d.doc_id AS doc_id, d.source_type AS source_type, d.title AS title"
    ),
)

PROOF_PATH = NamedQuery(
    name="proof_path",
    operation=(
        "Proof traversal: Assertion -ASSERTS-> retired Proposition <-SELECTS- CanonEvent "
        "<-SUPERSEDES- CanonEvent -SELECTS-> current Proposition"
    ),
    cypher=(
        "MATCH (a:Assertion {id: $assertion_id})-[:ASSERTS]->(retired:Proposition)"
        "<-[:SELECTS]-(old:CanonEvent)<-[:SUPERSEDES]-(new:CanonEvent)-[:SELECTS]->"
        "(current:Proposition) "
        "RETURN retired.id AS retired_id, retired.value AS retired_value, old.id AS old_event_id, "
        "new.id AS new_event_id, new.transition AS transition, "
        "new.temporal_quality AS temporal_quality, new.evidence_doc_id AS evidence_doc_id, "
        "current.id AS current_id, current.value AS current_value"
    ),
)

ALIASES_FOR_PERSON = NamedQuery(
    name="aliases_for_person",
    operation="Entity path: Alias -RESOLVES_TO-> Person",
    cypher=(
        "MATCH (a:Alias)-[:RESOLVES_TO]->(p:Person {id: $person_id}) "
        "RETURN a.value AS value, a.alias_type AS alias_type, a.resolution AS resolution, "
        "a.support AS support, a.evidence_doc_id AS evidence_doc_id, "
        "a.evidence_span AS evidence_span"
    ),
)

PEOPLE_FOR_ALIAS = NamedQuery(
    name="people_for_alias",
    operation="Entity path: Alias -RESOLVES_TO-> Person (candidates)",
    cypher=(
        "MATCH (a:Alias {id: $alias_id})-[:RESOLVES_TO]->(p:Person) "
        "RETURN p.id AS id, p.name AS name, p.organization AS organization ORDER BY p.name"
    ),
)

COUNT_ALIASES_BY_RESOLUTION = NamedQuery(
    name="count_aliases_by_resolution",
    operation="MATCH (:Alias) count by resolution state",
    cypher=(
        "MATCH (a:Alias {namespace: $namespace, resolution: $resolution}) RETURN count(*) AS n"
    ),
)

ALIASES_BY_RESOLUTION = NamedQuery(
    name="aliases_by_resolution",
    operation="MATCH Alias by resolution state",
    cypher=(
        "MATCH (a:Alias {namespace: $namespace, resolution: $resolution}) "
        "RETURN a.id AS id, a.value AS value, a.alias_type AS alias_type, "
        "a.resolution AS resolution, a.support AS support, "
        "a.candidate_count AS candidate_count, a.evidence_doc_id AS evidence_doc_id, "
        "a.evidence_span AS evidence_span ORDER BY a.support DESC LIMIT $limit"
    ),
)

RETIRED_PROPOSITIONS = NamedQuery(
    name="retired_propositions",
    operation="MATCH Proposition status=retired",
    cypher=(
        "MATCH (c:ClaimKey {namespace: $namespace})"
        "-[:HAS_VALUE]->(p:Proposition {status: 'retired'}) "
        "RETURN p.id AS id, p.value AS value, c.id AS claim_key_id, c.key AS key ORDER BY c.key"
    ),
)
