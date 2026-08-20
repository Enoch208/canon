from collections import Counter
from dataclasses import dataclass

from canon_graph.schema import (
    ExtractionMethod,
    Stance,
    TemporalQuality,
    Transition,
    TruthState,
)

CANDIDATE_STANCES = frozenset({Stance.CURRENT})


@dataclass(frozen=True, slots=True)
class AssertionInput:
    doc_id: str
    source_type: str
    value: str
    evidence_span: str
    stance: Stance
    structured: bool
    extraction_method: ExtractionMethod
    asserted_at: str | None = None
    source_field: str | None = None


@dataclass(frozen=True, slots=True)
class SupersessionSignal:
    doc_id: str
    from_value: str
    to_value: str
    evidence_span: str
    occurred_at: str | None = None


@dataclass(frozen=True, slots=True)
class ClaimBundle:
    entity_name: str
    entity_type: str
    key: str
    predicate: str
    question_id: str
    assertions: tuple[AssertionInput, ...]
    supersessions: tuple[SupersessionSignal, ...]
    temporal_quality: TemporalQuality


@dataclass(frozen=True, slots=True)
class EventPlan:
    value: str
    supersedes_value: str | None
    evidence_doc_id: str
    occurred_at: str | None


@dataclass(frozen=True, slots=True)
class CanonDecision:
    state: TruthState
    current_value: str | None
    retired_values: tuple[str, ...]
    contested_values: tuple[str, ...]
    transition: Transition
    temporal_quality: TemporalQuality
    events: tuple[EventPlan, ...]
    why: str


def candidate_values(bundle: ClaimBundle) -> tuple[str, ...]:
    ordered: dict[str, None] = {}
    for assertion in bundle.assertions:
        if assertion.stance in CANDIDATE_STANCES:
            ordered.setdefault(assertion.value, None)
    return tuple(ordered)


def canonize(bundle: ClaimBundle) -> CanonDecision:
    values = candidate_values(bundle)
    if not values:
        return _unknown(bundle)
    if len(values) == 1:
        return _single(bundle, values[0])
    explicit = _explicit_supersession(bundle, values)
    if explicit is not None:
        return explicit
    if bundle.temporal_quality is TemporalQuality.T1:
        dated = _dated_order(bundle, values)
        if dated is not None:
            return dated
    return _contested(bundle, values)


def _unknown(bundle: ClaimBundle) -> CanonDecision:
    return CanonDecision(
        state=TruthState.UNKNOWN,
        current_value=None,
        retired_values=(),
        contested_values=(),
        transition=Transition.NONE,
        temporal_quality=bundle.temporal_quality,
        events=(),
        why="no assertion with a CURRENT stance supports any value",
    )


def _single(bundle: ClaimBundle, value: str) -> CanonDecision:
    evidence = _first_assertion(bundle, value)
    return CanonDecision(
        state=TruthState.CANON,
        current_value=value,
        retired_values=(),
        contested_values=(),
        transition=Transition.NONE,
        temporal_quality=bundle.temporal_quality,
        events=(EventPlan(value, None, evidence.doc_id, evidence.asserted_at),),
        why=f"one value asserted as current in {_support_count(bundle, value)} assertion(s)",
    )


def _contested(bundle: ClaimBundle, values: tuple[str, ...]) -> CanonDecision:
    return CanonDecision(
        state=TruthState.CONTESTED,
        current_value=None,
        retired_values=(),
        contested_values=values,
        transition=Transition.NONE,
        temporal_quality=TemporalQuality.T3,
        events=(),
        why=(
            f"{len(values)} values conflict and neither explicit supersession language "
            "nor reliable ordering establishes which one won"
        ),
    )


def _explicit_supersession(bundle: ClaimBundle, values: tuple[str, ...]) -> CanonDecision | None:
    signals = [
        signal
        for signal in bundle.supersessions
        if signal.from_value in values and signal.to_value in values
    ]
    if not signals:
        return None
    superseded = {signal.from_value for signal in signals}
    sinks = [value for value in values if value not in superseded]
    if len(sinks) != 1:
        return None
    current = sinks[0]
    chain = _order_chain(signals, current)
    if set(chain) != set(values):
        return None
    events = _events_for_chain(bundle, signals, chain)
    quality = (
        TemporalQuality.T1 if bundle.temporal_quality is TemporalQuality.T1 else TemporalQuality.T2
    )
    signal_docs = sorted({signal.doc_id for signal in signals})
    return CanonDecision(
        state=TruthState.CANON,
        current_value=current,
        retired_values=tuple(value for value in chain if value != current),
        contested_values=(),
        transition=Transition.EXPLICIT_SUPERSESSION,
        temporal_quality=quality,
        events=events,
        why=(
            f"explicit supersession language in {', '.join(signal_docs)} names "
            f"{' -> '.join(chain)}; corroboration count was not consulted"
        ),
    )


