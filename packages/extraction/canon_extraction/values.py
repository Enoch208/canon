import re

LIST_SEPARATOR = re.compile(r"\s*[/,]\s*(?:and\s+)?")
DASHES = re.compile(r"[\u2010-\u2015\u2212]")
PARENTHETICAL = re.compile(r"\s*\([^)]*\)\s*$")
WHITESPACE = re.compile(r"\s+")
MIN_SEARCHABLE = 3


def normalize(value: str) -> str:
    return WHITESPACE.sub(" ", DASHES.sub("-", value)).strip()


def strip_parenthetical(value: str) -> str:
    return PARENTHETICAL.sub("", value).strip()


def list_items(value: str) -> tuple[str, ...]:
    core = strip_parenthetical(value)
    parts = tuple(part.strip() for part in LIST_SEPARATOR.split(core) if part.strip())
    return parts if len(parts) > 1 else ()


def joined_variants(items: tuple[str, ...]) -> tuple[str, ...]:
    if len(items) < 2:
        return ()
    head = ", ".join(items[:-1])
    return (
        "/".join(items),
        " / ".join(items),
        ", ".join(items),
        f"{head}, and {items[-1]}",
        f"{head} and {items[-1]}",
    )


def percent_variants(value: str) -> tuple[str, ...]:
    match = re.fullmatch(r"~?(\d+(?:\.\d+)?)\s*%", value)
    if not match:
        return ()
    number = match.group(1)
    return (f"{number}%", f"{number} %", f"{number} percent")


def value_variants(value: str) -> tuple[str, ...]:
    core = normalize(value)
    seen: dict[str, None] = {core: None}
    stripped = strip_parenthetical(core)
    if stripped:
        seen.setdefault(stripped, None)
    items = list_items(core)
    for variant in joined_variants(items):
        seen.setdefault(variant, None)
    for variant in percent_variants(stripped):
        seen.setdefault(variant, None)
    return tuple(variant for variant in seen if len(variant) >= MIN_SEARCHABLE)


def item_variants(value: str) -> tuple[str, ...]:
    return tuple(item for item in list_items(normalize(value)) if len(item) >= MIN_SEARCHABLE)


def find_all(text: str, needle: str) -> list[int]:
    lowered = text.lower()
    target = needle.lower()
    positions: list[int] = []
    start = 0
    while True:
        index = lowered.find(target, start)
        if index < 0:
            return positions
        positions.append(index)
        start = index + 1
