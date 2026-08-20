import json
from pathlib import Path

from canon_graph.ids import (
    Namespace,
    artifact_id,
    assertion_id,
    canon_event_id,
    claim_key_id,
    entity_id,
    kind_of,
    namespace_of,
    node_id,
    proposition_id,
)
from canon_graph.schema import NodeKind

INVENTORY = Path(__file__).resolve().parents[3] / "research" / "conflict_inventory.json"


def test_ids_are_deterministic() -> None:
    assert claim_key_id("Atlas.launch_date") == claim_key_id("Atlas.launch_date")
    assert proposition_id("Atlas.launch_date", "Sep 18") != proposition_id(
        "Atlas.launch_date", "Sep 21"
    )


def test_ids_encode_kind_and_namespace() -> None:
    value = proposition_id("Atlas.launch_date", "Sep 18", Namespace.VERIFY)
    assert kind_of(value) is NodeKind.PROPOSITION
    assert namespace_of(value) is Namespace.VERIFY
    assert namespace_of(entity_id("Atlas")) is Namespace.CANON


def test_same_key_different_kind_never_collides() -> None:
    seen = {node_id(kind, "same") for kind in NodeKind}
    assert len(seen) == len(NodeKind)


def test_ids_fit_in_signed_int64() -> None:
    biggest = node_id(NodeKind.ARTIFACT, "x", Namespace.BENCH)
    assert 0 < biggest < 2**62


def test_inventory_claim_keys_do_not_collide() -> None:
    inventory = json.loads(INVENTORY.read_text())
    ids: set[int] = set()
    for conflict in inventory["conflicts"]:
        key = conflict["claim_key"]
        ids.add(claim_key_id(key))
        ids.add(proposition_id(key, conflict["old_proposition"]))
        ids.add(proposition_id(key, conflict["new_proposition"]))
        ids.add(artifact_id(conflict["old_doc_id"]))
        ids.add(artifact_id(conflict["new_doc_id"]))
        ids.add(assertion_id(key, conflict["old_proposition"], conflict["old_doc_id"], "s"))
        ids.add(canon_event_id(key, conflict["new_proposition"], conflict["new_doc_id"]))
    unique_docs = len(inventory["unique_gold_doc_ids"])
    assert len(ids) == 20 * 5 + unique_docs
