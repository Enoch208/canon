from canon_extraction.entities import (
    AliasType,
    Binding,
    Resolution,
    extract_bindings,
    name_from_local_part,
    normalize_name,
    organization_of,
    resolve,
)

HEADER = (
    "[\"From: Grace O'Connor <grace@redwood.com>\\nTo: Markus Klein "
    "<markus_klein@redwood.com>\\nSubject: capacity\\n"
)


def binding(name: str, email: str, doc_id: str = "dsid_a") -> Binding:
    return Binding(name, email, doc_id, "gmail", f"From: {name} <{email}>")


def test_extract_bindings_reads_real_header_shape() -> None:
    found = extract_bindings("dsid_a", "gmail", HEADER)
    assert [(b.display_name, b.email) for b in found] == [
        ("Grace O'Connor", "grace@redwood.com"),
        ("Markus Klein", "markus_klein@redwood.com"),
    ]
    assert found[0].evidence_span.startswith("[\"From: Grace O'Connor")


def test_single_word_names_are_not_bindings() -> None:
    assert extract_bindings("dsid_a", "gmail", "From: Connor <grace@redwood.com>") == []


def test_normalization_strips_titles_and_punctuation() -> None:
    assert normalize_name("AM Grace O'Connor") == "grace o connor"
    assert normalize_name("Grace Oconnor") == "grace oconnor"
    assert name_from_local_part("markus_klein@redwood.com") == "markus klein"
    assert organization_of("a.b@Redwood.COM") == "redwood.com"


def test_email_alias_resolves_and_spellings_attach_to_one_person() -> None:
    graph = resolve(
        [
            binding("Grace O'Connor", "grace@redwood.com"),
            binding("AM Grace O'Connor", "grace@redwood.com"),
        ],
        documents_scanned=2,
    )
    assert len(graph.people) == 1
    email_alias = next(a for a in graph.aliases if a.alias_type is AliasType.EMAIL)
    assert email_alias.resolution is Resolution.RESOLVED
    assert email_alias.person is not None and email_alias.person.organization == "redwood.com"
    display = [a for a in graph.aliases if a.alias_type is AliasType.DISPLAY_NAME]
    assert {a.value for a in display} == {"grace o connor"}
    assert all(a.resolution is Resolution.PROBABLE for a in display)


def test_same_name_across_organizations_stays_ambiguous() -> None:
    graph = resolve(
        [
            binding("Alyssa Chen", "alyssa.chen@cascadefg.com"),
            binding("Alyssa Chen", "alyssa.chen@zenovahealth.com"),
        ],
        documents_scanned=2,
    )
    assert len(graph.people) == 2
    display = next(a for a in graph.aliases if a.alias_type is AliasType.DISPLAY_NAME)
    assert display.resolution is Resolution.AMBIGUOUS
    assert display.person is None
    assert len(display.candidates) == 2
    emails = [a for a in graph.aliases if a.alias_type is AliasType.EMAIL]
    assert all(a.resolution is Resolution.RESOLVED for a in emails)


def test_counts_cover_every_resolution_state() -> None:
    graph = resolve([binding("Grace O'Connor", "grace@redwood.com")], documents_scanned=1)
    assert set(graph.counts()) == {"RESOLVED", "PROBABLE", "AMBIGUOUS"}
    assert graph.bindings_found == 1
    assert graph.documents_scanned == 1


def test_email_alias_support_counts_every_binding() -> None:
    graph = resolve(
        [
            binding("Grace O'Connor", "grace@redwood.com", "dsid_a"),
            binding("Grace O'Connor", "grace@redwood.com", "dsid_b"),
            binding("Grace O'Connor", "grace@redwood.com", "dsid_c"),
        ],
        documents_scanned=3,
    )
    email_alias = next(a for a in graph.aliases if a.alias_type is AliasType.EMAIL)
    assert email_alias.support == 3
