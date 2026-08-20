#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from canon_extraction.conflicts import load_inventory
from canon_extraction.pipeline import seed_conflicts
from canon_graph.hydra import HydraClient
from canon_graph.ingest import GraphWriter
from canon_retrieval.dataset import corpus_db_path
from canon_retrieval.store import CorpusStore

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "research" / "conflict_inventory.json"
EVIDENCE = ROOT / "evidence" / "seed.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract conflict claims and seed HydraDB")
    parser.add_argument("--no-residue", action="store_true", help="skip the corpus residue scan")
    parser.add_argument("--reset", action="store_true", help="purge the canon namespace first")
    args = parser.parse_args()
    client = HydraClient.from_env()
    if not client.healthy():
        print(f"HydraDB unreachable at {client.base_url}; run `make hydra-up`")
        return 2
    db_path = corpus_db_path(ROOT)
    if not db_path.exists():
        print(f"corpus store {db_path} missing; run `make index`")
        return 2
    store = CorpusStore(db_path)
    writer = GraphWriter(client)
    if args.reset:
        writer.purge_namespace()
        print("purged canon namespace")
    report = seed_conflicts(
        load_inventory(INVENTORY), store, writer, scan_corpus=not args.no_residue
    )
    for claim in report.claims:
        residue = claim.residue
        counts = (
            f"verified={residue.verified_structured} historical={residue.historical_reference} "
            f"rejected={residue.rejected_reference} restated={residue.lexical_restatement}"
            if residue
            else "residue=not scanned"
        )
        print(f"{claim.question_id} {claim.state:<9} {claim.transition:<22} {counts}")
    summary = report.as_dict()
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(summary, indent=2) + "\n")
    print(
        f"nodes_created={report.nodes_created} edges_created={report.edges_created} "
        f"skipped_existing={report.skipped_existing}"
    )
    print(f"evidence: {EVIDENCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
