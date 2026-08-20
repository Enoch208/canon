import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from canon_graph import queries
from canon_graph.hydra import HydraClient, NamedQuery, Param
from canon_graph.ids import Namespace, node_id
from canon_graph.ingest import BATCH_LIMIT, GraphWriter
from canon_graph.schema import EdgeType, NodeKind

CLEANUP_BATCH = 128
FULL_SCAN_NOTE = (
    "An unanchored MATCH ()-[:REL]->() count exceeds the 30 s query timeout once the benchmark "
    "subgraph is loaded. Canon never issues one: every product query starts from a vertex id or a "
    "namespace predicate. The counts below are namespace-scoped for that reason."
)
ORPHAN_NOTE = (
    "Benchmark vertices are created by UNWIND batches and carry only an id — no label, no kind, "
    "no namespace — so no product query can reach them once their edges are deleted. Edge deletion "
    "runs at roughly 1.6k rows/s; deleting the vertices themselves costs about a second each on "
    "this engine, so it is opt-in via --delete-nodes."
)
BENCH_EDGE = EdgeType.SUPERSEDES
FAN_IN_EDGE = EdgeType.ASSERTS


@dataclass(frozen=True, slots=True)
class LatencySample:
    name: str
    operation: str
    runs: int
    p50_ms: float
    p95_ms: float
    max_ms: float
    result_rows: int


@dataclass(slots=True)
class PerfReport:
    measured_at: str
    hydra_url: str
    nodes_written: int
    edges_written: int
    write_seconds: float
    write_rows_per_second: float
    engine_write_seconds: float
    samples: list[LatencySample] = field(default_factory=list)
    graph_counts: dict[str, int] = field(default_factory=dict)
    edge_cleanup_seconds: float = 0.0
    node_cleanup_seconds: float | None = None
    orphan_nodes_left: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "measured_at": self.measured_at,
            "hydra_url": self.hydra_url,
            "nodes_written": self.nodes_written,
            "edges_written": self.edges_written,
            "write_seconds": round(self.write_seconds, 2),
            "write_rows_per_second": round(self.write_rows_per_second, 1),
            "engine_write_seconds": round(self.engine_write_seconds, 3),
            "edge_cleanup_seconds": round(self.edge_cleanup_seconds, 2),
            "edge_cleanup_rows_per_second": (
                round(self.edges_written / self.edge_cleanup_seconds, 1)
                if self.edge_cleanup_seconds
                else 0.0
            ),
            "node_cleanup_seconds": (
                round(self.node_cleanup_seconds, 2)
                if self.node_cleanup_seconds is not None
                else None
            ),
            "orphan_nodes_left": self.orphan_nodes_left,
            "orphan_note": ORPHAN_NOTE,
            "full_scan_note": FULL_SCAN_NOTE,
            "graph_counts": self.graph_counts,
            "latency": [asdict(sample) for sample in self.samples],
        }


def bench_id(index: int) -> int:
    return node_id(NodeKind.ASSERTION, f"bench:{index}", Namespace.BENCH)


def chain_id(index: int) -> int:
    return node_id(NodeKind.CANON_EVENT, f"bench-chain:{index}", Namespace.BENCH)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 3)


def measure(
    client: HydraClient, query: NamedQuery, params: dict[str, Param], runs: int
) -> LatencySample:
    timings: list[float] = []
    rows = 0
    for _ in range(runs):
        result = client.run(query, params)
        timings.append(result.client_ms)
        rows = len(result)
    return LatencySample(
        name=query.name,
        operation=query.operation,
        runs=runs,
        p50_ms=percentile(timings, 0.5),
        p95_ms=percentile(timings, 0.95),
        max_ms=round(max(timings), 3),
        result_rows=rows,
    )


def write_edges(client: HydraClient, edge: EdgeType, pairs: list[tuple[int, int]]) -> None:
    query = queries.unwind_create_edges(edge)
    for start in range(0, len(pairs), BATCH_LIMIT):
        batch = pairs[start : start + BATCH_LIMIT]
        client.run(query, {"rows": [{"s": source, "t": target} for source, target in batch]})


