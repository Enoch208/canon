#!/usr/bin/env python3
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from canon_retrieval.dataset import documents_parquet_path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "evidence" / "run_manifest.json"
TRACKED = (
    "eval/results/latest.json",
    "eval/results/summary.json",
    "eval/official/baseline.jsonl",
    "eval/official/canon_filtered.jsonl",
    "eval/official/canon.jsonl",
    "eval/official/random_filter.jsonl",
    "evidence/official_eval.json",
    "evidence/verify.json",
    "evidence/hydra_perf.json",
    "evidence/graph_stats.json",
    "evidence/corpus_index.json",
    "evidence/seed.json",
    "evidence/entities.json",
    "evidence/topk_sweep.json",
    "evidence/random_control.json",
    "eval/question_ids.json",
    "research/conflict_inventory.json",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str]) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=False).stdout.strip()


def main() -> int:
    image_digest = run(
        [
            "docker",
            "inspect",
            "--format",
            "{{index .RepoDigests 0}}",
            "ghcr.io/hydra-db/hydradb:latest",
        ]
    )
    parquet = documents_parquet_path()
    dataset_revision = next(
        (part for part in parquet.parts if len(part) == 40 and part.isalnum()), "unknown"
    )
    corpus = json.loads((ROOT / "evidence" / "corpus_index.json").read_text())
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": run(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
        "hydradb_image": image_digest or "ghcr.io/hydra-db/hydradb:latest (digest unavailable)",
        "dataset": {
            "repo": "onyx-dot-app/EnterpriseRAG-Bench",
            "revision": dataset_revision,
            "documents_indexed": corpus["indexed"],
        },
        "models": {
            "answer": "claude-sonnet-5",
            "judge_three_pass": "claude-sonnet-5",
            "official_harness_judge": "claude-sonnet-4-6",
        },
        "question_sets": json.loads((ROOT / "eval" / "question_ids.json").read_text()),
        "files": {path: sha256(ROOT / path) for path in TRACKED if (ROOT / path).exists()},
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"{len(manifest['files'])} artifacts fingerprinted")
    summary = (
        f"git {manifest['git_commit'][:12]} · dataset {dataset_revision[:12]} · "
        f"{manifest['hydradb_image'][-20:]}"
    )
    print(summary)
    print(f"evidence: {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
