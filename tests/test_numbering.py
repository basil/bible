"""The table of chapters and verses, and the passages the editor's pages name."""

import re

import pytest

from bible import edition, numbering, paths, quotations, versification
from bible.checks import CheckFailed
from bible.numbering import WANTING, Psalter, Table, within
from bible.references import Verse, parse_verse


@pytest.fixture(scope="module")
def inventory(archives):
    return versification.edition_inventory(archives)


@pytest.fixture(scope="module")
def facing(archives):
    return numbering.kjv_inventory(archives)


@pytest.fixture(scope="module")
def page(archives):
    """The table's page as it prints."""
    written = (paths.CONTENT_DIR / "numbering.sfm").read_text(encoding="utf-8")
    return numbering.page(written, archives)


@pytest.fixture(scope="module")
def introduction(archives):
    written = (paths.CONTENT_DIR / "introduction.sfm").read_text(encoding="utf-8")
    return written, numbering.page(written, archives)


def rows(code, inventory, facing):
    return Table(code, inventory, facing).rows()


@pytest.mark.parametrize(
    "verses,printed",
    [
        (["LEV 8:19", "LEV 8:20", "LEV 8:21"], "8:19–21"),
        (["LEV 8:18"], "8:18"),
        (["JOS 9:2a", "JOS 9:2b", "JOS 9:2c"], "9:2a–c"),
        (["JER 10:5", "JER 10:9a"], "10:5, 9a"),
        (["ISA 8:23", "ISA 9:1"], "8:23; 9:1"),
        (["1KI 16:28d", "1KI 16:28e", "1KI 22:46"], "16:28d–e; 22:46"),
    ],
)
def test_verses_print_chapter_by_chapter(verses, printed):
    assert within(list(map(parse_verse, verses))) == printed


def test_a_chapter_that_stands_whole_elsewhere_is_one_row(inventory, facing):
    jeremias = rows("JER", inventory, facing)
    for ours, theirs in (("26", "46"), ("32", "25"), ("36", "29"), ("50", "43")):
        assert (ours, theirs) in jeremias
    # A chapter in part is its verses.
    assert ("38:1–34", "31:1–34") in jeremias
    assert ("51:1–30", "44:1–30") in jeremias and ("51:31–35", "45:1–5") in jeremias
    assert ("25:15–19", "49:35–39") in jeremias


def test_what_either_bible_lacks_is_wanting(inventory, facing):
    jeremias = rows("JER", inventory, facing)
    assert (WANTING, "33:14–26") in jeremias
    assert (WANTING, "39:4–13") in jeremias
    assert ("36:8", WANTING) in rows("EXO", inventory, facing)
    # Where the King James Bible has it, among the rows of its chapter.
    at = jeremias.index((WANTING, "33:14–26"))
    assert jeremias[at - 1] == ("40", "33") and jeremias[at + 1] == ("41", "34")


def test_a_verse_may_stand_beside_two(inventory, facing):
    leviticus = rows("LEV", inventory, facing)
    assert leviticus[:5] == [
        ("5:20–26", "6:1–7"),
        ("6:1–23", "6:8–30"),
        ("8:18", "8:18–19"),
        ("8:19–28", "8:20–29"),
        ("8:29–30", "8:30"),
    ]
    assert ("9:2a–f", "8:30–35") in rows("JOS", inventory, facing)


def test_malachias_ends_in_another_order(inventory, facing):
    assert rows("MAL", inventory, facing) == [("4:4–5", "4:5–6"), ("4:6", "4:4")]


def test_proverbs_table_identifies_the_partial_overlap(inventory, facing):
    assert ("8:28", "8:28–29") in rows("PRO", inventory, facing)
    assert ("8:28–29", "8:28–29") not in rows("PRO", inventory, facing)


def test_a_run_that_keeps_its_numbers_has_no_row(inventory, facing):
    # Genesis 31:47-48 is read to keep its numbers, against the words.
    kept = [
        run for run in versification.DATA["kjv"]["GEN"] if run.get("by") == "reading"
    ]
    assert [(run["edition"], run["kjv"]) for run in kept] == [
        ("GEN 31:47-48", "GEN 31:47-48")
    ]
    assert not [row for row in rows("GEN", inventory, facing) if row[0] == row[1]]
    assert rows("JDG", inventory, facing) == rows("RUT", inventory, facing) == []


