"""The 1611 marginal notes: parsing, corrections, and anchoring in the text."""

import pytest

from bible import notes
from bible.checks import CheckFailed
from bible.edition import scripture_unit as unit
from bible.prepare import scripture_text


def test_marginal_notes_parse():
    parsed = notes.marginal_notes()
    assert sum(len(n) for n in parsed.values()) == notes.EXPECTED_NT_MARGINAL_NOTES


def test_unused_correction(patched):
    patched(notes, "MARGINAL_NOTES")["corrections"]["MAT 1:1 nothing"] = {
        "from": "a",
        "to": "b",
    }
    with pytest.raises(
        CheckFailed, match=r"Unused marginal note corrections: \['MAT 1:1 nothing'\]"
    ):
        notes.marginal_notes()


def test_correction_that_does_not_apply(patched):
    patched(notes, "MARGINAL_NOTES")["corrections"]["MAT 23:18 guilty"][
        "from"
    ] = "no such text"
    with pytest.raises(
        CheckFailed, match="correction does not apply: MAT 23:18 guilty"
    ):
        notes.marginal_notes()


def test_transcribers_remark_left_in_note(patched):
    # This correction removes "[symbol in wrong place in 1611]".
    del patched(notes, "MARGINAL_NOTES")["corrections"]["MAT 5:15 a bushel"]
    with pytest.raises(
        CheckFailed, match="Transcriber's remark left in marginal note: MAT 5:15"
    ):
        notes.marginal_notes()


def test_unused_anchor(patched):
    patched(notes, "MARGINAL_NOTES")["anchors"]["MAT 1:1 nothing"] = {
        "anchor": "nothing"
    }
    with pytest.raises(CheckFailed, match="Unused marginal note anchors"):
        notes.marginal_notes()


def test_missing_anchor_verse(archives, patched):
    anchors = patched(notes, "MARGINAL_NOTES")["anchors"]
    anchors["MAT 12:14 held a counsel"]["verse"] = "12:99"
    with pytest.raises(CheckFailed, match="verse missing: MAT 12:14 held a counsel"):
        scripture_text(unit("MAT"), archives)


def test_wrong_anchor(archives, patched):
    # George's lemma reads "counsel" where the Cambridge text has "council".
    del patched(notes, "MARGINAL_NOTES")["anchors"]["MAT 12:14 held a counsel"]
    with pytest.raises(
        CheckFailed, match=r"not found exactly once: MAT 12:14 held a counsel \(0\)"
    ):
        scripture_text(unit("MAT"), archives)


def test_ambiguous_anchor(archives, patched):
    # "of" occurs more than once in Matthew 6:1; the override picks the second.
    del patched(notes, "MARGINAL_NOTES")["anchors"]["MAT 6:1 of"]
    with pytest.raises(
        CheckFailed, match=r"not found exactly once: MAT 6:1 of \([2-9]\)"
    ):
        scripture_text(unit("MAT"), archives)


def test_anchor_inside_added_words(archives, patched):
    # "it" is the second of Mark 3:21's added words "of it".
    patched(notes, "MARGINAL_NOTES")["anchors"]["MRK 3:21 friends"] = {"anchor": "it"}
    with pytest.raises(
        CheckFailed, match="caller inside a character span: MRK 3:21 friends"
    ):
        scripture_text(unit("MRK"), archives)


def test_cambridge_text_must_not_already_have_notes(with_source):
    damaged = with_source(
        "kjv",
        "MAT",
        lambda t: t.replace("\\v 2 ", "\\v 2 \\f + \\ft x\\f* ", 1),
    )
    with pytest.raises(CheckFailed, match="already has footnotes: MAT"):
        scripture_text(unit("MAT"), damaged)


@pytest.mark.parametrize(
    "note, usfm",
    [
        ("Or, a thing", "\\f + \\fr 1:1 \\fqa Or, \\ft a thing.\\f*"),
        ("Gr. logos.", "\\f + \\fr 1:1 \\fqa Gr. \\ft logos.\\f*"),
        ("Who is he?", "\\f + \\fr 1:1 \\ft Who is he?\\f*"),
    ],
)
def test_marginal_note_usfm(note, usfm):
    assert notes.marginal_note_usfm("1:1", note) == usfm
