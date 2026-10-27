"""The table of chapters and verses, and the passages the editor's pages name."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, Protocol

import pytest
from conftest import changed

import bible.numbering
import bible.pipeline
import bible.policy
import bible.references
import bible.sources
from bible import (
    assembly,
    crossrefs,
    numbering,
    quotations,
    scripture,
    terminology,
    usfm,
    usj,
    versification,
)
from bible.checks import CheckFailed
from bible.numbering import MISSING, Table, within
from bible.policy import NUMBERING
from bible.references import Verse, parse_verse
from bible.scripture import Inventory


class Printed(Protocol):
    def __call__(
        self,
        written: str,
        inventory: Inventory = ...,
        ours: bible.references.Books = ...,
    ) -> str: ...


@pytest.fixture(scope="module")
def facing(sources: bible.sources.Sources) -> Inventory:
    """The King James Bible's chapters and verses, by book."""
    return {
        code: usfm.inventory(text)["chapters"]
        for code, text in sources.kjv.items()
        if re.search(r"^\\c ", text, re.M)
    }


@pytest.fixture(scope="module")
def names(edition: bible.pipeline.Edition) -> tuple[bible.references.Books, ...]:
    """Both Bibles' names for their books: the edition's, and the King James."""
    return edition.books, edition.read.kjv_books


@pytest.fixture(scope="module")
def printed(
    policy: bible.policy.Policy,
    edition: bible.pipeline.Edition,
    facing: Inventory,
    names: tuple[bible.references.Books, ...],
) -> Printed:
    """One of the editor's pages as it prints, from what it is written."""

    def page(
        written: str,
        inventory: Mapping[str, Mapping[str, Sequence[str]]] = edition.inventory,
        ours: bible.references.Books = names[0],
    ) -> str:
        return usj.serialize(
            numbering.page(
                written,
                inventory,
                facing,
                ours,
                names[1],
                glossary=edition.glossary,
                policy=policy,
            )
        )

    return page


@pytest.fixture(scope="module")
def rows(
    policy: bible.policy.Policy, edition: bible.pipeline.Edition, facing: Inventory
) -> Callable[[str], list[tuple[str, str]]]:
    return lambda code: Table(code, edition.inventory, facing, policy=policy).rows()


@pytest.mark.parametrize(
    "verses,cell",
    [
        (["LEV 8:19", "LEV 8:20", "LEV 8:21"], "8:19–21"),
        (["LEV 8:18"], "8:18"),
        (["JOS 9:2a", "JOS 9:2b", "JOS 9:2c"], "9:2a–c"),
        (["JER 10:5", "JER 10:9a"], "10:5, 9a"),
        (["ISA 8:23", "ISA 9:1"], "8:23; 9:1"),
        (["1KI 16:28d", "1KI 16:28e", "1KI 22:46"], "16:28d–e; 22:46"),
    ],
)
def test_verses_print_chapter_by_chapter(verses: list[str], cell: str) -> None:
    assert within(list(map(parse_verse, verses))) == cell


def test_a_chapter_that_stands_whole_elsewhere_is_one_row(
    rows: Callable[[str], list[tuple[str, str]]],
) -> None:
    jeremias = set(rows("JER"))
    assert {("26", "46"), ("36", "29"), ("50", "43")} <= jeremias
    # A chapter in part is its verses, and so is one that is only part of
    # the King James chapter: the rest of chapter 25 keeps its number.
    assert ("32", "25") not in jeremias
    assert {
        ("32:1–24", "25:15–38"),
        ("38:1–34", "31:1–34"),
        ("51:1–30", "44:1–30"),
        ("51:31–35", "45:1–5"),
        ("25:15–19", "49:35–39"),
    } <= jeremias


def test_what_either_bible_lacks_is_missing(
    rows: Callable[[str], list[tuple[str, str]]],
) -> None:
    jeremias = rows("JER")
    assert ("missing", "39:4–13") in jeremias
    assert ("38:15", "missing") in rows("EXO")
    # Where the King James Bible has it, among the rows of its chapter.
    at = jeremias.index((MISSING, "33:14–26"))
    assert jeremias[at - 1] == ("40", "33") and jeremias[at + 1] == ("41", "34")
    # In the King James Bible's order, where the edition's verse holds more.
    at = jeremias.index(("10:5, 9a", "10:5"))
    assert jeremias[at + 1 : at + 3] == [(MISSING, "10:6–8"), (MISSING, "10:10")]
    # A lettered verse that the King James Bible lacks has no row: its
    # letter says so. Esther's prayer is ruled to be one.
    esther = rows("ESG")
    assert (MISSING, "5:1–2") in esther
    assert not [row for row in esther if row[1] == MISSING]


