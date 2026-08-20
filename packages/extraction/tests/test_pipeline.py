import json
from pathlib import Path

from canon_extraction.conflicts import bundle_for, load_inventory
from canon_extraction.pipeline import gold_residue_classes, residue_assertion
from canon_extraction.residue import ResidueCandidate
from canon_graph.canonize import canonize
from canon_graph.schema import Discovery, ExtractionMethod, ResidueClass, Stance
from canon_retrieval.store import Document

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "research" / "conflict_inventory.json"
FIXTURES = ROOT / "packages" / "retrieval" / "tests" / "fixtures" / "gold_excerpts.json"


class DictDocuments:
    def __init__(self) -> None:
        self.by_id = {row["doc_id"]: Document(**row) for row in json.loads(FIXTURES.read_text())}

    def document(self, doc_id: str) -> Document | None:
        return self.by_id.get(doc_id)


def test_gold_residue_classes_flag_the_superseded_source() -> None:
    documents = DictDocuments()
    record = next(r for r in load_inventory(INVENTORY).records if r.question_id == "qst_0428")
    bundle = bundle_for(record, documents)
    decision = canonize(bundle)
    classes = gold_residue_classes(bundle, decision, documents)
    assert classes[record.old_doc_id] is ResidueClass.LEXICAL_RESTATEMENT
    assert record.new_doc_id not in classes


def test_residue_assertion_marks_unstructured_hits_uncertain() -> None:
    candidate = ResidueCandidate(
        doc_id="dsid_x",
        source_type="gmail",
        title="t",
        matched_variant="100k / 1M / 5M",
        entity_anchors_matched=(),
        predicate_anchors_in_line=("monthly",),
        line_no=4,
        line="unit economics at 100k / 1M / 5M monthly tokens",
        field_name=None,
        structured=False,
        residue_class=ResidueClass.LEXICAL_RESTATEMENT,
    )
    assertion = residue_assertion(candidate, "100k / 1M / 5M")
    assert assertion.stance is Stance.UNCERTAIN
    assert assertion.extraction_method is ExtractionMethod.LEXICAL_SPAN
    assert Discovery.CORPUS_SCAN is Discovery("corpus_scan")