def _order_chain(signals: list[SupersessionSignal], current: str) -> tuple[str, ...]:
    predecessors: dict[str, str] = {}
    for signal in signals:
        predecessors.setdefault(signal.to_value, signal.from_value)
    chain = [current]
    seen = {current}
    while chain[-1] in predecessors:
        previous = predecessors[chain[-1]]
        if previous in seen:
            break
        chain.append(previous)
        seen.add(previous)
    chain.reverse()
    return tuple(chain)


def _events_for_chain(
    bundle: ClaimBundle, signals: list[SupersessionSignal], chain: tuple[str, ...]
) -> tuple[EventPlan, ...]:
    events: list[EventPlan] = []
    for index, value in enumerate(chain):
        if index == 0:
            first = _first_assertion(bundle, value)
            events.append(EventPlan(value, None, first.doc_id, first.asserted_at))
            continue
        signal = next(
            s for s in signals if s.to_value == value and s.from_value == chain[index - 1]
        )
        occurred_at = signal.occurred_at or _first_assertion(bundle, value).asserted_at
        events.append(EventPlan(value, chain[index - 1], signal.doc_id, occurred_at))
    return tuple(events)


def _dated_order(bundle: ClaimBundle, values: tuple[str, ...]) -> CanonDecision | None:
    latest_by_value: dict[str, tuple[str, AssertionInput]] = {}
    for assertion in bundle.assertions:
        if assertion.stance not in CANDIDATE_STANCES or assertion.asserted_at is None:
            continue
        current = latest_by_value.get(assertion.value)
        if current is None or assertion.asserted_at > current[0]:
            latest_by_value[assertion.value] = (assertion.asserted_at, assertion)
    if set(latest_by_value) != set(values):
        return None
    ranked = sorted(latest_by_value.items(), key=lambda item: item[1][0], reverse=True)
    top_date = ranked[0][1][0]
    tied = [value for value, (date, _) in ranked if date == top_date]
    transition = Transition.TEMPORAL_ORDER
    if len(tied) > 1:
        support = Counter(
            assertion.value
            for assertion in bundle.assertions
            if assertion.stance in CANDIDATE_STANCES
        )
        best = max(support[value] for value in tied)
        leaders = [value for value in tied if support[value] == best]
        if len(leaders) != 1:
            return None
        ranked.sort(key=lambda item: (item[1][0], support[item[0]]), reverse=True)
        transition = Transition.CORROBORATION_TIEBREAK
    all_structured = all(assertion.structured for _, assertion in latest_by_value.values())
    if all_structured and transition is Transition.TEMPORAL_ORDER:
        transition = Transition.STRUCTURED_TRANSITION
    chain = tuple(value for value, _ in reversed(ranked))
    current = chain[-1]
    events: list[EventPlan] = []
    for index, value in enumerate(chain):
        _, assertion = latest_by_value[value]
        events.append(
            EventPlan(
                value,
                chain[index - 1] if index else None,
                assertion.doc_id,
                assertion.asserted_at,
            )
        )
    return CanonDecision(
        state=TruthState.CANON,
        current_value=current,
        retired_values=chain[:-1],
        contested_values=(),
        transition=transition,
        temporal_quality=TemporalQuality.T1,
        events=tuple(events),
        why=(
            f"T1 dated assertions order values {' -> '.join(chain)}"
            + (
                "; corroboration broke a same-date tie"
                if transition is Transition.CORROBORATION_TIEBREAK
                else ""
            )
        ),
    )


def _first_assertion(bundle: ClaimBundle, value: str) -> AssertionInput:
    for assertion in bundle.assertions:
        if assertion.value == value and assertion.stance in CANDIDATE_STANCES:
            return assertion
    raise ValueError(f"no current assertion for {value!r} in {bundle.key}")


def _support_count(bundle: ClaimBundle, value: str) -> int:
    return sum(
        1
        for assertion in bundle.assertions
        if assertion.value == value and assertion.stance in CANDIDATE_STANCES
    )