def test_a_verse_may_stand_beside_two(
    rows: Callable[[str], list[tuple[str, str]]],
) -> None:
    assert rows("LEV")[:2] == [
        ("5:20–26", "6:1–7"),
        ("6:1–23", "6:8–30"),
    ]
    assert ("9:2a–f", "8:30–35") in rows("JOS")
    assert ("35:16", "35:16, 21") in rows("GEN")
    # The Hebrew's chapter 30 stands in chapter 24 under the Hebrew's labels,
    # which print alike on both sides, so no row names it.
    assert not any("22f" in ours or ours.startswith("30:") for ours, _ in rows("PRO"))
    # Proverbs 8:28 also holds the first part of the King James Bible's 8:29,
    # which the row says without giving 8:29 both.
    assert ("8:28", "8:28–29") in rows("PRO")
    assert ("8:28–29", "8:28–29") not in rows("PRO")
    # One verse may hold what the King James Bible tells in two places, and
    # lettered verses that a reading pairs each stand beside their own part.
    assert ("38:11", "37:4, 15") in rows("EXO")
    kingdoms = rows("1KI")
    assert ("2:35c", "3:1") in kingdoms
    at = kingdoms.index(("10:22a", "9:15, 17–19"))
    # The Pharaoh passage omitted at 5:14b no longer supplies the capture of Gazer.
    assert kingdoms[at + 1 : at + 4] == [
        (MISSING, "9:16"),
        ("10:22b", "9:20–21"),
        ("10:22c", "9:22"),
    ]
    # Malachias ends in another order.
    assert rows("MAL") == [("4:4–5", "4:5–6"), ("4:6", "4:4")]


def test_a_run_that_keeps_its_numbers_has_no_row(
    policy: bible.policy.Policy, rows: Callable[[str], list[tuple[str, str]]]
) -> None:
    # Genesis 31:47-48 is read to keep its numbers, against the words.
    kept = [
        (run["edition"], run["kjv"])
        for run in policy.versification["kjv"]["GEN"]
        if run.get("by") == "reading" and run["edition"] == run["kjv"]
    ]
    assert kept == [("GEN 31:47-48", "GEN 31:47-48")]
    assert not [row for row in rows("GEN") if row[0] == row[1]]
    assert rows("JDG") == rows("RUT") == []


def read_cell(cell: str, book: str) -> list[bible.references.Verse]:
    """The verses a cell names, read back from what it prints; none, if it
    names a whole chapter or says that its verses are missing."""
    verses = []
    # A run printed out of the order of its numbers says what it follows.
    cell = re.sub(rf" \({numbering.AFTER} \w+\)$", "", cell)
    for part in cell.split("; ") if ":" in cell else ():
        chapter, _, listed = part.partition(":")
        for stretch in listed.split(", "):
            first, _, last = stretch.partition("–")
            match = re.fullmatch(r"(\d+)([a-z]?)", first)
            assert match is not None
            number, letter = match.groups()
            if not last:
                verses.append(Verse(book, int(chapter), int(number), letter))
            elif last.isalpha():
                verses += [
                    Verse(book, int(chapter), int(number), chr(n))
                    for n in range(ord(letter), ord(last) + 1)
                ]
            else:
                verses += [
                    Verse(book, int(chapter), n)
                    for n in range(int(number), int(last) + 1)
                ]
    return verses


