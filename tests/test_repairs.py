"""Corrections to the sources' transcription."""

from __future__ import annotations

from typing import Any, Unpack

import pytest

import bible.pipeline
import bible.policy
from bible import repairs
from bible.checks import CheckFailed
from bible.policy_schema import Correction

BOOK = (
    "\\id GEN\n\\c 1\n\\p\n"
    "\\v 1 In the begin ning God made \\f + \\fr 1:1 \\fqa Gr. \\fqa Gr. \\ft founded.\\f*the heaven.\n"
    "\\v 2 But the earthwas unsightly.\\f + \\fr 1:2 \\ft first.\\f*\\f + \\fr 1:2 \\ft secnd.\\f*\n"
)


@pytest.mark.parametrize(
    "before, after, category",
    [
        ("earthwas", "earth was", "missing word space"),
        ("word, word", "word word", "stray punctuation"),
        ("word; word", "word, word", "wrong punctuation"),
        ("secnd", "second", "missing letter"),
        ("worrd", "word", "stray letter"),
        ("Avith", "with", None),
        ("\\fqa Gr. \\fqa Gr. ", "\\fqa Gr. ", "doubled text"),
        ("note [sic] here", "note here", "remark"),
        ("\\f + \\fr 6:1 \\f*", "", "empty note"),
        ("[Greek characters]", "λόγος", "omitted Greek"),
    ],
)
def test_a_correction_mends_a_known_kind_of_slip(
    before: str, after: str, category: str | None
) -> None:
    assert repairs.category(before, after) == category


def corrected(key: str, **correction: Unpack[Correction]) -> tuple[str, frozenset[str]]:
    return repairs.brenton("GEN", BOOK, {key: {"why": "a slip", **correction}})


def test_corrections_are_made_where_their_keys_say() -> None:
    text, mended = corrected(
        "GEN 1:2", **Correction({"from": "earthwas", "to": "earth was"})
    )
    assert "But the earth was unsightly" in text and mended == frozenset()
    # #2 names the verse's second note, and the note it mends is recorded.
    text, mended = corrected(
        "GEN 1:2#2", **Correction({"from": "secnd", "to": "second"})
    )
    assert "\\ft second.\\f*" in text and mended == {"1:2#2"}
    text, mended = corrected(
        "GEN 1:1", **Correction({"from": "\\fqa Gr. \\fqa Gr. ", "to": "\\fqa Gr. "})
    )
    assert text.count("\\fqa Gr. ") == 1 and mended == {"1:1"}


@pytest.mark.parametrize(
    "key, correction, refusal",
    [
        ("GEN 1:1", {"from": "earthwas", "to": "earth was"}, "not where its key says"),
        ("GEN 1:2", {"from": "secnd", "to": "second"}, "not where its key says"),
        ("GEN 1:2", {"from": "the", "to": "this"}, "does not apply"),
        ("GEN 1:2", {"from": "unsightly", "to": "unsightly"}, "no-op"),
        # Outside a note, only a word space may be mended in the translation.
        (
            "GEN 1:1",
            {"from": "begin ning", "to": "beginning", "uncategorized": True},
            None,
        ),
        (
            "GEN 1:2",
            {"from": "unsightly.", "to": "unsightly,"},
            "changes the wording outside a note",
        ),
        ("GEN 1:2", {"from": "earthwas", "to": "earth is"}, "fits no category"),
        (
            "GEN 1:2",
            {"from": "earthwas", "to": "earth was", "uncategorized": True},
            "listed as uncategorized is a missing word space",
        ),
    ],
)
def test_a_correction_that_does_not_fit_is_refused(
    key: str, correction: dict[str, Any], refusal: str | None
) -> None:
    if refusal is None:
        assert "In the beginning God" in corrected(key, **correction)[0]
        return
    with pytest.raises(CheckFailed, match=refusal):
        corrected(key, **correction)


def test_the_editions_corrections_all_apply(
    read: bible.pipeline.Read, policy: bible.policy.Policy
) -> None:
    """Each is made once, to a file the edition prints; reading refused otherwise."""
    corrections = policy.brenton_notes["corrections"]
    assert len(corrections) == 83
    assert read.mended["1KI"] and "21:11" in read.mended["GEN"]
