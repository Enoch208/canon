import os
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO_ID = "onyx-dot-app/EnterpriseRAG-Bench"
DOCUMENTS_FILE = "data/documents/test.parquet"
DEFAULT_CORPUS_DB = Path("data") / "corpus.sqlite"


def documents_parquet_path() -> Path:
    return Path(hf_hub_download(repo_id=REPO_ID, filename=DOCUMENTS_FILE, repo_type="dataset"))


def corpus_db_path(root: Path) -> Path:
    configured = os.environ.get("CANON_CORPUS_DB")
    return Path(configured) if configured else root / DEFAULT_CORPUS_DB