def test_the_table_says_what_the_runs_say(
    policy: bible.policy.Policy,
    edition: bible.pipeline.Edition,
    facing: Inventory,
) -> None:
    """Read back, the rows give every verse the King James verses that the
    runs give it, and every verse they don't name keeps its number. A range
    of psalms is read back psalm by psalm."""
    for code in policy.versification["old_testament"]:
        table = Table(code, edition.inventory, facing, policy=policy)
        kjv = versification.kjv_book(code, policy=policy)
        told: dict[Verse, tuple[Verse, ...]] = {}
        listed = (
            numbering.psalms_rows(edition.inventory, facing, policy=policy)
            if code == "PSA"
            else table.rows()
        )
        for ours, theirs in listed:
            if ours == MISSING:
                for verse in read_cell(theirs, kjv):
                    assert versification.from_kjv(verse, policy=policy) == ()
                continue
            if ":" not in ours:
                if theirs == MISSING:
                    assert all(
                        verse in versification.apocryphal(policy=policy)
                        for verse in table.verses(ours)
                    )
                    continue
                # A chapter that stands whole elsewhere.
                first, _, last = ours.partition("–")
                other_first, _, other_last = theirs.partition("–")
                chapters = range(int(first), int(last or first) + 1)
                other = range(int(other_first), int(other_last or other_first) + 1)
                assert len(chapters) == len(other)
                for numbered_chapter, facing_chapter in zip(chapters, other):
                    for verse in table.verses(numbered_chapter):
                        if not verse.letter:
                            told[verse] = (Verse(kjv, facing_chapter, verse.number),)
                continue
            here, there = read_cell(ours, code), tuple(read_cell(theirs, kjv))
            pairs = (
                zip(here, ((verse,) for verse in there))
                if len(here) == len(there)
                else ((verse, there) for verse in here)
            )
            for verse, facing_it in pairs:
                assert verse not in told, str(verse)
                told[verse] = facing_it
        for chapter in table.ours:
            for verse in table.verses(chapter):
                if verse in versification.apocryphal(policy=policy):
                    continue
                facing_it = versification.to_kjv(verse, policy=policy)
                found = tuple(v for v in facing_it if v.number != versification.TITLE)
                if facing_it and not found:
                    # A title, which the King James Bible doesn't number.
                    assert verse not in told
                elif verse in told:
                    assert told[verse] == found, (str(verse), told[verse], found)
                elif verse in versification.printed_as(policy=policy):
                    # A verse that prints its King James label tells it itself.
                    shown = versification.printed_as(policy=policy)[verse]
                    assert found == (Verse(kjv, shown.chapter, shown.number),)
                elif verse.letter:
                    assert found == (), str(verse)
                else:
                    assert found == (Verse(kjv, verse.chapter, verse.number),)


def test_psalms_use_whole_psalms_and_verse_ranges(
    policy: bible.policy.Policy,
    edition: bible.pipeline.Edition,
    facing: Inventory,
) -> None:
    psalms = numbering.psalms_rows(edition.inventory, facing, policy=policy)
    assert psalms[:8] == [
        ("3:2–9", "3:1–8"),
        ("4:2–9", "4:1–8"),
        ("5:2–13", "5:1–12"),
        ("6:2–11", "6:1–10"),
        ("7:2–18", "7:1–17"),
        ("8:2–10", "8:1–9"),
        ("9:2–21", "9:1–20"),
        ("9:22–39", "10:1–18"),
    ]
    assert ("13–16", "14–17") in psalms
    assert ("50:3–21", "51:1–19") in psalms
    assert ("12:2–5", "13:1–4") in psalms
    assert ("12:6", "13:5–6") in psalms
    assert ("113:1–8", "114:1–8") in psalms
    assert ("113:9–26", "115:1–18") in psalms
    assert ("114:1–9", "116:1–9") in psalms
    assert ("115:1–10", "116:10–19") in psalms
    assert ("146:1–11", "147:1–11") in psalms
    assert ("147:1–9", "147:12–20") in psalms
    assert ("114", "116") not in psalms
    assert ("146", "147") not in psalms