def read_cell(cell, book):
    """The verses a cell names, read back from what it prints."""
    verses = []
    for part in cell.split("; "):
        chapter, _, listed = part.partition(":")
        for stretch in listed.split(", "):
            first, _, last = stretch.partition("–")
            number, letter = re.fullmatch(r"(\d+)([a-z]?)", first).groups()
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


def test_the_table_says_what_the_file_says(inventory, facing, archives):
    """Read back, the rows give every verse the King James verses that the
    file gives it, and every verse they don't name keeps its number. A psalm
    whose verses the table numbers together is numbered there."""
    psalter = Psalter(archives)
    steps, uneven = psalter.steps()
    for code in versification.DATA["old_testament"]:
        table = Table(code, inventory, facing)
        kjv = versification.kjv_book(code)
        printed = table.rows() if code != "PSA" else psalter.uneven_rows()
        told = {}
        for ours, theirs in printed:
            if ours == WANTING:
                for verse in read_cell(theirs, kjv):
                    assert versification.from_kjv(verse) == (), (code, theirs)
                continue
            if ":" not in ours:
                # A chapter that stands whole elsewhere.
                for verse in table.verses(ours):
                    if not verse.letter:
                        told[verse] = (Verse(kjv, int(theirs), verse.number),)
                continue
            here = read_cell(ours, code)
            there = () if theirs == WANTING else tuple(read_cell(theirs, kjv))
            pairs = (
                zip(here, ((verse,) for verse in there))
                if len(here) == len(there)
                else ((verse, there) for verse in here)
            )
            for verse, facing_it in pairs:
                assert verse not in told, (code, str(verse))
                told[verse] = facing_it
        for chapter in table.ours:
            for verse in table.verses(chapter):
                if verse in versification.apocryphal():
                    continue
                facing_it = versification.to_kjv(verse)
                found = tuple(v for v in facing_it if v.number != versification.TITLE)
                if facing_it and not found:
                    # A title, which the King James Bible doesn't number.
                    assert verse not in told
                    continue
                same = (Verse(kjv, verse.chapter, verse.number),)
                if code == "PSA" and verse.chapter not in uneven:
                    continue
                if verse in told:
                    assert told[verse] == found, (str(verse), told[verse], found)
                elif verse.letter:
                    assert found == (), str(verse)
                else:
                    assert found == same, (str(verse), found)


def test_the_psalms_verses_are_as_the_table_numbers_them(archives):
    # Outside the psalms that have rows of their own, a verse is the King
    # James verse of the same number, or so many lower, or the title.
    psalter = Psalter(archives)
    steps, uneven = psalter.steps()
    lower = {psalm: step for step, psalms in steps.items() for psalm in psalms}
    numbers = {}
    for ours, theirs in psalter.numbers():
        first, _, last = ours.split(" ")[1].partition("–")
        if theirs == WANTING:
            continue
        there, _, end = theirs.split(" ")[1].partition("–")
        if (last or first) != first and (end or there) != there:
            for n in range(int(first), int(last) + 1):
                numbers[n] = int(there) + n - int(first)
    for psalm, step in lower.items():
        for verse in psalter.table.verses(psalm):
            found = versification.to_kjv(verse)
            if verse.number <= step:
                assert [v.number for v in found] == [versification.TITLE], str(verse)
            else:
                [kjv] = found
                assert kjv.number == verse.number - step, str(verse)
                assert kjv.chapter == numbers.get(psalm, psalm), str(verse)


