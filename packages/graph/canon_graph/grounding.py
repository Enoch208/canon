import re
from dataclasses import dataclass, field
from enum import StrEnum

from canon_graph.querycard import HydraQueryCard
from canon_graph.resolve import ArtifactClaim, GraphReader, Resolution
from canon_graph.schema import ClaimKey, Discovery, PropositionStatus, Stance, TruthState

WORD = re.compile(r"[a-z0-9][a-z0-9\-]*")
QUESTION_STOPWORD_TEXT = (
    "what which when where who how why is are was were the a an of for in on to and or does "
    "do did should would could must our we you your their there these those into than then them "
    "they about after before between during over under with from by as at be has have it its this "
    "that apply applies current currently now still"
)
QUESTION_STOPWORDS = frozenset(QUESTION_STOPWORD_TEXT.split())
MIN_CLAIM_KEY_TERMS = 3
MIN_CLAIM_KEY_COVERAGE = 0.5


class GroundingMode(StrEnum):
    CURRENT = "current"
    HISTORICAL = "historical"


class DocDisposition(StrEnum):
    CURRENT_EVIDENCE = "current_evidence"
    SUPERSEDED = "superseded_for_current_grounding"
    HISTORICAL_EVIDENCE = "historical_evidence"
    CONTESTED_EVIDENCE = "contested_evidence"
    UNLINKED = "not_in_claim_graph"


KEPT_FOR_MODE = {
    GroundingMode.CURRENT: frozenset(
        {
            DocDisposition.CURRENT_EVIDENCE,
            DocDisposition.CONTESTED_EVIDENCE,
            DocDisposition.UNLINKED,
        }
    ),
    GroundingMode.HISTORICAL: frozenset(
        {
            DocDisposition.HISTORICAL_EVIDENCE,
            DocDisposition.SUPERSEDED,
            DocDisposition.CONTESTED_EVIDENCE,
            DocDisposition.UNLINKED,
        }
    ),
}


@dataclass(frozen=True, slots=True)
class DocGrounding:
    doc_id: str
    disposition: DocDisposition
    claims: tuple[ArtifactClaim, ...]


@dataclass(frozen=True, slots=True)
class ClaimKeyMatch:
    claim_key: ClaimKey
    score: int
    coverage: float
    matched_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Grounding:
    mode: GroundingMode
    state: TruthState
    resolutions: tuple[Resolution, ...]
    docs: tuple[DocGrounding, ...]
    pinned_doc_ids: tuple[str, ...]
    claim_key_matches: tuple[ClaimKeyMatch, ...]
    query_cards: tuple[HydraQueryCard, ...] = field(default_factory=tuple)

    @property
    def kept_doc_ids(self) -> tuple[str, ...]:
        wanted = KEPT_FOR_MODE[self.mode]
        return tuple(doc.doc_id for doc in self.docs if doc.disposition in wanted)

    @property
    def dropped_doc_ids(self) -> tuple[str, ...]:
        kept = set(self.kept_doc_ids)
        return tuple(doc.doc_id for doc in self.docs if doc.doc_id not in kept)

    @property
    def primary(self) -> Resolution | None:
        return self.resolutions[0] if self.resolutions else None


def question_terms(question: str) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for token in WORD.findall(question.lower()):
        cleaned = token.strip("-")
        if len(cleaned) >= 3 and cleaned not in QUESTION_STOPWORDS:
            seen.setdefault(cleaned, None)
    return tuple(seen)


def claim_key_terms(claim_key: ClaimKey) -> tuple[str, ...]:
    return question_terms(claim_key.key.replace("_", " ").replace(".", " "))


def match_claim_keys(question: str, claim_keys: tuple[ClaimKey, ...]) -> tuple[ClaimKeyMatch, ...]:
    asked = set(question_terms(question))
    matches: list[ClaimKeyMatch] = []
    for claim_key in claim_keys:
        terms = claim_key_terms(claim_key)
        if not terms:
            continue
        matched = tuple(term for term in terms if term in asked)
        coverage = len(matched) / len(terms)
        if len(matched) >= MIN_CLAIM_KEY_TERMS and coverage >= MIN_CLAIM_KEY_COVERAGE:
            matches.append(ClaimKeyMatch(claim_key, len(matched), round(coverage, 3), matched))
    matches.sort(key=lambda match: (-match.coverage, -match.score, match.claim_key.key))
    return tuple(matches)


