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
from bible import assembly, numbering, quotations, usfm, usj, versification
from bible.checks import CheckFailed
from bible.numbering import WANTING, Psalter, Table, within
from bible.policy import EDITOR, NUMBERING
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
def names(
    policy: bible.policy.Policy, sources: bible.sources.Sources
) -> tuple[bible.references.Books, ...]:
    """Both Bibles' names for their books: the edition's, and the King James."""
    return assembly.books(policy, sources), assembly.kjv_books(policy, sources)


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
            numbering.page(written, inventory, facing, ours, names[1], policy=policy)
        )

    return page


@pytest.fixture(scope="module")
def rows(
    policy: bible.policy.Policy, edition: bible.pipeline.Edition, facing: Inventory
) -> Callable[[str], list[tuple[str, str]]]:
    return lambda code: Table(code, edition.inventory, facing, policy=policy).rows()


@pytest.fixture(scope="module")
def psalter(
    policy: bible.policy.Policy, edition: bible.pipeline.Edition, facing: Inventory
) -> bible.numbering.Psalter:
    return Psalter(facing, printed=edition.inventory, policy=policy)


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
    assert {("26", "46"), ("32", "25"), ("36", "29"), ("50", "43")} <= jeremias
    # A chapter in part is its verses.
    assert {
        ("38:1–34", "31:1–34"),
        ("51:1–30", "44:1–30"),
        ("51:31–35", "45:1–5"),
        ("25:15–19", "49:35–39"),
    } <= jeremias


def test_what_either_bible_lacks_is_wanting(
    rows: Callable[[str], list[tuple[str, str]]],
) -> None:
    jeremias = rows("JER")
    assert (WANTING, "39:4–13") in jeremias
    assert ("36:8", WANTING) in rows("EXO")
    # Where the King James Bible has it, among the rows of its chapter.
    at = jeremias.index((WANTING, "33:14–26"))
    assert jeremias[at - 1] == ("40", "33") and jeremias[at + 1] == ("41", "34")


def test_a_verse_may_stand_beside_two(
    rows: Callable[[str], list[tuple[str, str]]],
) -> None:
    assert rows("LEV")[:5] == [
        ("5:20–26", "6:1–7"),
        ("6:1–23", "6:8–30"),
        ("8:18", "8:18–19"),
        ("8:19–28", "8:20–29"),
        ("8:29–30", "8:30"),
    ]
    assert ("9:2a–f", "8:30–35") in rows("JOS")
    # Proverbs 8:28 also holds the first part of the King James Bible's 8:29,
    # which the row says without giving 8:29 both.
    assert ("8:28", "8:28–29") in rows("PRO")
    assert ("8:28–29", "8:28–29") not in rows("PRO")
    # Malachias ends in another order.
    assert rows("MAL") == [("4:4–5", "4:5–6"), ("4:6", "4:4")]


def test_a_run_that_keeps_its_numbers_has_no_row(
    policy: bible.policy.Policy, rows: Callable[[str], list[tuple[str, str]]]
) -> None:
    # Genesis 31:47-48 is read to keep its numbers, against the words.
    kept = [
        (run["edition"], run["kjv"])
        for run in policy.versification["kjv"]["GEN"]
        if run.get("by") == "reading"
    ]
    assert kept == [("GEN 31:47-48", "GEN 31:47-48")]
    assert not [row for row in rows("GEN") if row[0] == row[1]]
    assert rows("JDG") == rows("RUT") == []


