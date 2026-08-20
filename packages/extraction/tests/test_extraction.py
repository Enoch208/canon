import json
from pathlib import Path

import pytest

from canon_extraction.conflicts import (
    ConflictRecord,
    bundle_for,
    load_inventory,
    split_claim_key,
)
from canon_extraction.residue import anchor_terms, scan_residue
from canon_extraction.structured import (
    classify_line,
    is_structured_field_line,
    line_containing,
    match_at,
)
from canon_extraction.values import find_all, value_variants
from canon_graph.canonize import canonize
from canon_graph.schema import ResidueClass, TemporalQuality, Transition, TruthState
from canon_retrieval.store import CorpusStore, Document

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "research" / "conflict_inventory.json"
FIXTURES = ROOT / "packages" / "retrieval" / "tests" / "fixtures" / "gold_excerpts.json"


class DictDocuments:
    def __init__(self, documents: list[Document]) -> None:
        self.by_id = {document.doc_id: document for document in documents}

    def document(self, doc_id: str) -> Document | None:
        return self.by_id.get(doc_id)


@pytest.fixture(scope="module")
def documents() -> DictDocuments:
    return DictDocuments([Document(**row) for row in json.loads(FIXTURES.read_text())])


def test_value_variants_cover_list_and_percent_forms() -> None:
    assert "100k/1M/5M" in value_variants("100k / 1M / 5M")
    assert "100k, 1M, and 5M" in value_variants("100k / 1M / 5M")
    assert value_variants("20%")[:3] == ("20%", "20 %", "20 percent")
    assert value_variants("12 months (expand only if anomalies)")[:2] == (
        "12 months (expand only if anomalies)",
        "12 months",
    )
    assert find_all("Price 20% now, was 20% before", "20%") == [6, 19]


def test_structured_field_lines_only_for_structured_sources() -> None:
    assert is_structured_field_line("jira", "due_date: 2026-03-12") == (True, "due_date")
    assert is_structured_field_line("confluence", "due_date: 2026-03-12") == (False, None)
    assert is_structured_field_line("jira", "Some prose without a field") == (False, None)
    prose = "description: " + "x" * 200
    assert is_structured_field_line("jira", prose) == (False, "description")


def test_classify_line_markers_take_precedence_over_structure() -> None:
    assert classify_line("jira", "status: no longer 20%")[0] is ResidueClass.REJECTED_REFERENCE
    assert classify_line("jira", "note: previously 20%")[0] is ResidueClass.HISTORICAL_REFERENCE
    assert classify_line("jira", "reserve: 20%") == (
        ResidueClass.VERIFIED_STRUCTURED,
        True,
        "reserve",
    )
    assert classify_line("slack", "reserve: 20%")[0] is ResidueClass.LEXICAL_RESTATEMENT
    assert classify_line("jira", "limit: cannot exceed 20%")[0] is ResidueClass.LEXICAL_RESTATEMENT


def test_match_at_reports_line_of_gold_span(documents: DictDocuments) -> None:
    document = documents.document("dsid_10559147d3014931898864f22c311e47")
    assert document is not None
    position = find_all(document.content, "old doc says 100k/1M/5M")[0]
    line = match_at(document.source_type, document.content, position)
    assert line.residue_class is ResidueClass.HISTORICAL_REFERENCE
    assert "outdated" in line.line


def test_inventory_loads_all_twenty_conflicts() -> None:
    inventory = load_inventory(INVENTORY)
    assert len(inventory.records) == 20
    assert inventory.primary_demo_question_id in {r.question_id for r in inventory.records}
    assert split_claim_key(
        "Hosted enterprise_playbook.monthly_token_volume_discount_breakpoints"
    ) == (
        "Hosted enterprise_playbook",
        "monthly_token_volume_discount_breakpoints",
    )


def test_bundle_for_qst_0428_canonizes_by_explicit_supersession(documents: DictDocuments) -> None:
    record = next(r for r in load_inventory(INVENTORY).records if r.question_id == "qst_0428")
    bundle = bundle_for(record, documents)
    assert bundle.entity_name == "Hosted enterprise_playbook"
    assert {a.value for a in bundle.assertions} == {"100k / 1M / 5M", "250k / 2M / 10M"}
    assert len(bundle.supersessions) == 1
    decision = canonize(bundle)
    assert decision.state is TruthState.CANON
    assert decision.current_value == "250k / 2M / 10M"
    assert decision.retired_values == ("100k / 1M / 5M",)
    assert decision.transition is Transition.EXPLICIT_SUPERSESSION
    assert decision.temporal_quality is TemporalQuality.T1


def test_bundle_without_explicit_supersession_is_contested(documents: DictDocuments) -> None:
    record = ConflictRecord(
        question_id="synthetic_check",
        question="",
        claim_key="Hosted enterprise_playbook.monthly_token_volume_discount_breakpoints",
        old_value="100k / 1M / 5M",
        new_value="250k / 2M / 10M",
        old_doc_id="dsid_1214ee9ab5e44de487c800f7a4771d7d",
        new_doc_id="dsid_10559147d3014931898864f22c311e47",
        old_span="Volume discounts: predefined breaks at 100k, 1M, and 5M monthly tokens",
        new_span="predefined breaks at 250k, 2M, and 10M monthly tokens",
        explicit_supersession=False,
        temporal_quality=TemporalQuality.T2,
        gold_answer="",
        demo_score=0,
    )
    assert canonize(bundle_for(record, documents)).state is TruthState.CONTESTED


def test_bundle_raises_when_gold_doc_missing(documents: DictDocuments) -> None:
    record = next(r for r in load_inventory(INVENTORY).records if r.question_id == "qst_0413")
    with pytest.raises(FileNotFoundError):
        bundle_for(record, documents)


def test_residue_scan_over_fixture_corpus(tmp_path: Path, documents: DictDocuments) -> None:
    store = CorpusStore(tmp_path / "corpus.sqlite")
    store.index_rows(documents.by_id.values())
    store.connection.commit()
    scan = scan_residue(
        store,
        "100k / 1M / 5M",
        "Hosted enterprise_playbook",
        "monthly_token_volume_discount_breakpoints",
    )
    assert anchor_terms("Hosted enterprise_playbook") == ("hosted", "enterprise", "playbook")
    assert scan.entity_anchors == ("hosted", "enterprise", "playbook")
    assert "AND" in scan.fts_query
    by_doc = {candidate.doc_id: candidate for candidate in scan.candidates}
    assert set(by_doc) == {
        "dsid_1214ee9ab5e44de487c800f7a4771d7d",
        "dsid_10559147d3014931898864f22c311e47",
    }
    assert by_doc["dsid_10559147d3014931898864f22c311e47"].residue_class is (
        ResidueClass.HISTORICAL_REFERENCE
    )
    assert by_doc["dsid_1214ee9ab5e44de487c800f7a4771d7d"].residue_class is (
        ResidueClass.LEXICAL_RESTATEMENT
    )
    assert scan.count(ResidueClass.VERIFIED_STRUCTURED) == 0


def test_questions_are_not_assertions() -> None:
    assert classify_line("fireflies", "Nina: When you say sign, is that GPG?")[0] is (
        ResidueClass.NOT_AN_ASSERTION
    )
    assert classify_line("confluence", "Volume discounts: breaks at 100k, 1M, and 5M.")[0] is (
        ResidueClass.LEXICAL_RESTATEMENT
    )


def test_line_containing_keeps_the_first_character_when_there_is_no_break() -> None:
    assert line_containing("price: 20% flat", 7) == (1, "price: 20% flat")
    assert line_containing("a\nprice: 20%", 3) == (2, "price: 20%")
