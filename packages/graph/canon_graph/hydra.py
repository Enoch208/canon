import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from itertools import count
from uuid import uuid4

Cell = int | float | str | bool | None | list["Cell"]
Row = dict[str, Cell]
Param = int | float | str | bool | list["Param"] | dict[str, "Param"]

DEFAULT_HTTP = "http://127.0.0.1:8443"
DEFAULT_METRICS = "http://127.0.0.1:9090/metrics"
DEFAULT_TOKEN = "local-development-token-32-bytes"
TRANSIENT_CODES = frozenset(
    {"not_cell_writer", "routing", "fencing", "contention", "internal", "query_timeout"}
)
TRANSIENT_RETRY_SECONDS = 60.0
WRITER_PROBE_ID = 4611686018427387900


class HydraError(RuntimeError):
    def __init__(self, code: str, message: str, query_name: str) -> None:
        super().__init__(f"{query_name}: {code}: {message}")
        self.code = code
        self.message = message
        self.query_name = query_name


class HydraUnreachableError(HydraError):
    def __init__(self, base_url: str, reason: str) -> None:
        super().__init__("unreachable", f"{base_url}: {reason}", "connect")


@dataclass(frozen=True, slots=True)
class NamedQuery:
    name: str
    operation: str
    cypher: str


@dataclass(frozen=True, slots=True)
class QueryResult:
    query: NamedQuery
    query_id: str
    columns: tuple[str, ...]
    rows: tuple[Row, ...]
    client_ms: float
    read_epoch: int | None

    def __len__(self) -> int:
        return len(self.rows)

    def column(self, name: str) -> list[Cell]:
        return [row[name] for row in self.rows]

    def scalar(self) -> Cell:
        if not self.rows:
            return None
        first = self.rows[0]
        return first[self.columns[0]]


@dataclass(frozen=True, slots=True)
class HydraMetrics:
    query_rows_duration_us_sum: float
    query_rows_duration_count: int
    read_op_seconds_sum: float
    read_op_count: int
    write_op_seconds_sum: float
    write_op_count: int
    query_started: int
    query_completed: int
    query_failed: int
    cache_entries: int
    cache_resident_bytes: int


def decode_cell(cell: dict[str, object]) -> Cell:
    cell_type = cell.get("type")
    if cell_type == "null":
        return None
    value = cell.get("value")
    if cell_type == "list":
        items = value if isinstance(value, list) else []
        return [decode_cell(item) for item in items if isinstance(item, dict)]
    if isinstance(value, int | float | str | bool):
        return value
    raise HydraError("decode", f"unsupported cell {cell!r}", "decode")


