#!/usr/bin/env python3
import sys

from canon_graph.hydra import HydraClient


def main() -> int:
    client = HydraClient.from_env()
    if not client.wait_until_writable(180):
        print(f"HydraDB at {client.base_url} did not accept writes within 180s")
        return 1
    print(f"HydraDB ready at {client.base_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
