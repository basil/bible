"""The versification seed: the table and the words, heard together."""

from bible import alignment, seed, versification
from bible.references import Verse, parse_verse

OURS = (
    "\\id GEN\n\\c 1\n\\p\n"
    "\\v 1 The ark rested upon the mountains of Ararat.\n"
    "\\v 2 The raven went forth from the window.\n"
    "\\v 3 The dove found no rest for her foot.\n"
    "\\v 4 Noe builded an altar of clean beasts.\n"
    "\\v 5 Abimelech king of Gerara.\n"
    "\\v 6 The bow shall be seen in the cloud.\n"
    "\\v 6a The addition of the Greek.\n"
)
THEIRS = (
    "\\id GEN\n\\c 1\n\\p\n"
    "\\v 1 And the ark rested upon the mountains of Ararat.\n"
    "\\v 2 And the dove found no rest for the sole of her foot.\n"
    "\\v 3 And he sent forth a raven from the window.\n"
    "\\v 4 And Noah builded an altar, and took of every clean beast.\n"
    "\\v 5 Ahimelek of Philistia.\n"
    "\\v 6 The bow shall be seen in the cloud.\n"
    "\\v 7 While the earth remaineth, seedtime and harvest.\n"
)


class Texts(seed.Texts):
    def __init__(self, ours, theirs):
        self.books = {"GEN": "GEN"}
        self.edition = alignment.Verses({"GEN": ours})
        self.kjv = alignment.Verses({"GEN": theirs}, titled=True)
        self.weight = alignment.weights(self.edition.words, self.kjv.words)


def same(texts):
    """The table's account of a Bible it says nothing of."""
    return {
        verse: () if verse.letter else (Verse("GEN", verse.chapter, verse.number),)
        for verse in texts.edition.words
    }


def blocks(texts, table):
    return [
        (" ".join(map(str, ours)), " ".join(map(str, theirs)), by)
        for ours, theirs, by in seed.aligned(texts, "GEN", table)
    ]


def test_the_words_move_a_verse_and_its_place_keeps_one():
    texts = Texts(OURS, THEIRS)
    table = same(texts)
    # Where the table's rows disagree, it says nothing.
    table[parse_verse("GEN 1:5")] = None
    assert blocks(texts, table) == [
        ("GEN 1:1", "GEN 1:1", "words"),
        ("GEN 1:2", "GEN 1:3", "words"),
        ("GEN 1:3", "GEN 1:2", "words"),
        ("GEN 1:4", "GEN 1:4", "words"),
        # Names spelt otherwise share no words.
        ("GEN 1:5", "GEN 1:5", "place"),
        ("GEN 1:6", "GEN 1:6", "words"),
        ("GEN 1:6a", "", "words"),
        ("", "GEN 1:7", "words"),
    ]


def test_a_verse_left_over_joins_the_pair_that_has_its_words():
    ours = OURS.replace(
        "\\v 4 Noe builded an altar of clean beasts.\n",
        "\\v 4 Noe builded an altar\n\\v 4a of clean beasts.\n",
    )
    texts = Texts(ours, THEIRS)
    table = same(texts)
    assert ("GEN 1:4 GEN 1:4a", "GEN 1:4", "words") in blocks(texts, table)


def test_the_words_must_outvote_the_table():
    texts = Texts(OURS, THEIRS)
    raven, dove = parse_verse("GEN 1:2"), parse_verse("GEN 1:3")
    table = same(texts)
    assert seed.outvotes(texts, table, raven, dove)
    assert seed.outvotes(texts, table, raven, raven)
    # One that shares a word with its neighbour doesn't go to it for that.
    assert not seed.outvotes(texts, table, parse_verse("GEN 1:1"), dove)


def test_the_words_may_not_leave_a_verse_without_a_place():
    texts = Texts(OURS, THEIRS)
    one, two, three = (parse_verse(f"GEN 1:{n}") for n in (1, 2, 3))
    taken = [
        {"edition": [one], "words": [two], "table": [one], "by": "words"},
        {"edition": [two], "words": [], "table": [two], "by": "words"},
    ]
    settled = seed.settle(texts, taken)
    assert [(b["words"], b["by"]) for b in settled] == [
        ([one], "table"),
        ([two], "table"),
    ]
    # Unless a verse that stands in the way has no other place to go.
    held = [
        {"edition": [one], "words": [two], "table": None, "by": "words"},
        {"edition": [two], "words": [], "table": [two], "by": "words"},
        {"edition": [three], "words": [three], "table": [three], "by": "words"},
    ]
    assert [b["words"] for b in seed.settle(texts, held)] == [[two], [], [three]]


def test_runs_are_written_verse_for_verse_or_whole():
    verses = [parse_verse(f"GEN 1:{n}") for n in range(1, 8)]
    lettered = parse_verse("GEN 1:6a")
    entries = [
        ([verses[0]], [verses[1]], "words", None),
        ([verses[1]], [verses[2]], "words", None),
        ([verses[2]], [verses[3]], "table", None),
        ([verses[3], verses[4]], [verses[4]], "words", None),
        ([lettered], [verses[6]], "reading", "x"),
        ([verses[6]], [], "words", None),
    ]
    assert seed._runs(entries) == [
        {"edition": "GEN 1:1-2", "kjv": "GEN 1:2-3", "by": "words"},
        {"edition": "GEN 1:3", "kjv": "GEN 1:4", "by": "table"},
        {"edition": "GEN 1:4-5", "kjv": "GEN 1:5", "by": "words"},
        {"edition": "GEN 1:6a", "kjv": "GEN 1:7", "by": "reading", "why": "x"},
        {"edition": "GEN 1:7", "kjv": None, "by": "words"},
    ]


def test_the_seed_is_the_file(scripture, archives):
    # What has been read is in the file, and nothing has changed since it was
    # seeded: the sources are pinned, and so is the table.
    assert seed.seed(scripture, archives) == versification.DATA["kjv"]


def test_what_has_been_read_stands(scripture, archives, patched):
    runs = patched(versification, "DATA")["kjv"]["LEV"]
    runs[:] = [run for run in runs if run["by"] != "reading"]
    found = seed.seed(scripture, archives)["LEV"]
    # The raven and the owls, which the witnesses leave where they are numbered.
    assert not [run for run in found if "LEV 11" in (run["edition"] or run["kjv"])]
