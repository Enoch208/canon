#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

from canon_graph.hydra import HydraClient
from canon_graph.verify import Verifier

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence" / "verify.json"


def restart_hydra() -> None:
    subprocess.run(
        ["docker", "compose", "restart", "hydradb"], cwd=ROOT, check=True, capture_output=True
    )


def main() -> int:
    client = HydraClient.from_env()
    if not client.healthy():
        print(f"HydraDB unreachable at {client.base_url}; run `make hydra-up`")
        return 2
    report = Verifier(client, restart_hydra).run()
    width = max(len(check.name) for check in report.checks) + 4
    for check in report.checks:
        dots = "." * (width - len(check.name))
        status = "PASS" if check.passed else "FAIL"
        print(f"{check.name} {dots} {status}  ({check.elapsed_ms:.0f} ms)  {check.detail}")
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report.as_dict(), indent=2) + "\n")
    print(f"evidence: {EVIDENCE.relative_to(ROOT)}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
