"""Verses compared by the rarer words they share."""

from bible import alignment
from bible.alignment import Verses, content_words, similarity, stem, weights
from bible.references import Verse

PSALM = (
    "\\id PSA\n\\c 3\n\\d A Psalm of David, when he fled.\n\\q1\n"
    "\\v 1 Lord, how are they increased that trouble me!\n"
    "\\v 2 Many there be which say of my soul.\\f + \\fr 3:2 \\ft Selah\\f*\n"
    "\\c 4\n\\q1\n\\v 1 Hear me when I call.\n"
)
BRENTON = (
    "\\id PSA\n\\c 50\n\\d\n\\v 1 For the end, a Psalm of David,\n"
    "\\v 2 when Nathan the prophet came to him.\n\\p\n"
    "\\v 3 Have mercy upon me, O God.\n"
    "\\c 116\n\\p\n\\v 1 Praise the Lord, all ye nations.\n"
)


def test_a_word_is_compared_without_its_inflexion():
    assert [stem(w) for w in ("sows", "soweth", "sowing", "sowed")] == ["sow"] * 4
    # What is left must still be a word.
    assert stem("is") == "is" and stem("sing") == "sing"


def test_common_words_show_nothing():
    assert content_words("And the Lord said unto Moses") == {"lord", "mos"}


def test_a_title_is_the_words_before_the_first_verse():
    assert alignment.titles(PSALM) == {3: "A Psalm of David, when he fled."}
    # Brenton's title marker is empty: he numbers the title's words.
    assert alignment.titles(BRENTON) == {}
    assert alignment.title_verses(BRENTON) == {50: ["1", "2"]}


def test_a_title_is_verse_nothing_of_its_chapter():
    verses = Verses({"PSA": PSALM}, titled=True)
    assert list(map(str, verses.order["PSA"])) == [
        "PSA 3:0",
        "PSA 3:1",
        "PSA 3:2",
        "PSA 4:1",
    ]
    assert verses.words[Verse("PSA", 3, 0)] == {"psalm", "david", "fled"}
    assert Verse("PSA", 3, 0) not in Verses({"PSA": PSALM}).words


def test_a_notes_words_are_not_the_verses():
    verses = Verses({"PSA": PSALM})
    assert "selah" not in verses.words[Verse("PSA", 3, 2)]


def test_verses_can_be_left_out():
    left = Verses({"PSA": PSALM}, without={Verse("PSA", 3, 2)})
    assert list(map(str, left.order["PSA"])) == ["PSA 3:1", "PSA 4:1"]


def test_verses_shift_in_their_books_order():
    verses = Verses({"PSA": PSALM})
    [moved] = verses.shifted([Verse("PSA", 3, 2)], 1)
    assert str(moved) == "PSA 4:1"
    assert verses.shifted([Verse("PSA", 4, 1)], 1) is None


def test_rarer_words_weigh_more():
    ours = {1: {"ark", "water"}, 2: {"water"}, 3: {"water", "dove"}}
    theirs = {1: {"ark", "waters"}, 2: {"dove"}}
    weight = weights(ours, theirs)
    assert weight["ark"] > weight["water"]
    assert similarity(weight, ours[1], theirs[1]) > 0
    assert similarity(weight, ours[2], theirs[1]) == 0
    assert similarity(weight, set(), theirs[1]) == 0
    assert round(similarity(weight, theirs[2], theirs[2]), 6) == 1
