import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from canon_graph.canonize import AssertionInput, ClaimBundle, SupersessionSignal, canonize
from canon_graph.hydra import HydraClient
from canon_graph.ids import Namespace, proposition_id
from canon_graph.ingest import GraphWriter
from canon_graph.resolve import GraphReader
from canon_graph.schema import (
    ExtractionMethod,
    ResidueClass,
    Stance,
    TemporalQuality,
    Transition,
    TruthState,
)

PRICE_KEY = "VerifyCo Nova.price_per_1k_tokens"
LAUNCH_KEY = "VerifyCo Atlas.launch_date"
NEVER_KEY = "VerifyCo Atlas.never_asserted"


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: str
    elapsed_ms: float


@dataclass(slots=True)
class VerifyReport:
    started_at: str
    hydra_url: str
    checks: list[CheckResult] = field(default_factory=list)
    graph_writes: int = 0
    query_cards: list[dict[str, object]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def as_dict(self) -> dict[str, object]:
        return {
            "started_at": self.started_at,
            "hydra_url": self.hydra_url,
            "passed": self.passed,
            "checks": [asdict(check) for check in self.checks],
            "graph_writes": self.graph_writes,
            "query_cards": self.query_cards,
        }


def structured_assertion(
    doc_id: str, value: str, asserted_at: str, source_field: str
) -> AssertionInput:
    return AssertionInput(
        doc_id=doc_id,
        source_type="jira",
        value=value,
        evidence_span=f"{source_field}: {value}",
        stance=Stance.CURRENT,
        structured=True,
        extraction_method=ExtractionMethod.STRUCTURED_FIELD,
        asserted_at=asserted_at,
        source_field=source_field,
    )


def majority_bundle() -> ClaimBundle:
    old = tuple(
        structured_assertion(f"verify_old_{i}", "$0.08", f"2026-01-0{i + 1}", "price")
        for i in range(8)
    )
    update = structured_assertion("verify_update", "$0.06", "2026-02-01", "price")
    signal = SupersessionSignal(
        "verify_update", "$0.08", "$0.06", "price changed from $0.08 to $0.06", "2026-02-01"
    )
    return ClaimBundle(
        entity_name="VerifyCo Nova",
        entity_type="Product",
        key=PRICE_KEY,
        predicate="price_per_1k_tokens",
        question_id="verify_majority",
        assertions=(*old, update),
        supersessions=(signal,),
        temporal_quality=TemporalQuality.T1,
    )


def contested_bundle() -> ClaimBundle:
    return ClaimBundle(
        entity_name="VerifyCo Atlas",
        entity_type="Project",
        key=LAUNCH_KEY,
        predicate="launch_date",
        question_id="verify_contested",
        assertions=(
            structured_assertion("verify_c1", "Sep 18", "2026-03-01", "due_date"),
            structured_assertion("verify_c2", "Sep 21", "2026-03-01", "due_date"),
        ),
        supersessions=(),
        temporal_quality=TemporalQuality.T3,
    )


class Verifier:
    def __init__(self, client: HydraClient, restart: Callable[[], None]) -> None:
        self.client = client
        self.restart = restart
        self.writer = GraphWriter(client, Namespace.VERIFY)
        self.reader = GraphReader(client)
        self.report = VerifyReport(datetime.now(UTC).isoformat(), client.base_url)

    def _check(self, name: str, run: Callable[[], tuple[bool, str]]) -> None:
        started = time.perf_counter()
        try:
            passed, detail = run()
        except Exception as error:
            passed, detail = False, f"{type(error).__name__}: {error}"
        elapsed = (time.perf_counter() - started) * 1000
        self.report.checks.append(CheckResult(name, passed, detail, round(elapsed, 1)))
        self.report.query_cards.extend(card.as_dict() for card in self.reader.take_cards())

    def run(self) -> VerifyReport:
        self.writer.purge_namespace()
        try:
            self._check("HydraDB write/read", self.check_write_read)
            self._check("Persistence", self.check_persistence)
            self._check("Supersession", self.check_supersession)
            self._check("Majority adversarial", self.check_majority)
            self._check("Residue traversal", self.check_residue)
            self._check("UNKNOWN", self.check_unknown)
            self._check("CONTESTED", self.check_contested)
        finally:
            self.report.graph_writes = self.writer.report.nodes_created
            self.writer.purge_namespace()
        return self.report

    def check_write_read(self) -> tuple[bool, str]:
        bundle = majority_bundle()
        self.writer.write_claim(bundle, canonize(bundle), {})
        claim_key = self.reader.claim_key(PRICE_KEY)
        if claim_key is None:
            return False, "claim key not readable after write"
        evidence = self.reader.evidence(self.writer_proposition("$0.08"))
        written = self.writer.report.nodes_created
        return len(evidence) == 8, f"wrote {written} nodes, read back {len(evidence)} assertions"

    def writer_proposition(self, value: str) -> int:
        return proposition_id(PRICE_KEY, value, Namespace.VERIFY)

    def check_persistence(self) -> tuple[bool, str]:
        self.restart()
        if not self.client.wait_until_writable(180):
            return False, "HydraDB did not accept writes after restart"
        claim_key = self.reader.claim_key(PRICE_KEY)
        if claim_key is None:
            return False, "claim key lost after restart"
        evidence = self.reader.evidence(self.writer_proposition("$0.08"))
        return len(evidence) == 8, f"after restart: {len(evidence)} assertions still readable"

    def check_supersession(self) -> tuple[bool, str]:
        claim_key = self.reader.claim_key(PRICE_KEY)
        if claim_key is None:
            return False, "claim key missing"
        resolution = self.reader.resolve(claim_key)
        chain_ok = (
            len(resolution.events) == 2
            and resolution.events[1].supersedes_event_id == resolution.events[0].id
        )
        values = [p.value for p in resolution.retired] + (
            [resolution.current.value] if resolution.current else []
        )
        return chain_ok, f"SUPERSEDES chain {' -> '.join(values)} via {resolution.transition}"

    def check_majority(self) -> tuple[bool, str]:
        claim_key = self.reader.claim_key(PRICE_KEY)
        if claim_key is None:
            return False, "claim key missing"
        resolution = self.reader.resolve(claim_key)
        current = resolution.current.value if resolution.current else None
        passed = (
            resolution.state is TruthState.CANON
            and current == "$0.06"
            and resolution.transition is Transition.EXPLICIT_SUPERSESSION
        )
        return passed, f"8 assertions of $0.08 vs 1 explicit update -> CURRENT={current}"

    def check_residue(self) -> tuple[bool, str]:
        residue = AssertionInput(
            doc_id="verify_residue_doc",
            source_type="hubspot",
            value="$0.08",
            evidence_span="unit_price: $0.08",
            stance=Stance.CURRENT,
            structured=True,
            extraction_method=ExtractionMethod.STRUCTURED_FIELD,
            source_field="unit_price",
        )
        retired_id = self.writer_proposition("$0.08")
        assertion_id = self.writer.write_assertion(
            PRICE_KEY, retired_id, residue, "Quote 42", ResidueClass.VERIFIED_STRUCTURED
        )
        rows = self.reader.residue(retired_id)
        proof = self.reader.proof_path(assertion_id)
        passed = [r.assertion.doc_id for r in rows] == ["verify_residue_doc"] and len(proof) == 1
        return (
            passed,
            f"reverse traversal found {len(rows)} residue row(s); proof rows={len(proof)}",
        )

    def check_unknown(self) -> tuple[bool, str]:
        claim_key = self.reader.claim_key(NEVER_KEY)
        return claim_key is None, f"{NEVER_KEY} -> {TruthState.UNKNOWN}"

    def check_contested(self) -> tuple[bool, str]:
        bundle = contested_bundle()
        decision = canonize(bundle)
        self.writer.write_claim(bundle, decision, {})
        claim_key = self.reader.claim_key(LAUNCH_KEY)
        if claim_key is None:
            return False, "contested claim key missing"
        resolution = self.reader.resolve(claim_key)
        passed = resolution.state is TruthState.CONTESTED and resolution.current is None
        return passed, f"two same-date T3 values -> {resolution.state}"