def read_cell(cell: str, book: str) -> list[bible.references.Verse]:
    """The verses a cell names, read back from what it prints; none, if it
    names a whole chapter or says that its verses are wanting."""
    verses = []
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
    psalter: bible.numbering.Psalter,
) -> None:
    """Read back, the rows give every verse the King James verses that the
    runs give it, and every verse they don't name keeps its number. A psalm
    whose verses the table numbers together is numbered there."""
    _, uneven = psalter.steps()
    for code in policy.versification["old_testament"]:
        table = Table(code, edition.inventory, facing, policy=policy)
        kjv = versification.kjv_book(code, policy=policy)
        told: dict[Verse, tuple[Verse, ...]] = {}
        for ours, theirs in table.rows() if code != "PSA" else psalter.uneven_rows():
            if ours == WANTING:
                for verse in read_cell(theirs, kjv):
                    assert versification.from_kjv(verse, policy=policy) == ()
                continue
            if ":" not in ours:
                # A chapter that stands whole elsewhere.
                for verse in table.verses(ours):
                    if not verse.letter:
                        told[verse] = (Verse(kjv, int(theirs), verse.number),)
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
                elif code == "PSA" and verse.chapter not in uneven:
                    continue
                elif verse in told:
                    assert told[verse] == found, (str(verse), told[verse], found)
                elif verse.letter:
                    assert found == (), str(verse)
                else:
                    assert found == (Verse(kjv, verse.chapter, verse.number),)


def test_psalms_are_numbered_as_the_greek_numbers_them(
    psalter: bible.numbering.Psalter,
) -> None:
    assert psalter.numbers() == [
        ("Psalm 9", "Psalms 9–10"),
        ("Psalms 10–112", "Psalms 11–113"),
        ("Psalm 113", "Psalms 114–115"),
        ("Psalms 114–115", "Psalm 116"),
        ("Psalms 116–145", "Psalms 117–146"),
        # Together one, as Psalms 114-115 are: Psalm 146 isn't the whole of
        # the King James Bible's 147.
        ("Psalms 146–147", "Psalm 147"),
        ("Psalm 151", WANTING),
    ]


def test_a_psalms_title_is_counted(
    policy: bible.policy.Policy, psalter: bible.numbering.Psalter
) -> None:
    steps, uneven = psalter.steps()
    assert steps[2] == [50, 51, 53, 59]
    assert steps[1][:8] == [3, 4, 5, 6, 7, 8, 11, 17] and len(steps[1]) == 57
    assert uneven == [9, 12, 113, 115, 147]
    # Outside the psalms that have rows of their own, a verse is the King
    # James verse of the same number, or so many lower, or the title.
    numbers = {}
    for ours, theirs in psalter.numbers():
        first, _, last = ours.split(" ")[1].partition("–")
        there, _, end = theirs.split(" ")[-1].partition("–")
        if last and end:
            for n in range(int(first), int(last) + 1):
                numbers[n] = int(there) + n - int(first)
    for step, psalms in steps.items():
        for psalm in psalms:
            for verse in psalter.table.verses(psalm):
                found = versification.to_kjv(verse, policy=policy)
                if verse.number <= step:
                    assert [v.number for v in found] == [versification.TITLE]
                else:
                    [kjv] = found
                    assert kjv.number == verse.number - step, str(verse)
                    assert kjv.chapter == numbers.get(psalm, psalm), str(verse)


def test_the_page_prints_its_tables(edition: bible.pipeline.Edition) -> None:
    page = usj.serialize(edition.documents[NUMBERING["id"]])
    assert "{" not in page and "}" not in page
    assert page.count("\\tr\n\\tc1 ") == 408
    assert "\\is1 Jeremias (Jeremiah)\n\\tr\n\\th1 Jeremias\n\\th2 Jeremiah\n" in page
    assert "\\is1 Genesis\n\\tr\n\\th1 This edition\n\\th2 King James Bible\n" in page
    for ours, theirs in (
        ("3 Kingdoms", "1 Kings"),
        ("Epistle of Jeremias", "Baruch 6, in the Apocrypha"),
        ("Tobit", "Tobit, in the Apocrypha"),
        ("3 Maccabees", WANTING),
    ):
        assert f"\\tr\n\\tc1 {ours}\n\\tc2 {theirs}\n" in page
    assert "as Proverbs 22:8a, is an addition" in page
    assert "so that Psalm 33:13–17 is its 34:12–16." in page
    # Books that are numbered alike have no table.
    assert "\\is1 Judges" not in page and "\\is1 Ruth" not in page


