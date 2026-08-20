from collections.abc import Iterator

import pytest

from canon_graph.hydra import HydraClient
from canon_graph.ids import Namespace
from canon_graph.ingest import GraphWriter


@pytest.fixture(scope="session")
def hydra() -> HydraClient:
    client = HydraClient.from_env()
    if not client.healthy():
        pytest.skip(f"HydraDB not reachable at {client.base_url}; run `make hydra-up`")
    return client


@pytest.fixture
def verify_writer(hydra: HydraClient) -> Iterator[GraphWriter]:
    writer = GraphWriter(hydra, Namespace.VERIFY)
    writer.purge_namespace()
    yield writer
    writer.purge_namespace()