def test_the_page_prints_its_tables(edition: bible.pipeline.Edition) -> None:
    page = usj.serialize(edition.numbering_page)
    assert "{" not in page and "}" not in page
    # Only the book-name table moved; all chapter-and-verse rows remain.
    assert page.count("\\tr\n\\tc1 ") == 441
    # A run that keeps its numbers but stands out of their order says where.
    assert "\\tr\n\\tc1 23:7–8\n\\tc2 23:7–8 (after 40)\n" in page
    assert "\\tr\n\\tc1 31:25\n\\tc2 31:25 (after 26)\n" in page
    assert "\\s1 Jeremias\n" in page
    assert "\\s1 Genesis\n" in page
    assert "\\th1 \\sc " not in page
    assert "\\is2" not in page
    tables = [
        node
        for node in usj.walk(edition.numbering_page["content"])
        if usj.is_type(node, "table")
    ]
    # The Old Testament's, and four of the New Testament's.
    assert len(tables) == 34
    for table in tables:
        heading = next(usj.objects(table["content"]))
        assert sum(n.get("marker") == "th1" for n in usj.walk(table["content"])) == 1
        assert heading["marker"] == "tr"
        cells = list(usj.objects(heading["content"]))
        assert [cell["marker"] for cell in cells] == ["th1", "th2"]
        assert [cell["content"] for cell in cells] == [
            ["King James Bible"],
            ["Orthodox Liturgical English Bible"],
        ]
    intro = usj.serialize(edition.documents["introduction"])
    assert "\\s1 The Books and Their Order\n" in intro
    assert "\\s1 Names\n" in intro
    for ours, theirs in (
        ("3 Kingdoms", "1 Kings"),
        ("Epistle of Jeremias", "Baruch 6 (Apocrypha)"),
        ("3 Maccabees", "(\\it missing\\it*)"),
    ):
        assert f"\\tr\n\\tc1 {theirs}\n\\tc2 {ours}\n" in intro
    assert "as Proverbs 22:8a, is usually an addition" in page
    assert "the Prayer of Azarias and the Song stand within chapter 3" in intro
    assert "as 2:28–32 beside 3:1–5, they answer" in page
    # Esther's verses that are the King James Bible's Rest of Esther.
    assert (
        "\\tc1 The Rest of Esther (Apocrypha)\n\\tc2 Esther, the additions\n" in intro
    )
    assert "\\tc1 one lower" not in page and "\\tc1 two lower" not in page
    assert "\\tr\n\\tc1 (\\it missing\\it*)\n\\tc2 151\n" in page
    blocks = list(usj.objects(edition.numbering_page["content"]))
    headings = [
        usj.text_of(block["content"]) for block in blocks if block.get("marker") == "s1"
    ]
    # The Psalms' table stands at their place, directly after the editor's
    # explanation; neighboring tables need no blank paragraphs as padding.
    psalms = blocks.index(tables[headings.index("Psalms")])
    assert blocks[psalms - 2] == usj.para("s1", "Psalms")
    assert blocks[psalms - 1]["marker"] == "p"
    assert blocks[psalms + 1] == usj.para("s1", "Job")
    assert headings.index("Nehemias") < headings.index("Psalms")
    assert headings.index("Psalms") < headings.index("Job")
    # Books that are numbered alike have no table.
    assert "Judges" not in headings and "Ruth" not in headings


@pytest.mark.parametrize(
    "written",
    [
        "{books}\n{books}\n",
        "{books}\n{books}\n\\ip Psalms\n{psalms}\n",
        "{glosses}\n{glosses}\n",
        "{names}\n{names}\n",
        "{abbreviations}\n{abbreviations}\n",
    ],
)
def test_the_page_asks_for_each_table_at_most_once(
    printed: Printed, written: str
) -> None:
    with pytest.raises(CheckFailed, match="more than once"):
        printed(f"\\ip x\n{written}")


def test_the_page_tables_the_abbreviations_where_it_asks(
    printed: Printed, edition: bible.pipeline.Edition
) -> None:
    # Brenton's list, completed from the registry, as the pipeline finished it.
    page = printed("\\ip Before.\n{abbreviations}\n\\ip After.\n")
    table = usj.serialize(usj.document([edition.glossary]))
    assert page == "\\ip Before.\n" + table + "\\ip After.\n"
    assert "\\tr\n\\tc1 \\it KJV\\it*\n\\tc2 for King James Version\n" in page


@pytest.mark.parametrize(
    "written",
    [
        # Before the books, or with no words between the tables.
        "{psalms}\n{books}\n",
        "{books}\n{psalms}\n",
    ],
)
def test_the_psalms_have_their_words_between_the_books_and_their_table(
    printed: Printed, written: str
) -> None:
    with pytest.raises(CheckFailed, match="Words for the Psalms"):
        printed(f"\\ip x\n{written}")


@pytest.mark.parametrize(
    "named,cited",
    [
        ("{PSA 33:13-17}", "Psalm 33:13–17"),
        ("{kjv PSA 33:13-17}", "Psalm 34:12–16"),
        ("{kjv bare PSA 33:13-17}", "34:12–16"),
        ("{bare MAL 4:1-6}", "4:1–6"),
        ("{JER 38:31-34}", "Jeremias 38:31–34"),
        ("{kjv JER 38:31-34}", "Jeremiah 31:31–34"),
        ("{kjv MIC 5:1}", "Micah 5:2"),
        ("{kjv 1SA 17:4}", "1 Samuel 17:4"),
        ("{2CO 9:7}", "2 Corinthians 9:7"),
        ("{PRO 22:8a}", "Proverbs 22:8a"),
        # Into more than one place.
        ("{kjv bare JER 25:13-16}", "25:13; 49:34–36"),
    ],
)
def test_a_passage_named_prints_as_the_files_have_it(
    printed: Printed, named: str, cited: str
) -> None:
    assert printed(f"\\ip so that {named} is") == f"\\ip so that {cited} is\n"


