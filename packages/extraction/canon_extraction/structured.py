import re
from dataclasses import dataclass

from canon_graph.schema import ResidueClass

STRUCTURED_SOURCES = frozenset({"jira", "linear", "hubspot"})
FIELD_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_ ]{0,40}):\s*(\S.*)$")
MAX_STRUCTURED_VALUE_CHARS = 160

HISTORICAL_MARKERS = (
    "previously",
    "originally",
    "formerly",
    "used to be",
    "prior to",
    "outdated",
    "old doc says",
    "older",
    "legacy",
    "was set to",
    "earlier suggestion",
    "previous internal suggestion",
    "previous",
)
REJECTED_MARKERS = (
    "no longer",
    "superseded",
    "deprecated",
    "instead of",
    "changed from",
    "moved from",
    "updated from",
    "replaced",
    "rather than",
    "is wrong",
    "incorrect",
)
NEGATION_MARKERS = ("not ", "n't ", "never ", "cannot")


@dataclass(frozen=True, slots=True)
class LineMatch:
    line_no: int
    line: str
    field_name: str | None
    structured: bool
    residue_class: ResidueClass


LINE_BREAKS = ("\n", "\\n")
MAX_VERIFIED_LINE_CHARS = 300


def line_bounds(text: str, position: int) -> tuple[int, int]:
    starts = [
        found + len(token)
        for token, found in ((token, text.rfind(token, 0, position)) for token in LINE_BREAKS)
        if found >= 0
    ]
    ends = [index for index in (text.find(token, position) for token in LINE_BREAKS) if index >= 0]
    return (max(starts) if starts else 0), (min(ends) if ends else len(text))


def line_containing(text: str, position: int) -> tuple[int, str]:
    start, end = line_bounds(text, position)
    line_no = sum(text.count(token, 0, start) for token in LINE_BREAKS) + 1
    return line_no, text[start:end].strip(" \t\r\\")


def field_of(line: str) -> tuple[str, str] | None:
    match = FIELD_LINE.match(line)
    if not match:
        return None
    return match.group(1).strip().lower(), match.group(2).strip()


def is_structured_field_line(source_type: str, line: str) -> tuple[bool, str | None]:
    if source_type not in STRUCTURED_SOURCES:
        return False, None
    field = field_of(line)
    if field is None:
        return False, None
    name, value = field
    return len(value) <= MAX_STRUCTURED_VALUE_CHARS, name


def is_question(line: str) -> bool:
    return line.rstrip().endswith("?")


def classify_line(source_type: str, line: str) -> tuple[ResidueClass, bool, str | None]:
    lowered = line.lower()
    if is_question(line):
        return ResidueClass.NOT_AN_ASSERTION, False, None
    if any(marker in lowered for marker in REJECTED_MARKERS):
        return ResidueClass.REJECTED_REFERENCE, False, None
    if any(marker in lowered for marker in HISTORICAL_MARKERS):
        return ResidueClass.HISTORICAL_REFERENCE, False, None
    if any(marker in lowered for marker in NEGATION_MARKERS):
        return ResidueClass.LEXICAL_RESTATEMENT, False, None
    structured, field_name = is_structured_field_line(source_type, line)
    if structured and len(line) <= MAX_VERIFIED_LINE_CHARS:
        return ResidueClass.VERIFIED_STRUCTURED, True, field_name
    return ResidueClass.LEXICAL_RESTATEMENT, False, None


def match_at(source_type: str, text: str, position: int) -> LineMatch:
    line_no, line = line_containing(text, position)
    residue_class, structured, field_name = classify_line(source_type, line)
    return LineMatch(line_no, line, field_name, structured, residue_class)