class HydraClient:
    def __init__(
        self,
        base_url: str = DEFAULT_HTTP,
        token: str = DEFAULT_TOKEN,
        metrics_url: str = DEFAULT_METRICS,
        cell_id: str = "cell-0",
        namespace: str = "default",
        graph: str = "default",
        timeout_seconds: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.metrics_url = metrics_url
        self.cell_id = cell_id
        self.namespace = namespace
        self.graph = graph
        self.timeout_seconds = timeout_seconds
        self._headers = {
            "Authorization": f"Bearer {token}",
            "X-Graph-Namespace": namespace,
            "Content-Type": "application/json",
        }
        self._session = uuid4().hex[:12]
        self._sequence = count(1)

    def next_query_id(self, query_name: str) -> str:
        return f"canon-{self._session}-{next(self._sequence)}-{query_name}"

    @classmethod
    def from_env(cls) -> "HydraClient":
        return cls(
            base_url=os.environ.get("HYDRA_HTTP", DEFAULT_HTTP),
            token=os.environ.get("HYDRA_TOKEN", DEFAULT_TOKEN),
            metrics_url=os.environ.get("HYDRA_METRICS", DEFAULT_METRICS),
        )

    @property
    def query_url(self) -> str:
        return f"{self.base_url}/v1/graphs/{self.graph}/query"

    def run(
        self,
        query: NamedQuery,
        params: dict[str, Param] | None = None,
        consistency: str | None = None,
    ) -> QueryResult:
        deadline = time.monotonic() + TRANSIENT_RETRY_SECONDS
        while True:
            try:
                return self._run_once(query, params, consistency)
            except HydraError as error:
                if error.code not in TRANSIENT_CODES or time.monotonic() >= deadline:
                    raise
                time.sleep(0.5)

    def _run_once(
        self,
        query: NamedQuery,
        params: dict[str, Param] | None,
        consistency: str | None,
    ) -> QueryResult:
        body: dict[str, object] = {
            "cell_id": self.cell_id,
            "query": query.cypher,
            "query_id": self.next_query_id(query.name),
        }
        if params:
            body["parameters"] = params
        if consistency:
            body["consistency"] = consistency
        request = urllib.request.Request(
            self.query_url,
            data=json.dumps(body).encode(),
            headers=self._headers,
            method="POST",
        )
        started = time.perf_counter()
        payload = self._send(request, query.name)
        elapsed_ms = (time.perf_counter() - started) * 1000
        error = payload.get("error")
        if isinstance(error, dict):
            raise HydraError(str(error.get("code")), str(error.get("message")), query.name)
        columns = tuple(str(name) for name in payload.get("columns") or [])
        raw_rows = payload.get("rows") or []
        rows = tuple(
            {columns[index]: decode_cell(cell) for index, cell in enumerate(raw_row)}
            for raw_row in raw_rows
        )
        epoch = payload.get("read_epoch")
        return QueryResult(
            query=query,
            query_id=str(payload.get("query_id") or ""),
            columns=columns,
            rows=rows,
            client_ms=elapsed_ms,
            read_epoch=epoch if isinstance(epoch, int) else None,
        )

    def _send(self, request: urllib.request.Request, query_name: str) -> dict[str, object]:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            body = error.read().decode()
            try:
                payload = json.loads(body)
            except json.JSONDecodeError as decode_error:
                raise HydraError(str(error.code), body, query_name) from decode_error
            detail = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(detail, dict):
                raise HydraError(
                    str(detail.get("code")), str(detail.get("message")), query_name
                ) from error
            raise HydraError(str(error.code), body, query_name) from error
        except urllib.error.URLError as error:
            raise HydraUnreachableError(self.base_url, str(error.reason)) from error
        except TimeoutError as error:
            raise HydraUnreachableError(self.base_url, "timeout") from error

    def healthy(self) -> bool:
        request = urllib.request.Request(f"{self.base_url}/healthz", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode()).get("status") == "ok"
        except (OSError, TimeoutError, json.JSONDecodeError):
            return False

    def wait_until_healthy(self, timeout_seconds: float = 60.0) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if self.healthy():
                return True
            time.sleep(0.5)
        return False

    def wait_until_writable(self, timeout_seconds: float = 120.0) -> bool:
        if not self.wait_until_healthy(timeout_seconds):
            return False
        probe = NamedQuery(
            "writer_probe",
            "CREATE writer probe",
            "CREATE (a:WriterProbe {id: $id})-[:PROBES]->(b:WriterProbe {id: $other})",
        )
        cleanup = NamedQuery(
            "writer_probe_cleanup",
            "DETACH DELETE writer probe",
            "MATCH (n:WriterProbe {id: $id}) DETACH DELETE n",
        )
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                self.run(probe, {"id": WRITER_PROBE_ID, "other": WRITER_PROBE_ID + 1})
            except HydraError:
                time.sleep(0.5)
                continue
            for node_id in (WRITER_PROBE_ID, WRITER_PROBE_ID + 1):
                self.run(cleanup, {"id": node_id})
            return True
        return False

    def metrics(self) -> HydraMetrics:
        request = urllib.request.Request(self.metrics_url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                text = response.read().decode()
        except (urllib.error.URLError, TimeoutError) as error:
            raise HydraUnreachableError(self.metrics_url, str(error)) from error
        return parse_metrics(text)


def parse_metrics(text: str) -> HydraMetrics:
    values: dict[str, float] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        name, _, raw = line.rpartition(" ")
        bare = name.split("{", 1)[0]
        try:
            values[bare] = values.get(bare, 0.0) + float(raw)
        except ValueError:
            continue
    return HydraMetrics(
        query_rows_duration_us_sum=values.get("graph_query_rows_duration_microseconds_sum", 0.0),
        query_rows_duration_count=int(
            values.get("graph_query_rows_duration_microseconds_count", 0)
        ),
        read_op_seconds_sum=values.get("graph_client_operation_read_duration_seconds_sum", 0.0),
        read_op_count=int(values.get("graph_client_operation_read_duration_seconds_count", 0)),
        write_op_seconds_sum=values.get("graph_client_operation_write_duration_seconds_sum", 0.0),
        write_op_count=int(values.get("graph_client_operation_write_duration_seconds_count", 0)),
        query_started=int(values.get("graph_query_started", 0)),
        query_completed=int(values.get("graph_query_completed", 0)),
        query_failed=int(values.get("graph_query_failed", 0)),
        cache_entries=int(values.get("graph_cache_entries", 0)),
        cache_resident_bytes=int(values.get("graph_cache_resident_bytes", 0)),
    )