@pytest.mark.parametrize(
    "named,refusal",
    [
        ("{PSA 33:13-99}", "doesn't print"),
        ("{MAL 3:19-24}", "doesn't print"),
        ("{brenton MAL 3:19-24}", "no known way"),
        ("{kjv PRO 22:8a}", "King James Bible lacks"),
        ("{hebrew PSA 33:13}", "no known way"),
        ("{PSA 33}", "Malformed passage"),
        ("{table}", "Braces left"),
        ("{", "Braces left"),
    ],
)
def test_a_passage_misnamed_is_refused(
    printed: Printed, named: str, refusal: str
) -> None:
    with pytest.raises(CheckFailed, match=refusal):
        printed(f"\\ip so that {named} is")


def test_the_introduction_names_its_passages(
    edition: bible.pipeline.Edition,
    sources: bible.sources.Sources,
) -> None:
    written = sources.authored["content/introduction.sfm"]
    page = usj.serialize(edition.documents["introduction"])
    # Passage references are generated: a chapter and verse typed in the
    # introduction's own words names a passage in braces, so that it is
    # checked and printed under the edition's names, except for the
    # passages the edition does not print, the King James Bible's and the
    # Hebrew's labels of Proverbs' displaced passages, which the page
    # discusses. Footnotes cite the sources by their own numbering, and the
    # works cited give a recording's length.
    typed = re.sub(r"\\f \+.*?\\f\*", "", written, flags=re.S)
    typed = re.sub(r"^\\li1 .*$", "", typed, flags=re.M)
    typed = re.sub(r"\{[^{}]*\}", "", typed)
    allowed = (
        "Luke 17:36",
        "Acts 8:37",
        "Acts 15:34",
        "Acts 24:7",
        "John 7:53–8:11",
        "Daniel 3:24–90",
        "2 Esdras 1:39–40",
        "30:15–33",
        "30:1–14",
        "31:1–9",
        "30:15",
        "31:10",
        "31:1",
        "30:1",
        "24:23",
    )
    for reference in allowed:
        # Whole references alone: 30:1 excuses neither 130:1 nor 30:10.
        exact = re.compile(rf"(?<![\d:–]){re.escape(reference)}(?![\d–])")
        assert exact.search(typed), reference
        typed = exact.sub("", typed)
    assert not re.search(r"\d+:\d+", typed)
    assert "\\tr " not in written
    assert "{" not in page and "}" not in page
    # Concrete examples include a renamed book and both Testaments.
    for named, printed in (
        ("1KI 14:3", "3 Kingdoms 14:3"),
        ("EZK 1:14", "Ezekiel 1:14"),
        ("JHN 3:7", "John 3:7"),
        ("REV 22:19", "Revelation 22:19"),
    ):
        assert "{" + named + "}" in written
        assert "(" + printed + ")" in page


def test_the_introductions_scripture_quotes_match_the_prepared_edition(
    edition: bible.pipeline.Edition,
) -> None:
    introduction = usj.text_of(edition.documents["introduction"]["content"])
    for code, reference in (
        ("JHN", "3:7"),
        ("REV", "22:19"),
        ("EZK", "1:14"),
        ("1KI", "14:3"),
        ("MAT", "21:16"),
        ("GEN", "3:22"),
    ):
        text = scripture.verses(edition.documents[code])[reference].text
        if code == "MAT":
            text = text[text.index("Yea;") :]
        elif code == "GEN":
            text = text[: text.index(", Behold,")]
        assert text.rstrip(".") in introduction, (code, reference)


def test_the_introduction_tables_the_glosses_by_turpies_classes(
    edition: bible.pipeline.Edition,
) -> None:
    # Each gloss the links print, beside the classes of Turpie's it is
    # printed for and what it means: C is divided, as crossrefs.agreement
    # divides it.
    # The introduction's tables are known by their heads: the glosses'
    # beside the names'.
    [(heads, *rows)] = [
        rows
        for b in edition.documents["introduction"]["content"]
        if b["type"] == "table"
        for rows in [
            [
                tuple(
                    usj.text_of(cell["content"]) for cell in usj.objects(row["content"])
                )
                for row in usj.objects(b["content"])
            ]
        ]
        if rows[0] == ("Gloss", "Turpie’s classes", "Meaning")
    ]
    assert [(gloss, classes) for gloss, classes, _ in rows] == [
        ("Heb.\u00a0+ LXX", "A, C\u00a0I"),
        ("Heb.\u00a0≠ LXX", "B"),
        ("LXX\u00a0≠ Heb.", "D"),
        ("reference alone", "C\u00a0II, C\u00a0III, E"),
    ]
    assert [meaning for *_, meaning in rows] == [
        crossrefs.GLOSS_MEANINGS[a] for a in ("A", "B", "D", None)
    ]


