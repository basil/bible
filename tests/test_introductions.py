"""The introductions to the books of the Apocrypha, at the front and as
footnotes on the books they introduce."""

import re

import pytest

from bible import introductions
from bible.checks import CheckFailed
from bible.introductions import INTRODUCTIONS, book_notes, placed_paragraphs
from bible.prepare import introductions_source, recorder
from bible.usfm import plain_text


@pytest.fixture
def source(archives):
    # Corrected, as the build reads it.
    return introductions_source(archives)


def test_every_paragraph_is_placed_or_omitted_once(source):
    placed = placed_paragraphs(source)
    assert (
        sum(len(p) for p in placed.values()) + len(INTRODUCTIONS["omit"])
        == source.count("\\ip ")
        == 25
    )
    assert [key for _, key, _ in placed["front"]] == INTRODUCTIONS["front"]


def test_front_keeps_its_title_and_general_paragraphs(source):
    text = introductions.front_text(source, recorder(None, "OTH"))
    assert "\\mt1 THE BOOKS OF THE APOCRYPHA" in text
    assert not re.search(r"^\\is", text, re.M)
    assert text.count("\\ip ") == 4
    assert (
        "The third and fourth books of the Maccabees have been translated" not in text
    )
    assert "The second book of Esdras [of the English Apocrypha] is not" in text
    assert "The book of Tobit" not in text


def test_gloss_at_the_front(source):
    text = introductions.front_text(source, recorder(None, "OTH"))
    assert (
        "save I. and II. Esdras [of the English Apocrypha] and the Prayer of Manasses"
    ) in text
    assert "between Nehemias and the New Testament" in text


def test_printed_paragraphs_give_back_the_source(source):
    # The front, the books' notes and the omitted paragraphs, without the
    # glosses and name changes, are the source's paragraphs, each once.
    def paragraphs(text):
        return [line[4:] for line in text.split("\n") if line.startswith("\\ip ")]

    def words(text):
        return plain_text(introductions.GLOSS.sub("", text))

    def original_words(text, key):
        for change in reversed(INTRODUCTIONS["names"].get(key, [])):
            text = text.replace(change["to"], change["from"])
        for gloss in INTRODUCTIONS["glosses"].get(key, []):
            if "replace" in gloss:
                text = text.replace(gloss["insert"], gloss["replace"])
        return words(text)

    bodies = [words(p) for p in paragraphs(source)]
    placed = placed_paragraphs(source)
    front = paragraphs(introductions.front_text(source, recorder(None, "OTH")))
    assert front == [body for _, _, body in placed["front"]]
    for entries in placed.values():
        for i, key, body in entries:
            assert original_words(body, key) == bodies[i]
    notes = book_notes(source)
    for place, entries in placed.items():
        if place != "front":
            expected = " ".join(words(body) for _, _, body in entries)
            note = notes[place][0].removeprefix("\\ef - \\ft ").removesuffix("\\ef*")
            assert words(note) == expected
    omitted = [
        i
        for key in INTRODUCTIONS["omit"]
        for i, b in enumerate(bodies)
        if b.startswith(key)
    ]
    printed = [i for entries in placed.values() for i, _, _ in entries]
    assert sorted(printed + omitted) == list(range(len(bodies)))


def test_book_notes_are_reviewed(prepared):
    (tobit,) = [e for e in prepared["TOB"].review if e["rule"] == "book introduction"]
    assert tobit["key"] == "TOB 1:1 introduction"
    assert tobit["verse"].startswith("The book of the words of Tobit")
    assert tobit["note"].startswith("The book of Tobit is one")
    assert tobit["source"].startswith("The book of Tobit is one")
    daniel = [
        e["key"] for e in prepared["DAG"].review if e["rule"] == "book introduction"
    ]
    assert daniel == ["DAG 0:1 introduction", "DAG 3:25 introduction"]
    (epistle,) = [e for e in prepared["LJE"].review if e["rule"] == "book introduction"]
    assert "[in the English Apocrypha]" in epistle["note"]
    # The source is the paragraph as Brenton's edition prints it.
    assert epistle["source"].startswith("This pseudepigraphal epistle, containing")
    assert "[" not in epistle["source"]
    (first,) = [e for e in prepared["1MA"].review if e["rule"] == "book introduction"]
    assert first["note"].startswith("There are four books of the Maccabees")


def test_book_note_on_the_first_verse(scripture):
    tobit = scripture["TOB"]
    assert tobit.count("one of the most perfect of Hebrew idylls") == 1
    assert "\\v 1 \\ef - \\ft The book of Tobit is one" in tobit


def test_book_note_paragraphs_and_nested_styles(source):
    note, *_ = book_notes(source)["1MA"]
    assert note.startswith("\\ef - \\ft There are four books")
    assert "canonical. The \\+it First\\+it* Book of the Maccabees" in note
    assert note.endswith("sterling worth.\\ef*")
    assert "\\+sc b.c.\\+sc*" in note


