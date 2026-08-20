import re
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

TOKEN = re.compile(r"[A-Za-z0-9_]+")
STOPWORD_TEXT = (
    "a an and are as at be by for from has have how in is it its of on or that the this to was "
    "what when where which who why will with does do did should would could must our we you your "
    "their there these those been being into than then them they about after before between "
    "during over under up down out off again further once here all any both each few more most "
    "other some such no nor not only own same so too very can just now "
)
STOPWORDS = frozenset(STOPWORD_TEXT.split())

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS documents (
        rowid INTEGER PRIMARY KEY,
        doc_id TEXT NOT NULL UNIQUE,
        source_type TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
        title, content, content='documents', content_rowid='rowid', tokenize='unicode61'
    )
    """,
    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE VIRTUAL TABLE IF NOT EXISTS documents_vocab USING fts5vocab('documents_fts', 'row')",
)


@dataclass(frozen=True, slots=True)
class Document:
    doc_id: str
    source_type: str
    title: str
    content: str


@dataclass(frozen=True, slots=True)
class Hit:
    doc_id: str
    source_type: str
    title: str
    score: float
    rank: int


@dataclass(frozen=True, slots=True)
class IndexReport:
    parquet: str
    indexed: int
    skipped_duplicates: int
    seconds: float
    indexed_at: str
    limit: int | None


def query_terms(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for token in TOKEN.findall(text.lower()):
        if token not in STOPWORDS and len(token) > 1:
            seen.setdefault(token, None)
    return list(seen)


def fts_or_query(text: str) -> str:
    return " OR ".join(f'"{term}"' for term in query_terms(text))


def fts_phrase(text: str) -> str:
    return '"' + " ".join(TOKEN.findall(text)) + '"'


class CorpusStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        for statement in SCHEMA:
            self.connection.execute(statement)
        self.connection.commit()

    def fetch(self, sql: str, params: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
        with self.lock:
            return self.connection.execute(sql, params).fetchall()

    def close(self) -> None:
        self.connection.close()

    def count(self) -> int:
        return int(self.fetch("SELECT count(*) FROM documents")[0][0])

    def document_frequency(self, term: str) -> int:
        rows = self.fetch("SELECT doc FROM documents_vocab WHERE term = ?", (term.lower(),))
        return int(rows[0][0]) if rows else 0

    def meta(self, key: str) -> str | None:
        rows = self.fetch("SELECT value FROM meta WHERE key = ?", (key,))
        return str(rows[0][0]) if rows else None

    def _set_meta(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT INTO meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def index_rows(self, rows: Iterable[Document]) -> tuple[int, int]:
        inserted = 0
        skipped = 0
        with self.lock:
            cursor = self.connection.cursor()
            for document in rows:
                result = cursor.execute(
                    "INSERT OR IGNORE INTO documents(doc_id, source_type, title, content) "
                    "VALUES (?, ?, ?, ?)",
                    (document.doc_id, document.source_type, document.title, document.content),
                )
                if result.rowcount == 0:
                    skipped += 1
                    continue
                cursor.execute(
                    "INSERT INTO documents_fts(rowid, title, content) VALUES (?, ?, ?)",
                    (cursor.lastrowid, document.title, document.content),
                )
                inserted += 1
        return inserted, skipped

    def index_parquet(
        self,
        parquet_path: Path,
        limit: int | None = None,
        batch_size: int = 8192,
        progress: Callable[[int], None] | None = None,
    ) -> IndexReport:
        started = time.perf_counter()
        self.connection.execute("PRAGMA synchronous=OFF")
        inserted_total = 0
        skipped_total = 0
        for batch in parquet_documents(parquet_path, batch_size, limit):
            inserted, skipped = self.index_rows(batch)
            inserted_total += inserted
            skipped_total += skipped
            self.connection.commit()
            if progress is not None:
                progress(inserted_total)
        self.connection.execute("PRAGMA synchronous=NORMAL")
        seconds = round(time.perf_counter() - started, 1)
        report = IndexReport(
            parquet=str(parquet_path),
            indexed=self.count(),
            skipped_duplicates=skipped_total,
            seconds=seconds,
            indexed_at=datetime.now(UTC).isoformat(),
            limit=limit,
        )
        self._set_meta("parquet", report.parquet)
        self._set_meta("indexed", str(report.indexed))
        self._set_meta("indexed_at", report.indexed_at)
        self._set_meta("index_seconds", str(report.seconds))
        self._set_meta("limit", "" if limit is None else str(limit))
        self.connection.commit()
        return report

    def document(self, doc_id: str) -> Document | None:
        rows = self.fetch(
            "SELECT doc_id, source_type, title, content FROM documents WHERE doc_id = ?", (doc_id,)
        )
        return Document(*rows[0]) if rows else None

    def documents(self, doc_ids: Iterable[str]) -> dict[str, Document]:
        found: dict[str, Document] = {}
        for doc_id in doc_ids:
            document = self.document(doc_id)
            if document is not None:
                found[doc_id] = document
        return found

    def rank_match(self, match: str, k: int) -> list[Hit]:
        rows = self.fetch(
            "SELECT d.doc_id, d.source_type, d.title, ranked.score FROM ("
            "SELECT rowid AS rid, bm25(documents_fts, 2.0, 1.0) AS score FROM documents_fts "
            "WHERE documents_fts MATCH ? ORDER BY score LIMIT ?"
            ") AS ranked JOIN documents d ON d.rowid = ranked.rid ORDER BY ranked.score",
            (match, k),
        )
        return [
            Hit(doc_id, source_type, title, round(-float(score), 4), rank)
            for rank, (doc_id, source_type, title, score) in enumerate(rows, start=1)
        ]

    def search(self, text: str, k: int = 10) -> list[Hit]:
        match = fts_or_query(text)
        return self.rank_match(match, k) if match else []

    def phrase_hits(self, phrase: str, k: int = 100) -> list[Hit]:
        match = fts_phrase(phrase)
        return self.rank_match(match, k) if match != '""' else []

    def any_phrase_hits(self, phrases: Iterable[str], k: int = 100) -> list[Hit]:
        parts = [fts_phrase(phrase) for phrase in phrases]
        match = " OR ".join(part for part in parts if part != '""')
        return self.rank_match(match, k) if match else []


def parquet_documents(
    parquet_path: Path, batch_size: int, limit: int | None
) -> Iterator[list[Document]]:
    parquet_file = pq.ParquetFile(parquet_path)
    columns = ["doc_id", "source_type", "title", "content"]
    emitted = 0
    for batch in parquet_file.iter_batches(batch_size=batch_size, columns=columns):
        table = batch.to_pydict()
        documents: list[Document] = []
        for doc_id, source_type, title, content in zip(
            table["doc_id"], table["source_type"], table["title"], table["content"], strict=True
        ):
            if limit is not None and emitted >= limit:
                break
            documents.append(Document(doc_id, source_type or "", title or "", content or ""))
            emitted += 1
        if documents:
            yield documents
        if limit is not None and emitted >= limit:
            return
