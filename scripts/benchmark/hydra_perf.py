#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from canon_graph.hydra import HydraClient
from canon_graph.perf import run_perf

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "hydra_perf.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="HydraDB viability and latency measurements")
    parser.add_argument("--nodes", type=int, default=10_000)
    parser.add_argument("--fan-in", type=int, default=40)
    parser.add_argument("--chain-depth", type=int, default=10)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--cross-passes", type=int, default=2)
    parser.add_argument(
        "--delete-nodes",
        action="store_true",
        help="also delete the bench vertices after their edges (slow on this engine)",
    )
    args = parser.parse_args()

    client = HydraClient.from_env()
    if not client.healthy():
        print(f"HydraDB unreachable at {client.base_url}; run `make hydra-up`")
        return 2
    report = run_perf(
        client,
        args.nodes,
        args.fan_in,
        args.chain_depth,
        args.runs,
        args.cross_passes,
        delete_nodes=args.delete_nodes,
    )
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report.as_dict(), indent=2) + "\n")
    print(json.dumps(report.as_dict(), indent=2))
    print(f"evidence: {EVIDENCE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