def test_book_introductions_run_as_one_paragraph(source):
    notes = book_notes(source)
    assert all("\\fp " not in note for note, *_ in notes.values())
    assert "story of the Exodus. The book was, without doubt" in notes["WIS"][0]
    sirach = notes["SIR"][0]
    assert "The book falls into two" in sirach
    assert "The title" in sirach


def test_gloss_in_a_book_note(source):
    note, *_ = book_notes(source)["LJE"]
    assert "the last chapter of Baruch [in the English Apocrypha]. It" in note
    note, *_ = book_notes(source)["4MA"]
    assert note.endswith(
        "this edition of the Apocrypha [for which this introduction was written].\\ef*"
    )


def test_the_books_notes_cite_as_the_edition_does(scripture, prepared):
    # Where the books are prepared, so that a note is read at its own book.
    assert (
        "Manasses, King of Judah, mentioned in 2 Chronicles 33:18." in scripture["MAN"]
    )
    assert "peculiar to the book (3:1–5:6), commonly" in scripture["1ES"]
    assert "first portion (1:1–11:4) is distinguished" in scripture["WIS"]
    baruch = scripture["BAR"]
    assert "historical introduction (1:1–14), attributing" in baruch
    assert "ending at 3:8, was" in baruch
    assert "second portion (3:9–4:4) in Aramaic" in baruch
    assert "third portion (4:5–5:9) in Greek" in baruch
    [read] = [
        operation
        for operation in prepared["BAR"].transformations
        if operation["operation"] == "read citations"
        and operation["dialect"] == "apocrypha-introduction"
    ]
    assert [citation["source"] for citation in read["citations"]] == [
        "1. 1–14",
        "3. 8",
        "3. 9–4. 4",
        "4. 5–5. 9",
    ]


def test_book_names_match_the_edition(source):
    notes = book_notes(source)
    assert "The First Book of Esdras, which" in notes["1ES"][0]
    assert "portions of 2 Chronicles, 2 Esdras, and Nehemias." in notes["1ES"][0]
    assert "These additions to the [Book of Esther] supply" in notes["ESG"][0]
    assert "Bel and the Dragon] to the [Book of Daniel] were" in notes["DAG"][0]
    assert "written in Hebrew by Jesus, the Son of Sirach of" in notes["SIR"][0]
    assert "Joshua" not in notes["SIR"][0]
    assert (
        "much inferior to that of the First Book [of the Maccabees]." in notes["2MA"][0]
    )
    assert notes["LJE"][0].startswith(
        "\\ef - \\ft [The Epistle of Jeremias], containing a denunciation"
    )
    assert "Susanna and Bel and the Dragon contain" in notes["DAG"][0]


def test_daniel_notes_follow_their_sections(scripture):
    daniel = scripture["DAG"]
    assert re.search(
        r"\\c 0\n.*?\\v 1 \\ef - \\ft These three additions \[the Song", daniel, re.S
    )
    assert (
        "\\s1 THE SONG OF THE THREE CHILDREN\n\\p\n\\v 25 "
        "\\ef - \\ft The Song of the Three Children"
    ) in daniel
    assert daniel.count("The Song of the Three Children contains") == 1
    assert daniel.count("in the Maccabean age") == 1
    assert "a matter of much dispute. Susanna and Bel and the Dragon contain" in daniel


def test_book_without_an_introduction(source):
    assert "GEN" not in book_notes(source)


