import re
from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from canon_extraction.structured import line_bounds
from canon_extraction.values import normalize

BINDING = re.compile(
    r"([A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){0,3})\s*<\s*"
    r"([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})\s*>"
)
TITLE_PREFIX = re.compile(r"^(?:AM|PM|Dr|Mr|Ms|Mrs|Prof)\.?\s+", re.IGNORECASE)
NAME_SEPARATOR = re.compile(r"[.\-_']+")
WHITESPACE = re.compile(r"\s+")
MIN_NAME_WORDS = 2
MAX_SPAN_CHARS = 300


class AliasType(StrEnum):
    EMAIL = "email"
    DISPLAY_NAME = "display_name"
    LOCAL_PART = "local_part"


class Resolution(StrEnum):
    RESOLVED = "RESOLVED"
    PROBABLE = "PROBABLE"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class Binding:
    display_name: str
    email: str
    doc_id: str
    source_type: str
    evidence_span: str


@dataclass(frozen=True, slots=True)
class PersonIdentity:
    name: str
    organization: str

    @property
    def key(self) -> str:
        return f"{self.name}@{self.organization}"


@dataclass(frozen=True, slots=True)
class ResolvedAlias:
    value: str
    alias_type: AliasType
    resolution: Resolution
    candidates: tuple[PersonIdentity, ...]
    support: int
    evidence_doc_id: str
    evidence_span: str

    @property
    def person(self) -> PersonIdentity | None:
        return self.candidates[0] if len(self.candidates) == 1 else None


@dataclass(frozen=True, slots=True)
class IdentityGraph:
    people: tuple[PersonIdentity, ...]
    aliases: tuple[ResolvedAlias, ...]
    documents_scanned: int
    bindings_found: int

    def counts(self) -> dict[str, int]:
        return {
            str(state): sum(1 for a in self.aliases if a.resolution is state)
            for state in Resolution
        }


def organization_of(email: str) -> str:
    return email.split("@", 1)[1].lower()


def normalize_name(display_name: str) -> str:
    stripped = TITLE_PREFIX.sub("", normalize(display_name))
    return WHITESPACE.sub(" ", NAME_SEPARATOR.sub(" ", stripped)).strip().lower()


def name_from_local_part(email: str) -> str:
    return WHITESPACE.sub(" ", NAME_SEPARATOR.sub(" ", email.split("@", 1)[0])).strip().lower()


def line_of(text: str, position: int) -> str:
    start, end = line_bounds(text, position)
    return text[start:end].strip(" \t\r\\")[:MAX_SPAN_CHARS]


def extract_bindings(doc_id: str, source_type: str, content: str) -> list[Binding]:
    bindings: list[Binding] = []
    for match in BINDING.finditer(content):
        display_name = normalize(match.group(1))
        if len(normalize_name(display_name).split(" ")) < MIN_NAME_WORDS:
            continue
        bindings.append(
            Binding(
                display_name=display_name,
                email=match.group(2).lower(),
                doc_id=doc_id,
                source_type=source_type,
                evidence_span=line_of(content, match.start()),
            )
        )
    return bindings


def resolve(bindings: list[Binding], documents_scanned: int) -> IdentityGraph:
    by_email: dict[str, list[Binding]] = defaultdict(list)
    for binding in bindings:
        by_email[binding.email].append(binding)

    person_of_email: dict[str, PersonIdentity] = {}
    for email, rows in by_email.items():
        name = normalize_name(rows[0].display_name)
        person_of_email[email] = PersonIdentity(name, organization_of(email))

    candidates: dict[tuple[str, AliasType], set[PersonIdentity]] = defaultdict(set)
    evidence: dict[tuple[str, AliasType], Binding] = {}
    support: dict[tuple[str, AliasType], int] = defaultdict(int)

    def record(
        value: str,
        alias_type: AliasType,
        person: PersonIdentity,
        binding: Binding,
        weight: int = 1,
    ) -> None:
        key = (value, alias_type)
        candidates[key].add(person)
        support[key] += weight
        evidence.setdefault(key, binding)

    for email, rows in by_email.items():
        person = person_of_email[email]
        record(email, AliasType.EMAIL, person, rows[0], weight=len(rows))
        local = name_from_local_part(email)
        if len(local.split(" ")) >= MIN_NAME_WORDS:
            record(local, AliasType.LOCAL_PART, person, rows[0], weight=len(rows))
        for binding in rows:
            record(normalize_name(binding.display_name), AliasType.DISPLAY_NAME, person, binding)

    aliases: list[ResolvedAlias] = []
    for (value, alias_type), people in candidates.items():
        ordered = tuple(sorted(people, key=lambda p: p.key))
        if len(ordered) > 1:
            resolution = Resolution.AMBIGUOUS
        elif alias_type is AliasType.EMAIL:
            resolution = Resolution.RESOLVED
        else:
            resolution = Resolution.PROBABLE
        binding = evidence[(value, alias_type)]
        aliases.append(
            ResolvedAlias(
                value=value,
                alias_type=alias_type,
                resolution=resolution,
                candidates=ordered,
                support=support[(value, alias_type)],
                evidence_doc_id=binding.doc_id,
                evidence_span=binding.evidence_span,
            )
        )

    people = tuple(sorted(set(person_of_email.values()), key=lambda p: p.key))
    aliases.sort(key=lambda a: (a.resolution, a.alias_type, a.value))
    return IdentityGraph(people, tuple(aliases), documents_scanned, len(bindings))
