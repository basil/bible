"""Corrections to the sources' transcription."""

from __future__ import annotations

from typing import Any, Unpack

import pytest
from conftest import changed

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
        ("I lay", "I \\f + \\fr 3:21 \\ft Gr. commit to.\\f*lay", "missing note"),
        # A note before a marker shares its backslash, not its first letter,
        # and one before another note shares that note's opening.
        (
            "I \\add lay",
            "I \\f + \\fr 3:21 \\ft Gr. commit to.\\f*\\add lay",
            "missing note",
        ),
        (
            "I \\f + \\fr 3:21 \\ft to.\\f*lay",
            "I \\f + \\fr 3:21 \\ft Gr.\\f*\\f + \\fr 3:21 \\ft to.\\f*lay",
            "missing note",
        ),
        # Two notes with words between them are not one missing note.
        (
            "I lay",
            "I \\f + \\fr 3:21 \\ft Gr.\\f* up \\f + \\fr 3:21 \\ft to.\\f*lay",
            None,
        ),
        ("[Greek characters]", "λόγος", "omitted Greek"),
    ],
)
def test_a_correction_mends_a_known_kind_of_slip(
    before: str, after: str, category: str | None
) -> None:
    assert repairs.category(before, after) == category


def corrected(key: str, **correction: Unpack[Correction]) -> tuple[str, frozenset[str]]:
    return repairs.brenton("GEN", BOOK, {key: ({"why": "a slip", **correction},)})


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
        ("GEN 1:1", {"from": "the", "to": "this"}, "does not apply"),
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


def test_identical_notes_are_corrected_one_by_one_within_each_note() -> None:
    note = "\\f + \\fr 1:1 \\ft secnd.\\f*"
    book = f"\\id GEN\n\\c 1\n\\p\n\\v 1 In {note}the {note}beginning.\n"
    slip = Correction({"from": "secnd", "to": "second", "why": "A slip."})
    text, mended = repairs.brenton(
        "GEN", book, {"GEN 1:1": (slip,), "GEN 1:1#2": (slip,)}
    )
    assert text.count("\\ft second.") == 2
    assert mended == {"1:1", "1:1#2"}
    assert repairs.NOTE.sub("", text) == repairs.NOTE.sub("", book)
    # A correction to a note may not reach beyond it into the scripture.
    with pytest.raises(CheckFailed, match="reaches beyond its note"):
        repairs.brenton(
            "GEN",
            book,
            {
                "GEN 1:1#2": (
                    {
                        "from": "secnd.\\f*beginning",
                        "to": "second.\\f*beginning",
                        "why": "A slip.",
                    },
                )
            },
        )
    with pytest.raises(CheckFailed, match="reaches beyond its note"):
        repairs.brenton(
            "GEN",
            book,
            {
                "GEN 1:1#2": (
                    {
                        "from": "secnd.\\f*",
                        "to": "second.",
                        "why": "A slip.",
                        "uncategorized": True,
                    },
                )
            },
        )


def test_a_dropped_note_is_restored_but_not_inside_another() -> None:
    note = "\\f + \\fr 1:1 \\ft Or, at.\\f*"
    text, _ = corrected(
        "GEN 1:1", **Correction({"from": "In the", "to": f"In {note}the"})
    )
    assert f"In {note}the begin ning" in text
    # A note at a verse's start is restored after the verse's marker.
    text, _ = corrected(
        "GEN 1:2", **Correction({"from": "\\v 2 But", "to": f"\\v 2 {note}But"})
    )
    assert f"\\v 2 {note}But the" in text
    with pytest.raises(CheckFailed, match="not where its key says"):
        corrected(
            "GEN 1:1", **Correction({"from": "\\v 2 But", "to": f"\\v 2 {note}But"})
        )
    with pytest.raises(CheckFailed, match="restored in a note"):
        corrected(
            "GEN 1:2#2",
            **Correction({"from": "\\ft secnd", "to": f"\\ft {note}secnd"}),
        )


def test_the_editions_corrections_all_apply(
    read: bible.pipeline.Read, policy: bible.policy.Policy
) -> None:
    """Each is made once, to a file the edition prints or reads; reading refused
    otherwise."""
    corrections = policy.brenton_notes["corrections"]
    assert len(corrections) == 355
    assert read.mended["1KI"] and "21:11" in read.mended["GEN"]


def test_policy_normalizes_correction_groups(declared: bible.policy.Policy) -> None:
    assert all(
        isinstance(group, tuple)
        for group in declared.brenton_notes["corrections"].values()
    )
    correction: Correction = {"from": "earthwas", "to": "earth was", "why": "A slip."}
    updated = changed(
        declared,
        "brenton_notes",
        lambda data: data["corrections"].update({"GEN 1:2": correction}),
    )
    assert updated.brenton_notes["corrections"]["GEN 1:2"] == (correction,)
    assert (
        updated.replace(brenton_notes=updated.brenton_notes).brenton_notes
        == updated.brenton_notes
    )


def test_empty_correction_group_is_refused(declared: bible.policy.Policy) -> None:
    with pytest.raises(
        CheckFailed, match="Brenton correction group with no corrections: GEN 1:2"
    ):
        changed(
            declared,
            "brenton_notes",
            lambda data: data["corrections"].update({"GEN 1:2": []}),
        )


def test_kjv_corrections_require_a_single_object(declared: bible.policy.Policy) -> None:
    with pytest.raises(
        CheckFailed, match="1611 correction GEN 1:2 has missing or unknown fields"
    ):
        changed(
            declared,
            "kjv_notes",
            lambda data: data["corrections"].update(
                {"GEN 1:2": [{"from": "a", "to": "b", "why": "A slip."}]}
            ),
        )
