#!/usr/bin/env python3
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from canon_graph.hydra import HydraClient
from canon_graph.queries import count_edges_in_namespace, count_nodes_in_namespace
from canon_graph.schema import EdgeType, NodeKind

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "graph_stats.json"
NAMESPACE = "canon"


def main() -> int:
    client = HydraClient.from_env()
    if not client.healthy():
        print(f"HydraDB unreachable at {client.base_url}; run `make hydra-up`")
        return 2
    scope = {"namespace": NAMESPACE}
    started = time.perf_counter()
    counts: dict[str, int] = {}
    for kind in NodeKind:
        counts[str(kind)] = int(client.run(count_nodes_in_namespace(kind), scope).scalar() or 0)
        print(f"  {kind:<12} {counts[str(kind)]:>7}", flush=True)
    for edge in EdgeType:
        counts[str(edge)] = int(client.run(count_edges_in_namespace(edge), scope).scalar() or 0)
        print(f"  {edge:<12} {counts[str(edge)]:>7}", flush=True)
    payload = {
        "measured_at": datetime.now(UTC).isoformat(),
        "namespace": NAMESPACE,
        "measure_seconds": round(time.perf_counter() - started, 1),
        "counts": counts,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"evidence: {EVIDENCE.relative_to(ROOT)} ({payload['measure_seconds']}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