@pytest.mark.parametrize(
    "damage, message",
    [
        (
            lambda d: d["books"]["TOB"].append("The story of Judith"),
            "paragraphs placed twice",
        ),
        (
            lambda d: d["books"]["TOB"].append("The story of Judit"),
            "paragraphs placed twice",
        ),
        (lambda d: d["books"].pop("JDT"), "not placed"),
        (lambda d: d["books"]["TOB"].__setitem__(0, "The"), "names no one paragraph"),
        (lambda d: d["books"]["SIR"].reverse(), "out of source order: SIR"),
        (lambda d: d["books"].__setitem__("XYZ", []), "outside the edition"),
        (
            lambda d: (
                d["sections"]["DAG"]["3:25"]["paragraphs"].clear(),
                d["books"]["DAG"].insert(0, "The Song of the Three Children"),
            ),
            r"no paragraphs: \['DAG@3:25'\]",
        ),
        (
            lambda d: d["glosses"]["This pseudepigraphal epistle"][1].__setitem__(
                "after", "the first chapter of Baruch"
            ),
            "Gloss does not apply",
        ),
        (
            lambda d: d["glosses"]["This pseudepigraphal epistle"][1].pop("why"),
            "Gloss without a why",
        ),
        (
            lambda d: d["glosses"]["This pseudepigraphal epistle"][1].__setitem__(
                "insert", " in the English Apocrypha"
            ),
            "not one bracketed insertion",
        ),
        (
            lambda d: d["glosses"].__setitem__(
                "Nothing", [{"after": "x", "insert": "y", "why": "z"}]
            ),
            "Glosses on no placed paragraph",
        ),
        (
            lambda d: d["names"]["This purports"][0].__setitem__("from", "Manasses"),
            "Name change does not apply once",
        ),
        (
            lambda d: d["names"]["This purports"][0].pop("why"),
            "Name change without a why",
        ),
        # Only whole words: "the first boo" would leave "the first boo [of the
        # Maccabees]k".
        (
            lambda d: d["glosses"]["The second book of the Maccabees"][0].__setitem__(
                "after", "the first boo"
            ),
            "Gloss does not apply",
        ),
        (
            lambda d: d["glosses"]["This pseudepigraphal epistle"][1].__setitem__(
                "after", "the last chapter of Baru"
            ),
            "Gloss does not apply",
        ),
        # A front with none of the general paragraphs would print a bare title.
        (
            lambda d: (
                d["omit"].update({key: "Test" for key in d["front"]}),
                d["front"].clear(),
                d["glosses"].pop("During the Reformation"),
                d["glosses"].pop("The second book of Esdras"),
                d["names"].pop("During the Reformation"),
                d["names"].pop("In more recent times"),
            ),
            r"no paragraphs: \['front'\]",
        ),
        # An empty entry is refused, not read as no gloss or no change.
        (
            lambda d: d["glosses"].__setitem__("The book of Tobit", [{}]),
            "Gloss without a why",
        ),
        (
            lambda d: d["glosses"].__setitem__("The book of Tobit", []),
            "Glosses with no gloss",
        ),
        (
            lambda d: d["names"].__setitem__("The book of Tobit", []),
            "Name changes with no change",
        ),
        # A gloss follows the source's words or replaces them, not both.
        (
            lambda d: d["glosses"]["This pseudepigraphal epistle"][0].__setitem__(
                "after", "This pseudepigraphal epistle"
            ),
            "Gloss does not apply",
        ),
        (
            lambda d: d["glosses"]["This pseudepigraphal epistle"][0].__setitem__(
                "insert", " [The Epistle of Jeremias]"
            ),
            "replacing words starts with a space",
        ),
        # The editor's words are bracketed, and only a gloss brackets.
        (
            lambda d: d["names"]["This purports"][0].__setitem__(
                "to", "Manasses [the King], King of Judah"
            ),
            "Name change adds brackets",
        ),
        # Brenton's italics and small capitals are kept.
        (
            lambda d: d["names"]["This purports"][0].__setitem__(
                "to", "\\it Manasses\\it*, King of Judah"
            ),
            "alters the markup: This purports",
        ),
        (
            lambda d: d["sections"]["DAG"]["3:25"].pop("heading"),
            r"missing or unknown fields: \['DAG@3:25'\]",
        ),
        # A gloss or name change applies to the source's words, not inside or
        # across another gloss.
        (
            lambda d: d["glosses"]["These three additions"].append(
                {"after": "Bel and the Dragon", "insert": " [x]", "why": "Test"}
            ),
            "Gloss does not apply: These three additions",
        ),
        (
            lambda d: d["names"].__setitem__(
                "This pseudepigraphal epistle",
                [
                    {
                        "from": "Baruch [in the English Apocrypha]",
                        "to": "Baruch",
                        "why": "Test",
                    }
                ],
            ),
            "Name change does not apply once: This pseudepigraphal epistle",
        ),
        # A gloss after words is set off from them by a space.
        (
            lambda d: d["glosses"]["This pseudepigraphal epistle"][1].__setitem__(
                "insert", "[in the English Apocrypha]"
            ),
            "following words starts without a space",
        ),
    ],
)
def test_broken_placement(patched, source, damage, message):
    damage(patched(introductions, "INTRODUCTIONS"))
    with pytest.raises(CheckFailed, match=message):
        placed_paragraphs(source)


@pytest.mark.parametrize(
    "damage, message",
    [
        (
            lambda s: s["DAG"]["3:25"].__setitem__("heading", "THE SONG"),
            "heading changed: DAG 3:25",
        ),
        (
            lambda s: s["DAG"].__setitem__("3:99", s["DAG"].pop("3:25")),
            "verse missing: DAG 3:99",
        ),
    ],
)
def test_broken_section(patched, scripture, source, damage, message):
    damage(patched(introductions, "INTRODUCTIONS")["sections"])
    with pytest.raises(CheckFailed, match=message):
        introductions.with_book_note(
            "DAG", scripture["DAG"], source, recorder(None, "DAG")
        )


@pytest.mark.parametrize(
    "damage, message",
    [
        # A paragraph run on to a second line would be moved only in part.
        (
            lambda s: s.replace(
                " It was written in Greek,", "\nIt was written in Greek,"
            ),
            "line of an unknown kind",
        ),
        # Square brackets in the notes are the editor's alone.
        (
            lambda s: s.replace(
                "the last chapter of Baruch", "[the last chapter of Baruch]"
            ),
            "brackets not a gloss's",
        ),
    ],
)
def test_broken_source(source, damage, message):
    damaged = damage(source)
    assert damaged != source
    with pytest.raises(CheckFailed, match=message):
        placed_paragraphs(damaged)
