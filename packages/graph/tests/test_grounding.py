import pytest

from canon_graph.canonize import canonize
from canon_graph.grounding import (
    DocDisposition,
    GroundingMode,
    best_claim_key,
    ground,
    match_claim_keys,
)
from canon_graph.hydra import HydraClient
from canon_graph.ingest import GraphWriter
from canon_graph.resolve import GraphReader
from canon_graph.schema import TruthState
from canon_graph.verify import PRICE_KEY, contested_bundle, majority_bundle

pytestmark = pytest.mark.hydra


def test_grounding_drops_superseded_docs_and_resolves_claim_key(
    hydra: HydraClient, verify_writer: GraphWriter
) -> None:
    bundle = majority_bundle()
    verify_writer.write_claim(bundle, canonize(bundle), {})
    reader = GraphReader(hydra)
    keys = reader.all_claim_keys("verify")
    matches = match_claim_keys("What is the VerifyCo Nova price per 1k tokens now?", keys)
    assert matches and matches[0].claim_key.key == PRICE_KEY

    grounding = ground(
        reader,
        "What is the VerifyCo Nova price per 1k tokens now?",
        ("verify_old_0", "verify_old_1", "verify_update", "unrelated_doc"),
        namespace="verify",
    )
    by_doc = {doc.doc_id: doc.disposition for doc in grounding.docs}
    assert by_doc["verify_old_0"] is DocDisposition.SUPERSEDED
    assert by_doc["verify_update"] is DocDisposition.CURRENT_EVIDENCE
    assert by_doc["unrelated_doc"] is DocDisposition.UNLINKED
    assert set(grounding.kept_doc_ids) == {"verify_update", "unrelated_doc"}
    assert grounding.query_cards
    assert grounding.state in {TruthState.CANON, TruthState.UNKNOWN}

    historical = ground(
        reader,
        "What was the VerifyCo Nova price per 1k tokens before the update?",
        ("verify_old_0", "verify_update"),
        mode=GroundingMode.HISTORICAL,
        namespace="verify",
    )
    assert "verify_old_0" in historical.kept_doc_ids
    assert "verify_update" not in historical.kept_doc_ids


def test_grounding_keeps_contested_evidence(hydra: HydraClient, verify_writer: GraphWriter) -> None:
    bundle = contested_bundle()
    verify_writer.write_claim(bundle, canonize(bundle), {})
    reader = GraphReader(hydra)
    grounding = ground(
        reader, "When does VerifyCo Atlas launch?", ("verify_c1", "verify_c2"), namespace="verify"
    )
    assert {doc.disposition for doc in grounding.docs} == {DocDisposition.CONTESTED_EVIDENCE}
    assert set(grounding.kept_doc_ids) == {"verify_c1", "verify_c2"}


def test_claim_key_matching_separates_conflicts_from_unanswerable_questions(
    hydra: HydraClient,
) -> None:
    reader = GraphReader(hydra)
    keys = reader.all_claim_keys()
    if len(keys) != 20:
        pytest.skip("canon graph not seeded; run `make seed`")

    answerable = (
        "What monthly token volume discount breakpoints apply for Hosted pricing in the "
        "enterprise playbook?"
    )
    matched = match_claim_keys(answerable, keys)
    assert best_claim_key(matched) is not None
    assert matched[0].coverage >= 0.5

    unanswerable = (
        "What are the exact Azure Marketplace metering dimension names and units we use for "
        "Hosted API, and which token counts do they bill?"
    )
    assert match_claim_keys(unanswerable, keys) == ()
