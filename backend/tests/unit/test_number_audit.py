"""SPEC § 13.1 — a number the tools did not produce must be flagged."""

from app.agent.audit import audit_answer

RESULTS = [
    {
        "total": 2,
        "items": [
            {
                "metrics": {"dps.total": {"value": 18619973.8}, "life.max": {"value": 3120.0}},
                "game_version": "3.27",
            },
            {
                "metrics": {"dps.total": {"value": 5607308.3}, "life.max": {"value": 4093.0}},
                "game_version": "3.29",
            },
        ],
    }
]


def test_exact_and_formatted_numbers_pass():
    a = audit_answer("The Slayer does 18,619,973.8 DPS with 3,120 life on patch 3.27.", RESULTS)
    assert a.checked == 3 and a.clean


def test_compact_rounding_passes_within_tolerance():
    a = audit_answer("About 18.6M DPS and 5.6M for the second, 3120 life.", RESULTS)
    assert a.clean, a.unverified


def test_french_formatting_passes():
    a = audit_answer("Environ 18 619 973,8 DPS et 3 120 de vie.", RESULTS)
    assert a.clean, a.unverified


def test_invented_numbers_are_flagged():
    a = audit_answer("It deals 25M DPS, has 3,120 life and 75% resistances.", RESULTS)
    assert not a.clean
    assert "25M" in a.unverified and "75%" in a.unverified
    assert "3,120" not in a.unverified


def test_no_numbers_is_clean_and_counts_zero():
    a = audit_answer("Unknown — the export carries no DPS.", RESULTS)
    assert a.clean and a.checked == 0


def test_versions_and_counts_are_audited_too():
    assert audit_answer("Two builds match on patch 3.27.", RESULTS).clean
    assert not audit_answer("Seven builds match on patch 3.30.", RESULTS).clean


def test_numbers_quoted_from_the_question_are_allowed():
    q = "What changed in Path of Exile 2 for builds under 20 divines?"
    a = audit_answer("In Path of Exile 2, nothing under 20 divines matched.", RESULTS, question=q)
    assert a.clean
    assert not audit_answer("In Path of Exile 2, nothing under 20 divines matched.", RESULTS).clean


def test_list_numbering_is_not_a_claim():
    text = "Two things:\n1. Life is 3,120.\n2. DPS is 18,619,973.8.\n3) Done."
    a = audit_answer(text, RESULTS)
    assert a.clean, a.unverified
    assert a.checked == 2