def build_pairs(
    nodes: int, fan_in: int, chain_depth: int, cross_passes: int
) -> tuple[list[tuple[int, int]], ...]:
    hub_count = max(1, nodes // fan_in)
    fan_pairs = [
        (bench_id(hub_count + index), bench_id(index % hub_count))
        for index in range(nodes - hub_count)
    ]
    chain_pairs = [(chain_id(index + 1), chain_id(index)) for index in range(chain_depth)]
    cross_pairs = [
        (bench_id(index), bench_id((index * (7 + 2 * step) + 3 + step) % max(1, nodes)))
        for step in range(cross_passes)
        for index in range(nodes)
    ]
    return fan_pairs, chain_pairs, cross_pairs


def run_perf(
    client: HydraClient,
    nodes: int = 10_000,
    fan_in: int = 40,
    chain_depth: int = 10,
    runs: int = 20,
    cross_passes: int = 2,
    delete_nodes: bool = False,
) -> PerfReport:
    writer = GraphWriter(client, Namespace.BENCH)
    fan_pairs, chain_pairs, cross_pairs = build_pairs(nodes, fan_in, chain_depth, cross_passes)
    before = client.metrics()
    started = time.perf_counter()
    write_edges(client, FAN_IN_EDGE, fan_pairs)
    write_edges(client, BENCH_EDGE, chain_pairs)
    write_edges(client, FAN_IN_EDGE, cross_pairs)
    write_seconds = time.perf_counter() - started
    after = client.metrics()

    edges = len(fan_pairs) + len(chain_pairs) + len(cross_pairs)
    node_ids = sorted({node for pair in fan_pairs + cross_pairs for node in pair})
    chain_ids = sorted({node for pair in chain_pairs for node in pair})
    report = PerfReport(
        measured_at=datetime.now(UTC).isoformat(),
        hydra_url=client.base_url,
        nodes_written=len(node_ids) + len(chain_ids),
        edges_written=edges,
        write_seconds=write_seconds,
        write_rows_per_second=edges / write_seconds if write_seconds else 0.0,
        engine_write_seconds=after.write_op_seconds_sum - before.write_op_seconds_sum,
    )

    hub = bench_id(0)
    report.samples.append(
        measure(
            client,
            NamedQuery(
                "bench_reverse_traversal",
                f"Reverse traversal: node <-{FAN_IN_EDGE}- fan-in",
                f"MATCH (hub {{id: $id}})<-[:{FAN_IN_EDGE}]-(source) RETURN source.id AS id",
            ),
            {"id": hub},
            runs,
        )
    )
    report.samples.append(
        measure(
            client,
            NamedQuery(
                "bench_variable_depth_chain",
                f"Variable-depth traversal: -{BENCH_EDGE}*1..10->",
                f"MATCH (head {{id: $id}})-[:{BENCH_EDGE}*1..10]->(older) RETURN older.id AS id",
            ),
            {"id": chain_id(chain_depth)},
            runs,
        )
    )
    report.samples.append(
        measure(
            client,
            NamedQuery(
                "bench_two_hop",
                "Two-hop neighborhood",
                f"MATCH (hub {{id: $id}})<-[:{FAN_IN_EDGE}]-(source)-[:{FAN_IN_EDGE}]->(other) "
                "RETURN other.id AS id",
            ),
            {"id": hub},
            runs,
        )
    )
    report.samples.append(
        measure(
            client,
            queries.count_nodes(NodeKind.CLAIM_KEY),
            {},
            runs,
        )
    )

    report.graph_counts = {
        str(kind): sum(
            1 for row in client.run(queries.namespaces_of(kind)).rows if row["namespace"] == "canon"
        )
        for kind in NodeKind
    }
    report.graph_counts.update(
        {
            str(edge): int(
                client.run(queries.count_edges_in_namespace(edge), {"namespace": "canon"}).scalar()
                or 0
            )
            for edge in EdgeType
        }
    )

    started = time.perf_counter()
    writer.delete_edges(FAN_IN_EDGE, fan_pairs + cross_pairs)
    writer.delete_edges(BENCH_EDGE, chain_pairs)
    report.edge_cleanup_seconds = time.perf_counter() - started
    if delete_nodes:
        started = time.perf_counter()
        writer.delete_nodes(node_ids + chain_ids, batch_size=CLEANUP_BATCH)
        report.node_cleanup_seconds = time.perf_counter() - started
    else:
        report.orphan_nodes_left = len(node_ids) + len(chain_ids)
    return report
