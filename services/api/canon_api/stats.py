import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class GraphStats:
    measured_at: str | None
    counts: dict[str, int]


def load_graph_stats(path: Path) -> GraphStats:
    if not path.exists():
        return GraphStats(None, {})
    payload = json.loads(path.read_text())
    counts = {str(key): int(value) for key, value in payload.get("counts", {}).items()}
    measured_at = payload.get("measured_at")
    return GraphStats(str(measured_at) if measured_at else None, counts)
