from enum import IntEnum
from hashlib import blake2b

from canon_graph.schema import NodeKind

HASH_BITS = 56
HASH_MASK = (1 << HASH_BITS) - 1


class Namespace(IntEnum):
    CANON = 0
    VERIFY = 1
    BENCH = 2


KIND_CODES: dict[NodeKind, int] = {
    NodeKind.ENTITY: 1,
    NodeKind.PERSON: 7,
    NodeKind.ALIAS: 8,
    NodeKind.CLAIM_KEY: 2,
    NodeKind.PROPOSITION: 3,
    NodeKind.ASSERTION: 4,
    NodeKind.CANON_EVENT: 5,
    NodeKind.ARTIFACT: 6,
}


def _hash56(text: str) -> int:
    digest = blake2b(text.encode("utf-8"), digest_size=7).digest()
    return int.from_bytes(digest, "big") & HASH_MASK


def node_id(kind: NodeKind, natural_key: str, namespace: Namespace = Namespace.CANON) -> int:
    prefix = (namespace << 4) | KIND_CODES[kind]
    return (prefix << HASH_BITS) | _hash56(f"{kind}:{natural_key}")


def kind_of(node_id_value: int) -> NodeKind:
    code = (node_id_value >> HASH_BITS) & 0xF
    for kind, kind_code in KIND_CODES.items():
        if kind_code == code:
            return kind
    raise ValueError(f"unknown kind code {code} in id {node_id_value}")


def namespace_of(node_id_value: int) -> Namespace:
    return Namespace((node_id_value >> (HASH_BITS + 4)) & 0xF)


def entity_id(name: str, namespace: Namespace = Namespace.CANON) -> int:
    return node_id(NodeKind.ENTITY, name, namespace)


def person_id(key: str, namespace: Namespace = Namespace.CANON) -> int:
    return node_id(NodeKind.PERSON, key, namespace)


def alias_id(value: str, alias_type: str, namespace: Namespace = Namespace.CANON) -> int:
    return node_id(NodeKind.ALIAS, f"{alias_type}:{value}", namespace)


def claim_key_id(key: str, namespace: Namespace = Namespace.CANON) -> int:
    return node_id(NodeKind.CLAIM_KEY, key, namespace)


def proposition_id(key: str, value: str, namespace: Namespace = Namespace.CANON) -> int:
    return node_id(NodeKind.PROPOSITION, f"{key}={value}", namespace)


def artifact_id(doc_id: str, namespace: Namespace = Namespace.CANON) -> int:
    return node_id(NodeKind.ARTIFACT, doc_id, namespace)


def assertion_id(
    key: str, value: str, doc_id: str, span: str, namespace: Namespace = Namespace.CANON
) -> int:
    return node_id(NodeKind.ASSERTION, f"{key}={value}@{doc_id}#{span}", namespace)


def canon_event_id(
    key: str, value: str, evidence_doc_id: str, namespace: Namespace = Namespace.CANON
) -> int:
    return node_id(NodeKind.CANON_EVENT, f"{key}={value}<-{evidence_doc_id}", namespace)
