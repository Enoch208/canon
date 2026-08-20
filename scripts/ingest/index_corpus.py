#!/usr/bin/env python3
import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from canon_retrieval.dataset import corpus_db_path, documents_parquet_path
from canon_retrieval.store import CorpusStore

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "corpus_index.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Index EnterpriseRAG-Bench documents into SQLite FTS5"
    )
    parser.add_argument("--limit", type=int, default=None, help="index only the first N documents")
    parser.add_argument(
        "--parquet", type=Path, default=None, help="local parquet path (default: download)"
    )
    args = parser.parse_args()
    parquet = args.parquet or documents_parquet_path()
    db_path = corpus_db_path(ROOT)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    store = CorpusStore(db_path)
    if store.count() and args.limit is None and store.meta("limit") == "":
        print(f"{db_path} already holds {store.count()} documents; delete it to re-index")
        return 0
    started = time.perf_counter()
    last_report = [0.0]

    def progress(done: int) -> None:
        now = time.perf_counter()
        if now - last_report[0] >= 10:
            rate = done / max(now - started, 1e-9)
            print(f"indexed {done:,} documents ({rate:,.0f}/s)", flush=True)
            last_report[0] = now

    report = store.index_parquet(parquet, limit=args.limit, progress=progress)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps({**asdict(report), "db": str(db_path)}, indent=2) + "\n")
    print(json.dumps(asdict(report), indent=2))
    print(f"evidence: {EVIDENCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
