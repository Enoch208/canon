from canon_graph.canonize import (
    AssertionInput,
    ClaimBundle,
    SupersessionSignal,
    canonize,
)
from canon_graph.schema import ExtractionMethod, Stance, TemporalQuality, Transition, TruthState


def assertion(
    doc_id: str,
    value: str,
    stance: Stance = Stance.CURRENT,
    asserted_at: str | None = None,
    structured: bool = False,
) -> AssertionInput:
    return AssertionInput(
        doc_id=doc_id,
        source_type="jira",
        value=value,
        evidence_span=f"price = {value}",
        stance=stance,
        structured=structured,
        extraction_method=ExtractionMethod.STRUCTURED_FIELD
        if structured
        else ExtractionMethod.LEXICAL_SPAN,
        asserted_at=asserted_at,
    )


def bundle(
    assertions: tuple[AssertionInput, ...],
    supersessions: tuple[SupersessionSignal, ...] = (),
    quality: TemporalQuality = TemporalQuality.T2,
) -> ClaimBundle:
    return ClaimBundle(
        entity_name="Nova",
        entity_type="Product",
        key="Nova.price",
        predicate="price",
        question_id="test",
        assertions=assertions,
        supersessions=supersessions,
        temporal_quality=quality,
    )


def test_majority_cannot_override_explicit_supersession() -> None:
    old_eight = tuple(
        assertion(f"doc_{i}", "$0.08", asserted_at="2026-01-0" + str(i + 1)) for i in range(8)
    )
    update = assertion("doc_update", "$0.06", asserted_at="2026-02-01")
    signal = SupersessionSignal(
        doc_id="doc_update",
        from_value="$0.08",
        to_value="$0.06",
        evidence_span="price changed from $0.08 to $0.06",
        occurred_at="2026-02-01",
    )
    decision = canonize(bundle((*old_eight, update), (signal,)))
    assert decision.state is TruthState.CANON
    assert decision.current_value == "$0.06"
    assert decision.retired_values == ("$0.08",)
    assert decision.transition is Transition.EXPLICIT_SUPERSESSION
    assert decision.temporal_quality is TemporalQuality.T2
    assert [event.value for event in decision.events] == ["$0.08", "$0.06"]
    assert decision.events[1].supersedes_value == "$0.08"
    assert decision.events[1].evidence_doc_id == "doc_update"


def test_explicit_supersession_keeps_t1_when_input_is_t1() -> None:
    decision = canonize(
        bundle(
            (
                assertion("a", "20%", asserted_at="2026-03-11"),
                assertion("b", "30%", asserted_at="2026-03-12"),
            ),
            (
                SupersessionSignal(
                    "b", "20%", "30%", "reserve 30% (previous internal suggestion was 20%)"
                ),
            ),
            TemporalQuality.T1,
        )
    )
    assert decision.temporal_quality is TemporalQuality.T1
    assert decision.current_value == "30%"


def test_two_values_without_ordering_evidence_are_contested() -> None:
    decision = canonize(bundle((assertion("a", "X"), assertion("b", "Y"), assertion("c", "Y"))))
    assert decision.state is TruthState.CONTESTED
    assert decision.current_value is None
    assert set(decision.contested_values) == {"X", "Y"}
    assert decision.temporal_quality is TemporalQuality.T3


def test_majority_alone_never_picks_a_winner_when_order_is_unreliable() -> None:
    dated = (
        assertion("a", "X", asserted_at="2026-01-01"),
        assertion("b", "Y", asserted_at="2026-02-01"),
        assertion("c", "Y", asserted_at="2026-02-02"),
    )
    decision = canonize(bundle(dated, quality=TemporalQuality.T2))
    assert decision.state is TruthState.CONTESTED


def test_t1_dates_order_values_when_no_explicit_language() -> None:
    dated = (
        assertion("a", "X", asserted_at="2026-01-01"),
        assertion("b", "Y", asserted_at="2026-02-01"),
    )
    decision = canonize(bundle(dated, quality=TemporalQuality.T1))
    assert decision.state is TruthState.CANON
    assert decision.current_value == "Y"
    assert decision.retired_values == ("X",)
    assert decision.transition is Transition.TEMPORAL_ORDER


def test_t1_structured_fields_record_structured_transition() -> None:
    dated = (
        assertion("a", "X", asserted_at="2026-01-01", structured=True),
        assertion("b", "Y", asserted_at="2026-02-01", structured=True),
    )
    decision = canonize(bundle(dated, quality=TemporalQuality.T1))
    assert decision.transition is Transition.STRUCTURED_TRANSITION


def test_same_date_tie_uses_corroboration_only_as_tiebreak() -> None:
    dated = (
        assertion("a", "X", asserted_at="2026-02-01"),
        assertion("b", "Y", asserted_at="2026-02-01"),
        assertion("c", "Y", asserted_at="2026-01-15"),
    )
    decision = canonize(bundle(dated, quality=TemporalQuality.T1))
    assert decision.state is TruthState.CANON
    assert decision.current_value == "Y"
    assert decision.transition is Transition.CORROBORATION_TIEBREAK


def test_same_date_and_same_support_is_contested() -> None:
    dated = (
        assertion("a", "X", asserted_at="2026-02-01"),
        assertion("b", "Y", asserted_at="2026-02-01"),
    )
    decision = canonize(bundle(dated, quality=TemporalQuality.T1))
    assert decision.state is TruthState.CONTESTED


def test_historical_and_rejected_stances_are_not_candidates() -> None:
    mixed = (
        assertion("a", "X", stance=Stance.HISTORICAL),
        assertion("b", "X", stance=Stance.REJECTED),
        assertion("c", "Y"),
    )
    decision = canonize(bundle(mixed))
    assert decision.state is TruthState.CANON
    assert decision.current_value == "Y"
    assert decision.transition is Transition.NONE


def test_no_current_assertion_is_unknown() -> None:
    decision = canonize(bundle((assertion("a", "X", stance=Stance.PROPOSED),)))
    assert decision.state is TruthState.UNKNOWN
    assert decision.events == ()


def test_three_value_chain_from_two_signals() -> None:
    values = (assertion("a", "1"), assertion("b", "2"), assertion("c", "3"))
    signals = (
        SupersessionSignal("b", "1", "2", "moved from 1 to 2"),
        SupersessionSignal("c", "2", "3", "moved from 2 to 3"),
    )
    decision = canonize(bundle(values, signals))
    assert decision.current_value == "3"
    assert decision.retired_values == ("1", "2")
    assert [event.supersedes_value for event in decision.events] == [None, "1", "2"]


def test_conflicting_signals_with_two_sinks_are_contested() -> None:
    values = (assertion("a", "1"), assertion("b", "2"), assertion("c", "3"))
    signals = (SupersessionSignal("b", "1", "2", "moved from 1 to 2"),)
    decision = canonize(bundle(values, signals))
    assert decision.state is TruthState.CONTESTED
