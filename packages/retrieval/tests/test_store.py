import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from canon_retrieval.store import CorpusStore, Document, fts_or_query, fts_phrase, query_terms

FIXTURES = Path(__file__).parent / "fixtures" / "gold_excerpts.json"


def fixture_documents() -> list[Document]:
    return [Document(**row) for row in json.loads(FIXTURES.read_text())]


@pytest.fixture
def store(tmp_path: Path) -> CorpusStore:
    corpus = CorpusStore(tmp_path / "corpus.sqlite")
    corpus.index_rows(fixture_documents())
    corpus.connection.commit()
    return corpus


def test_query_terms_drop_stopwords_and_dedupe() -> None:
    terms = query_terms("What is the price of the Hosted price tier?")
    assert terms == ["price", "hosted", "tier"]
    assert fts_or_query("What is the price?") == '"price"'
    assert fts_phrase("100k/1M/5M") == '"100k 1M 5M"'


def test_bm25_search_ranks_conflict_docs_first(store: CorpusStore) -> None:
    hits = store.search(
        "What monthly token volume discount breakpoints apply for Hosted pricing "
        "in the enterprise playbook?",
        k=3,
    )
    assert hits[0].rank == 1
    assert {hit.doc_id for hit in hits[:2]} == {
        "dsid_1214ee9ab5e44de487c800f7a4771d7d",
        "dsid_10559147d3014931898864f22c311e47",
    }
    assert hits[0].score >= hits[1].score >= hits[2].score


def test_phrase_hits_find_retired_value(store: CorpusStore) -> None:
    hits = store.phrase_hits("100k, 1M, and 5M monthly tokens")
    assert [hit.doc_id for hit in hits] == ["dsid_1214ee9ab5e44de487c800f7a4771d7d"]
    any_hits = store.any_phrase_hits(["100k, 1M, and 5M", "250k, 2M, and 10M"])
    assert {hit.doc_id for hit in any_hits} == {
        "dsid_1214ee9ab5e44de487c800f7a4771d7d",
        "dsid_10559147d3014931898864f22c311e47",
    }


def test_document_lookup(store: CorpusStore) -> None:
    document = store.document("dsid_5f3a672da4974781a5577b0f3d4993e9")
    assert document is not None and document.source_type == "jira"
    assert store.document("dsid_missing") is None
    assert store.count() == 12


def test_index_parquet_reports_real_counts(tmp_path: Path) -> None:
    documents = fixture_documents()
    table = pa.table(
        {
            "doc_id": [d.doc_id for d in documents] + [documents[0].doc_id],
            "source_type": [d.source_type for d in documents] + [documents[0].source_type],
            "title": [d.title for d in documents] + [documents[0].title],
            "content": [d.content for d in documents] + [documents[0].content],
        }
    )
    parquet = tmp_path / "docs.parquet"
    pq.write_table(table, parquet)
    corpus = CorpusStore(tmp_path / "corpus.sqlite")
    seen: list[int] = []
    report = corpus.index_parquet(parquet, batch_size=2, progress=seen.append)
    assert report.indexed == 12
    assert report.skipped_duplicates == 1
    assert report.limit is None
    assert seen[-1] == 12
    assert corpus.meta("indexed") == "12"
    limited = CorpusStore(tmp_path / "limited.sqlite").index_parquet(parquet, limit=2)
    assert limited.indexed == 2 and limited.limit == 2
