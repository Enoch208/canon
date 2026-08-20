import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.hydra


@pytest.fixture(scope="module")
def client() -> TestClient:
    try:
        from canon_api.app import app, service
    except Exception as error:
        pytest.skip(f"api service unavailable in this environment: {error}")
    if not service.healthy():
        pytest.skip("HydraDB not reachable; run `make hydra-up`")
    if not service.reader.all_claim_keys():
        pytest.skip("graph is empty; run `make seed`")
    return TestClient(app)


def test_health_reports_hydra_and_corpus(client: TestClient) -> None:
    payload = client.get("/health").json()
    assert payload["hydra"] is True
    assert payload["corpus_documents"] > 0


def test_conflicts_are_resolved_from_the_graph(client: TestClient) -> None:
    conflicts = client.get("/conflicts").json()
    assert len(conflicts) == 20
    canon = [row for row in conflicts if row["state"] == "CANON"]
    assert canon
    assert all(row["current_value"] for row in canon)
    assert all(row["retired_values"] for row in canon)


def test_truth_change_carries_evidence_and_query_cards(client: TestClient) -> None:
    change = client.get("/conflicts/qst_0428").json()
    assert change["state"] == "CANON"
    assert change["current_value"] == "250k / 2M / 10M"
    assert change["retired_values"] == ["100k / 1M / 5M"]
    assert change["current_evidence"] and change["retired_evidence"]
    assert all(row["discovery"] == "conflict_pair" for row in change["retired_evidence"])
    assert {row["discovery"] for row in change["residue"]} == {"conflict_pair", "corpus_scan"}
    assert {card["query_name"] for card in change["query_cards"]} >= {
        "claim_neighborhood",
        "supersession_chain",
        "residue_reverse_traversal",
    }
    assert client.get("/conflicts/qst_9999").status_code == 404


def test_ask_current_and_historical_modes(client: TestClient) -> None:
    question = "What monthly token volume discount breakpoints apply for Hosted pricing?"
    current = client.post("/ask", json={"question": question, "mode": "current"}).json()
    assert current["state"] == "CANON"
    assert current["answer_value"] == "250k / 2M / 10M"
    assert current["query_cards"]

    historical = client.post("/ask", json={"question": question, "mode": "historical"}).json()
    assert historical["answer_value"] == "100k / 1M / 5M"


def test_ask_returns_unknown_without_a_matching_claim(client: TestClient) -> None:
    payload = client.post(
        "/ask",
        json={
            "question": "Which public blockchain network anchors the admin activity chronicle?",
            "mode": "current",
        },
    ).json()
    assert payload["state"] == "UNKNOWN"
    assert payload["answer_value"] is None


def test_residue_report_defines_every_class_it_counts(client: TestClient) -> None:
    report = client.get("/residue").json()
    assert set(report["counts"]) == set(report["definition"])
    assert report["counts"]["VERIFIED_STRUCTURED"] == len(
        [row for row in report["rows"] if row["residue_class"] == "VERIFIED_STRUCTURED"]
    )
    for row in report["rows"]:
        assert row["evidence_span"]
        assert row["doc_id"].startswith("dsid_")


def test_dashboard_counts_only_the_canon_namespace(client: TestClient) -> None:
    dashboard = client.get("/dashboard").json()
    assert dashboard["claim_keys"] == 20
    assert dashboard["graph_counts"]["ClaimKey"] == 20
    assert dashboard["graph_counts"]["SUPERSEDES"] == dashboard["current_conflicts"]
    assert dashboard["verified_resurrections"] == 0
    assert "no metadata timestamp" in dashboard["resurrection_note"]


def test_identity_report_separates_the_three_resolution_states(client: TestClient) -> None:
    report = client.get("/entities").json()
    assert set(report["definition"]) == {"RESOLVED", "PROBABLE", "AMBIGUOUS"}
    assert report["corpus"]["bindings_found"] > 0
    assert report["corpus"]["people"] > 0
    assert set(report["materialised"]) == {"RESOLVED", "PROBABLE", "AMBIGUOUS"}
    for alias in report["aliases"]:
        assert alias["evidence_doc_id"].startswith("dsid_")
        assert alias["evidence_span"]
        assert alias["candidate_count"] >= 1
        if alias["resolution"] == "AMBIGUOUS":
            assert alias["candidate_count"] > 1
        else:
            assert alias["candidate_count"] == 1
