"""Preparing source books: chapter selection, regrouping, and relabelling."""

import pytest

from bible.checks import CheckFailed
from bible.edition import scripture_unit as unit
from bible.prepare import sample_chapters, scripture_text


def test_manifest_chapters_must_exist(archives):
    entry = {**unit("NEH"), "chapters": [11, 24]}
    with pytest.raises(CheckFailed, match="chapters outside the source: NEH"):
        scripture_text(entry, archives)


def test_malachias_chapter_boundary(with_source):
    damaged = with_source(
        "brenton",
        "MAL",
        lambda t: t.replace("\\v 19 For, behold", "\\v 19 For, lo"),
    )
    with pytest.raises(CheckFailed, match="Malachias chapter boundary changed"):
        scripture_text(unit("MAL"), damaged)


def test_song_of_the_three_children_boundary(with_source):
    damaged = with_source(
        "brenton",
        "DAG",
        lambda t: t.replace("Then Azarias stood up", "Azarias stood up"),
    )
    with pytest.raises(
        CheckFailed, match="Song of the Three Children boundary changed"
    ):
        scripture_text(unit("DAG"), damaged)


def test_relabelled_note_reference(with_source):
    # Nehemias relabels chapter markers only; a note would keep its source chapter.
    damaged = with_source(
        "brenton",
        "EZR",
        lambda t: t.replace(
            "son of Chelcia.", "son of Chelcia.\\f + \\fr 11:1 \\ft x\\f*", 1
        ),
    )
    with pytest.raises(
        CheckFailed, match="Note reference disagrees with its verse: NEH"
    ):
        scripture_text(unit("NEH"), damaged)


# Like the prepared Daniel: Susanna's heading ends the header, and Bel's
# follows Daniel's last verse on the same line.
HEADER = "\\id DAG\n\\mt1 DANIEL\n"
SUSANNA = "\\s1 SUSANNA\n\\c 0\n\\p\n\\v 1 A.  "
DANIEL_1 = "\\c 1\n\\p\n\\v 1 B.  "
BEL = "\\s1 BEL\n\\c 13\n\\nb\n\\v 1 C."
DANIEL = HEADER + SUSANNA + DANIEL_1 + BEL


@pytest.mark.parametrize(
    "wanted, expected",
    [
        ([0, 1, 13], DANIEL),
        ([1, 13], HEADER + DANIEL_1 + BEL),
        ([0, 13], HEADER + SUSANNA + BEL.replace("\\nb", "\\p")),
        ([0, 1], HEADER + SUSANNA + DANIEL_1),
    ],
)
def test_sample_chapters_keep_lead_in_headings_with_their_chapter(wanted, expected):
    assert sample_chapters("DAG", DANIEL, wanted) == expected


def test_sample_chapters_must_exist():
    with pytest.raises(CheckFailed, match="Sample chapters missing from DAG"):
        sample_chapters("DAG", DANIEL, [1, 2])