@pytest.mark.parametrize(
    "more", ["", "{names}\n{psalm numbers}\n{psalm verses}\n{psalm rows}\n"]
)
def test_the_page_asks_for_each_table_once(printed: Printed, more: str) -> None:
    # All five, or none; and none twice.
    with pytest.raises(CheckFailed, match="not once each"):
        printed(f"\\ip x\n{{names}}\n{{books}}\n{more}")


@pytest.mark.parametrize(
    "named,cited",
    [
        ("{PSA 33:13-17}", "Psalm 33:13–17"),
        ("{kjv PSA 33:13-17}", "Psalm 34:12–16"),
        ("{kjv bare PSA 33:13-17}", "34:12–16"),
        ("{bare MAL 4:1-6}", "4:1–6"),
        ("{brenton MAL 3:19-24}", "Malachias 3:19–24"),
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
        ("{brenton MAL 3:1-5}", "doesn't relabel"),
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
    policy: bible.policy.Policy,
    edition: bible.pipeline.Edition,
    sources: bible.sources.Sources,
) -> None:
    written = sources.authored[EDITOR["file"]]
    page = usj.serialize(edition.documents[EDITOR["id"]])
    # No chapter and verse is typed: each is a passage named, which the files
    # are held to.
    assert not re.search(r"\d+:\d+", re.sub(r"\{[^{}]*\}", "", written))
    assert "\\tr " not in written
    assert "so that Psalm 33:13–17 is the King James Bible’s 34:12–16." in page
    assert "so that Jeremias 38:31–34 is the King James Bible’s 31:31–34." in page
    assert "and Malachias 3:19–24 is numbered 4:1–6, again" in page
    # A Septuagint addition that Brenton letters has no King James number,
    # so the introduction names the one that a link stands at.
    linked = {
        str(verse)
        for row in quotations.reviewed_rows(policy=policy)
        for verse in quotations.brenton_verses(row["ot"], policy=policy)
        if verse.letter
    }
    assert linked == {"PRO 22:8a"}
    assert "of 2 Corinthians 9:7 is found at Proverbs 22:8a." in page


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
    names: tuple[bible.references.Books, ...],
    printed: Printed,
) -> None:
    def named(codes: Iterable[str]) -> list[tuple[str, ...]]:
        table = numbering.names_table(tuple(codes), *names, policy=policy)
        return [
            tuple(usj.text_of(cell["content"]) for cell in usj.objects(row["content"]))
            for row in usj.objects(table["content"])
        ]

    full = named(edition.inventory)
    tobit = ("Tobit", "Tobit, in the Apocrypha")
    assert tobit in full
    assert named(c for c in edition.inventory if c != "TOB") == [
        row for row in full if row != tobit
    ]
    proverbs = {**edition.inventory["PRO"], "22": ["1", "2"]}
    with pytest.raises(CheckFailed, match="edition doesn't print"):
        printed("\\ip {PRO 22:8a}", inventory={**edition.inventory, "PRO": proverbs})


def test_generated_names_share_the_body_heading_registry(
    policy: bible.policy.Policy,
    sources: bible.sources.Sources,
    printed: Printed,
) -> None:
    def rename(data: dict[str, Any]) -> None:
        unit = next(unit for unit in data["scripture"] if unit["id"] == "JER")
        unit["short_title"] = "Renamed Jeremias"

    ours = assembly.books(changed(policy, "manifest", rename), sources)
    written = sources.authored[NUMBERING["file"]] + "\\ip {JER 38:31}\n"
    page = printed(written, ours=ours)
    assert "\\tr\n\\tc1 Renamed Jeremias\n\\tc2 Jeremiah\n" in page
    assert "\\is1 Renamed Jeremias (Jeremiah)\n" in page
    assert page.endswith("\\ip Renamed Jeremias 38:31\n")