def test_psalms_are_numbered_as_the_greek_numbers_them(archives):
    assert Psalter(archives).numbers() == [
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


def test_a_psalms_title_is_counted(archives):
    steps, uneven = Psalter(archives).steps()
    assert steps[2] == [50, 51, 53, 59]
    assert steps[1][:8] == [3, 4, 5, 6, 7, 8, 11, 17] and len(steps[1]) == 57
    assert uneven == [9, 12, 113, 115, 147]
    # As the words show, and the verses a link names: Psalm 33:13-17.
    for verse in range(13, 18):
        [kjv] = versification.to_kjv(parse_verse(f"PSA 33:{verse}"))
        assert (kjv.chapter, kjv.number) == (34, verse - 1)


def test_the_page_prints_its_tables(page):
    assert "{" not in page and "}" not in page
    # The selective review restores the missing-verse rows for 1KI 6:11–14
    # and 2CH 27:8, whose English remains in the Appendix.
    # Proverbs 8:28 now also holds the first part of King James 8:29.
    assert page.count("\\tr \\tc1 ") == 408
    assert "\\is1 Jeremias (Jeremiah)\n\\tr \\th1 Jeremias \\th2 Jeremiah\n" in page
    assert "\\is1 Genesis\n\\tr \\th1 This edition \\th2 King James Bible\n" in page
    assert "\\tr \\tc1 3 Kingdoms \\tc2 1 Kings\n" in page
    assert "\\tr \\tc1 Epistle of Jeremias \\tc2 Baruch 6, in the Apocrypha\n" in page
    assert "\\tr \\tc1 Tobit \\tc2 Tobit, in the Apocrypha\n" in page
    assert "\\tr \\tc1 3 Maccabees \\tc2 wanting\n" in page
    assert "as Proverbs 22:8a, is an addition" in page
    assert "so that Psalm 33:13–17 is its 34:12–16." in page
    # Books that are numbered alike have no table.
    assert "\\is1 Judges" not in page and "\\is1 Ruth" not in page


def test_the_page_asks_for_each_table_once(archives):
    with pytest.raises(CheckFailed, match="not once each"):
        numbering.tables("\\ip x\n{names}\n{books}\n", archives)
    with pytest.raises(CheckFailed, match="not once each"):
        numbering.tables(
            "{names}\n{names}\n{psalm numbers}\n{psalm verses}\n{psalm rows}\n{books}",
            archives,
        )


@pytest.mark.parametrize(
    "named,printed",
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
def test_a_passage_named_prints_as_the_files_have_it(archives, named, printed):
    assert numbering.cited(f"so that {named} is", archives) == f"so that {printed} is"


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
        ("so {", "Braces left"),
    ],
)
def test_a_passage_misnamed_is_refused(archives, named, refusal):
    with pytest.raises(CheckFailed, match=refusal):
        numbering.cited(f"so that {named} is", archives)


def test_the_introduction_names_its_passages(introduction):
    written, printed = introduction
    # No chapter and verse is typed: each is a passage named, which the files
    # are held to.
    assert not re.search(r"\d+:\d+", re.sub(r"\{[^{}]*\}", "", written))
    assert "\\tr " not in written
    assert "so that Psalm 33:13–17 is the King James Bible’s 34:12–16." in printed
    assert "so that Jeremias 38:31–34 is the King James Bible’s 31:31–34." in printed
    assert "and Malachias 3:19–24 is numbered 4:1–6, again" in printed
    assert "of 2 Corinthians 9:7 is found at Proverbs 22:8a." in printed


def test_a_linked_lettered_verse_is_named(introduction):
    # A Septuagint addition that Brenton letters has no King James number,
    # so the introduction names the one that a link stands at.
    linked = {
        verse
        for row in quotations.reviewed_rows()
        for verse in quotations.brenton_verses(row["ot"])
        if verse.letter
    }
    assert {str(verse) for verse in linked} == {"PRO 22:8a"}
    assert "Proverbs 22:8a" in introduction[1]


def test_every_exception_is_in_the_table(inventory, facing):
    # Each exception pairs Turpie's English number with Brenton's, and the
    # table gives Brenton's beside the King James Bible's.
    for source, exception in versification.EXCEPTIONS.items():
        if exception.get("numbering") != "kjv":
            continue
        excepted = versification.verses(source)
        ours = [versification.lxx_to_edition(verse) for verse in excepted]
        printed = rows(excepted[0].book, inventory, facing)
        covered = [
            row
            for row in printed
            if re.match(rf"{ours[0].chapter}:", row[0])
            and str(excepted[0].number) in re.findall(r"\d+", row[1].split(":")[-1])
            or _spans(row[1], excepted[0])
        ]
        assert covered, source


def _spans(cell, verse):
    """Whether a cell of King James verses takes in a verse."""
    for part in cell.split("; "):
        chapter, _, verses = part.partition(":")
        if chapter != str(verse.chapter):
            continue
        for stretch in verses.split(", "):
            first, _, last = stretch.partition("–")
            if first.isdigit() and int(first) <= verse.number <= int(last or first):
                return True
    return False


def test_the_kjv_names_are_the_kjvs(archives):
    names = edition.kjv_books(archives).names
    assert (names["JER"], names["MIC"], names["1SA"]) == (
        "Jeremiah",
        "Micah",
        "1 Samuel",
    )
    assert edition.kjv_books(archives).name("PSA", [34]) == "Psalm"