def test_the_editors_pages_write_the_registrys_terms(
    policy: bible.policy.Policy, edition: bible.pipeline.Edition
) -> None:
    # The editor's pages write their abbreviations by hand, so they are held
    # to the registry: the labels of the textual variants.
    terms = terminology.registry(policy)
    variants = usj.serialize(edition.variants_page)
    for identity in (
        "textus-receptus",
        "robinson-pierpont",
        "king-james-version",
        "orthodox-liturgical-english-bible",
    ):
        assert f"({terms.display(identity)})" in variants


def test_every_exception_is_in_the_table(
    policy: bible.policy.Policy, rows: Callable[[str], list[tuple[str, str]]]
) -> None:
    # Each exception pairs Turpie's English number with Brenton's, and the
    # table gives Brenton's beside the King James Bible's.
    for source, exception in policy.quotations["lxx_to_edition"].items():
        if exception.get("numbering") != "kjv":
            continue
        theirs = versification.verses(source)[0]
        ours = versification.lxx_to_edition(theirs, policy=policy)
        assert any(
            ours in read_cell(here, ours.book) and theirs in read_cell(there, ours.book)
            for here, there in rows(ours.book)
        ), source


def test_a_page_is_written_of_the_books_and_verses_it_is_given(
    policy: bible.policy.Policy,
    edition: bible.pipeline.Edition,
    facing: Inventory,
    names: tuple[bible.references.Books, ...],
    printed: Printed,
) -> None:
    def named(codes: Iterable[str]) -> list[tuple[str, ...]]:
        table = numbering.names_table(tuple(codes), facing, *names, policy=policy)
        return [
            tuple(usj.text_of(cell["content"]) for cell in usj.objects(row["content"]))
            for row in usj.objects(table["content"])
        ]

    full = named(edition.inventory)
    tobit = ("Tobit (Apocrypha)", "Tobit")
    assert tobit not in full
    assert all(theirs != f"{ours} (Apocrypha)" for theirs, ours in full[1:])
    for name in (
        "Prayer of Manasses",
        "1 Esdras",
        "Tobit",
        "Judith",
        "1 Maccabees",
        "2 Maccabees",
        "Wisdom of Solomon",
        "Bel and the Dragon",
    ):
        assert (f"{name} (Apocrypha)", name) not in full
    # A book that the edition lacks is missing on its side.
    assert full[-1] == ("2 Esdras (Apocrypha)", "(missing)")
    assert named(c for c in edition.inventory if c != "TOB") == [
        *(row for row in full[:-1] if row != tobit),
        ("Tobit (Apocrypha)", "(missing)"),
        full[-1],
    ]
    proverbs = {**edition.inventory["PRO"], "22": ["1", "2"]}
    with pytest.raises(CheckFailed, match="edition doesn't print"):
        printed("\\ip {PRO 22:8a}", inventory={**edition.inventory, "PRO": proverbs})


def test_generated_names_share_the_body_heading_registry(
    policy: bible.policy.Policy,
    sources: bible.sources.Sources,
    printed: Printed,
    edition: bible.pipeline.Edition,
) -> None:
    def rename(data: dict[str, Any]) -> None:
        unit = next(unit for unit in data["scripture"] if unit["id"] == "JER")
        unit["short_title"] = "Renamed Jeremias"

    ours = assembly.books(changed(policy, "manifest", rename), edition.documents)
    written = sources.authored[NUMBERING["file"]] + "\\ip {JER 38:31}\n"
    page = printed(written, ours=ours)
    names_page = printed("{names}\n", ours=ours)
    assert "\\tr\n\\tc1 Jeremiah\n\\tc2 Renamed Jeremias\n" in names_page
    assert "\\s1 Renamed Jeremias\n" in page
    assert page.endswith("\\ip Renamed Jeremias 38:31\n")


@pytest.mark.parametrize(
    "written", ["{books}\n", "{psalms}\n", "{glosses}\n{psalms}\n"]
)
def test_a_page_asks_for_the_books_and_the_psalms_as_a_pair(
    printed: Printed, written: str
) -> None:
    with pytest.raises(CheckFailed, match="not asked for as a pair"):
        printed(written)