def best_claim_key(matches: tuple[ClaimKeyMatch, ...]) -> ClaimKey | None:
    if not matches:
        return None
    if len(matches) > 1 and (matches[0].coverage, matches[0].score) == (
        matches[1].coverage,
        matches[1].score,
    ):
        return None
    return matches[0].claim_key


def disposition_for(
    claims: tuple[ArtifactClaim, ...], resolutions_by_key: dict[int, Resolution]
) -> DocDisposition:
    if not claims:
        return DocDisposition.UNLINKED
    asserts_current = False
    asserts_retired = False
    resolved_any = False
    for claim in claims:
        resolution = resolutions_by_key.get(claim.claim_key_id)
        if resolution is None or resolution.state is not TruthState.CANON:
            continue
        resolved_any = True
        current_id = resolution.current.id if resolution.current else None
        if claim.proposition_id == current_id:
            asserts_current = True
        elif claim.status is PropositionStatus.RETIRED and claim.stance in (
            Stance.CURRENT,
            Stance.UNCERTAIN,
        ):
            asserts_retired = True
    if not resolved_any:
        return DocDisposition.CONTESTED_EVIDENCE
    if asserts_current:
        return DocDisposition.CURRENT_EVIDENCE
    if asserts_retired:
        return DocDisposition.SUPERSEDED
    return DocDisposition.HISTORICAL_EVIDENCE


def ground(
    reader: GraphReader,
    question: str,
    doc_ids: tuple[str, ...],
    mode: GroundingMode = GroundingMode.CURRENT,
    pin_graph_evidence: bool = False,
    namespace: str = "canon",
) -> Grounding:
    first_card = len(reader.cards)
    claims_by_doc = {doc_id: reader.artifact_claims(doc_id) for doc_id in doc_ids}
    all_keys = reader.all_claim_keys(namespace)
    keys_by_id = {claim_key.id: claim_key for claim_key in all_keys}
    matches = match_claim_keys(question, all_keys)
    chosen = best_claim_key(matches)
    touched: dict[int, None] = {}
    if chosen is not None:
        touched.setdefault(chosen.id, None)
    for claims in claims_by_doc.values():
        for claim in claims:
            touched.setdefault(claim.claim_key_id, None)
    resolutions = tuple(
        reader.resolve(keys_by_id[claim_key_id])
        for claim_key_id in touched
        if claim_key_id in keys_by_id
    )
    by_key = {resolution.claim_key.id: resolution for resolution in resolutions}
    docs = tuple(
        DocGrounding(doc_id, disposition_for(claims, by_key), claims)
        for doc_id, claims in claims_by_doc.items()
    )
    pinned = pinned_evidence(resolutions, doc_ids, mode) if pin_graph_evidence else ()
    return Grounding(
        mode=mode,
        state=_overall_state(resolutions),
        resolutions=resolutions,
        docs=docs,
        pinned_doc_ids=pinned,
        claim_key_matches=matches,
        query_cards=reader.cards_since(first_card),
    )


def pinned_evidence(
    resolutions: tuple[Resolution, ...], doc_ids: tuple[str, ...], mode: GroundingMode
) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for resolution in resolutions:
        rows = (
            resolution.current_evidence
            if mode is GroundingMode.CURRENT
            else resolution.retired_evidence
        )
        for row in rows:
            if (
                row.assertion.doc_id not in doc_ids
                and row.assertion.discovery is Discovery.CONFLICT_PAIR
            ):
                seen.setdefault(row.assertion.doc_id, None)
    return tuple(seen)


def _overall_state(resolutions: tuple[Resolution, ...]) -> TruthState:
    return resolutions[0].state if resolutions else TruthState.UNKNOWN
