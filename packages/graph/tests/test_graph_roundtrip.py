import pytest

from canon_graph import ids
from canon_graph.canonize import AssertionInput, ClaimBundle, SupersessionSignal, canonize
from canon_graph.hydra import HydraClient
from canon_graph.ingest import GraphWriter
from canon_graph.resolve import GraphReader
from canon_graph.schema import (
    ExtractionMethod,
    PropositionStatus,
    ResidueClass,
    Stance,
    TemporalQuality,
    Transition,
    TruthState,
)

pytestmark = pytest.mark.hydra

KEY = "VerifyCo Nova.price_per_1k_tokens"


def price_assertion(doc_id: str, value: str, asserted_at: str) -> AssertionInput:
    return AssertionInput(
        doc_id=doc_id,
        source_type="jira",
        value=value,
        evidence_span=f"price: {value}",
        stance=Stance.CURRENT,
        structured=True,
        extraction_method=ExtractionMethod.STRUCTURED_FIELD,
        asserted_at=asserted_at,
        source_field="price",
    )


def majority_bundle() -> ClaimBundle:
    old = tuple(price_assertion(f"verify_old_{i}", "$0.08", f"2026-01-0{i + 1}") for i in range(8))
    update = price_assertion("verify_update", "$0.06", "2026-02-01")
    signal = SupersessionSignal(
        "verify_update", "$0.08", "$0.06", "price changed from $0.08 to $0.06", "2026-02-01"
    )
    return ClaimBundle(
        entity_name="VerifyCo Nova",
        entity_type="Product",
        key=KEY,
        predicate="price_per_1k_tokens",
        question_id="verify_majority",
        assertions=(*old, update),
        supersessions=(signal,),
        temporal_quality=TemporalQuality.T1,
    )


def test_write_then_resolve_majority_vs_supersession(
    hydra: HydraClient, verify_writer: GraphWriter
) -> None:
    bundle = majority_bundle()
    decision = canonize(bundle)
    claim_key_id, propositions = verify_writer.write_claim(bundle, decision, {})
    assert verify_writer.report.nodes_created > 0

    reader = GraphReader(hydra)
    claim_key = reader.claim_key(KEY)
    assert claim_key is not None and claim_key.id == claim_key_id
    resolution = reader.resolve(claim_key)
    assert resolution.state is TruthState.CANON
    assert resolution.current is not None and resolution.current.value == "$0.06"
    assert [p.value for p in resolution.retired] == ["$0.08"]
    assert resolution.transition is Transition.EXPLICIT_SUPERSESSION
    assert resolution.temporal_quality is TemporalQuality.T1
    assert len(resolution.current_evidence) == 1
    assert len(resolution.retired_evidence) == 8
    assert len(resolution.events) == 2
    assert resolution.events[1].supersedes_event_id == resolution.events[0].id
    assert {card.query_name for card in resolution.query_cards} >= {
        "claim_neighborhood",
        "claim_events",
        "supersession_chain",
        "residue_reverse_traversal",
    }
    assert propositions["$0.08"] == ids.proposition_id(KEY, "$0.08", ids.Namespace.VERIFY)


def test_reingest_is_idempotent(hydra: HydraClient, verify_writer: GraphWriter) -> None:
    bundle = majority_bundle()
    decision = canonize(bundle)
    verify_writer.write_claim(bundle, decision, {})
    first = verify_writer.report.nodes_created
    second_writer = GraphWriter(hydra, ids.Namespace.VERIFY)
    second_writer.write_claim(bundle, decision, {})
    assert second_writer.report.nodes_created == 0
    assert second_writer.report.edges_created == 0
    assert first > 0
    reader = GraphReader(hydra)
    claim_key = reader.claim_key(KEY)
    assert claim_key is not None
    assert len(reader.resolve(claim_key).retired_evidence) == 8


def test_residue_reverse_traversal_and_proof(
    hydra: HydraClient, verify_writer: GraphWriter
) -> None:
    bundle = majority_bundle()
    decision = canonize(bundle)
    _, propositions = verify_writer.write_claim(bundle, decision, {})
    residue = AssertionInput(
        doc_id="verify_residue_doc",
        source_type="hubspot",
        value="$0.08",
        evidence_span="unit_price: $0.08",
        stance=Stance.CURRENT,
        structured=True,
        extraction_method=ExtractionMethod.STRUCTURED_FIELD,
        source_field="unit_price",
    )
    assertion_id = verify_writer.write_assertion(
        KEY, propositions["$0.08"], residue, "Quote 42", ResidueClass.VERIFIED_STRUCTURED
    )
    reader = GraphReader(hydra)
    rows = reader.residue(propositions["$0.08"])
    assert [row.assertion.doc_id for row in rows] == ["verify_residue_doc"]
    assert rows[0].assertion.residue_class is ResidueClass.VERIFIED_STRUCTURED
    assert rows[0].title == "Quote 42"
    proof = reader.proof_path(assertion_id)
    assert len(proof) == 1
    assert proof[0]["retired_value"] == "$0.08"
    assert proof[0]["current_value"] == "$0.06"
    assert proof[0]["transition"] == str(Transition.EXPLICIT_SUPERSESSION)
    claims = reader.artifact_claims("verify_residue_doc")
    assert claims[0].status is PropositionStatus.RETIRED
    assert claims[0].residue_class is ResidueClass.VERIFIED_STRUCTURED


def test_unknown_and_contested_states(hydra: HydraClient, verify_writer: GraphWriter) -> None:
    reader = GraphReader(hydra)
    assert reader.claim_key("VerifyCo.never_asserted") is None
    contested = ClaimBundle(
        entity_name="VerifyCo Atlas",
        entity_type="Project",
        key="VerifyCo Atlas.launch_date",
        predicate="launch_date",
        question_id="verify_contested",
        assertions=(
            price_assertion("verify_c1", "Sep 18", "2026-03-01"),
            price_assertion("verify_c2", "Sep 21", "2026-03-01"),
        ),
        supersessions=(),
        temporal_quality=TemporalQuality.T3,
    )
    decision = canonize(contested)
    assert decision.state is TruthState.CONTESTED
    verify_writer.write_claim(contested, decision, {})
    claim_key = reader.claim_key("VerifyCo Atlas.launch_date")
    assert claim_key is not None
    resolution = reader.resolve(claim_key)
    assert resolution.state is TruthState.CONTESTED
    assert resolution.current is None
    assert {p.value for p in resolution.contested} == {"Sep 18", "Sep 21"}
    assert resolution.events == ()
