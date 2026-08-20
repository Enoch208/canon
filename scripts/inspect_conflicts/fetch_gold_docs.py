#!/usr/bin/env python3
import json
from pathlib import Path

import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "research" / "conflict_inventory.json"
OUT_DIR = ROOT / "research" / "conflict_docs"
MANIFEST = OUT_DIR / "manifest.json"


def main() -> None:
    inventory = json.loads(INVENTORY.read_text())
    needed = set(inventory["unique_gold_doc_ids"])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    parquet_path = hf_hub_download(
        repo_id="onyx-dot-app/EnterpriseRAG-Bench",
        filename="data/documents/test.parquet",
        repo_type="dataset",
    )
    found = {}
    parquet_file = pq.ParquetFile(parquet_path)
    columns = ["doc_id", "source_type", "title", "content"]
    for batch in parquet_file.iter_batches(batch_size=4096, columns=columns):
        table = batch.to_pydict()
        for doc_id, source_type, title, content in zip(
            table["doc_id"],
            table["source_type"],
            table["title"],
            table["content"],
            strict=True,
        ):
            if doc_id in needed and doc_id not in found:
                found[doc_id] = {
                    "doc_id": doc_id,
                    "source_type": source_type,
                    "title": title,
                    "content": content,
                }
        if len(found) == len(needed):
            break
    missing = sorted(needed - set(found))
    for doc_id, row in found.items():
        text = json.dumps(row, ensure_ascii=False, indent=2) + "\n"
        (OUT_DIR / f"{doc_id}.json").write_text(text)
    MANIFEST.write_text(
        json.dumps(
            {
                "requested": sorted(needed),
                "found": sorted(found),
                "missing": missing,
                "parquet": parquet_path,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {len(found)} docs missing {len(missing)}")
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
