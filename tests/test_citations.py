"""Citations read as each source writes them, into the edition's verses."""

import pytest

from bible import citations, edition, validate, versification
from bible.checks import CheckFailed
from bible.citations import Item, scan
from bible.references import parse_verse

HOME = parse_verse("JDG 13:8")


@pytest.fixture(scope="module")
def inventory(archives):
    return versification.edition_inventory(archives)


@pytest.fixture
def brenton():
    return citations.dialect("brenton")


@pytest.fixture
def george():
    return citations.dialect("george")


def read(found):
    """Citations as (source, what they name), a chapter as its book and number."""
    return [
        (
            citation.source,
            [
                str(item.passage(citation.book) or f"{citation.book} {item.chapter}")
                for run in citation.items
                for item in run
            ],
        )
        for citation in found
    ]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("See Rom. 4. 7,8.", [("Rom. 4. 7,8", ["ROM 4:7", "ROM 4:8"])]),
        ("See Heb. 2. 6-9.", [("Heb. 2. 6-9", ["HEB 2:6-9"])]),
        ("See 1 Cor 2. 16. Gr.", [("1 Cor 2. 16", ["1CO 2:16"])]),
        ("Comp. 2 Tim. 4. 14-17.", [("2 Tim. 4. 14-17", ["2TI 4:14-17"])]),
        (
            "See Lev. 23. 6; Num. 29. 35; 2 Chr. 7. 9.",
            [
                ("Lev. 23. 6", ["LEV 23:6"]),
                ("Num. 29. 35", ["NUM 29:35"]),
                ("2 Chr. 7. 9", ["2CH 7:9"]),
            ],
        ),
        (
            "Jer. 40. 10,12;also 1 Cor. 12. 15,16.",
            [
                ("Jer. 40. 10,12", ["JER 40:10", "JER 40:12"]),
                ("1 Cor. 12. 15,16", ["1CO 12:15", "1CO 12:16"]),
            ],
        ),
        # Brenton's Kings are the four books of Kingdoms.
        ("See 2 Kings 22. 16.", [("2 Kings 22. 16", ["2SA 22:16"])]),
        ("See on 3 Kings 8. 53.", [("3 Kings 8. 53", ["1KI 8:53"])]),
        # A chapter, and the last verse of one.
        ("as in Gen. 43.", [("Gen. 43", ["GEN 43"])]),
        ("See Col. 2. ult.", [("Col. 2. ult", ["COL 2:23"])]),
        # What the edition relabels is cited by Brenton's number for it.
        ("See Mic. 7. 18.", [("Mic. 7. 18", ["MIC 7:18"])]),
    ],
)
def test_brenton_cites_by_his_own_names_and_numbers(brenton, inventory, text, expected):
    assert read(scan(text, brenton, HOME, "x", inventory)) == expected


def test_a_relabelled_verse_is_cited_by_its_source_label(brenton, inventory, patched):
    patched(citations, "DATA")["dialects"]["brenton"]["books"]["Mal"] = "MAL"
    tongue = citations.dialect("brenton")
    found = scan("See Mal. 3. 23.", tongue, HOME, "x", inventory)
    assert read(found) == [("Mal. 3. 23", ["MAL 4:5"])]


@pytest.mark.parametrize(
    "text,relative,expected",
    [
        ("See ver. 6.", "verse", ["JDG 13:6"]),
        ("See ver 3.", "verse", ["JDG 13:3"]),
        ("See v 8.", "verse", ["JDG 13:8"]),
        ("Gr. See v. 19.", "verse", ["JDG 13:19"]),
        ("For vv. 2-5, see above.", "verse", ["JDG 13:2-5"]),
        ("Verses 5 to 8 are read.", "verse", ["JDG 13:5-8"]),
        ("See chap 6. 13,15.", "chapter", ["JDG 6:13", "JDG 6:15"]),
        ("See chap. 9. 2.", "chapter", ["JDG 9:2"]),
        ("See ch. 10. 12.", "chapter", ["JDG 10:12"]),
        ("See chap 5. 25; 14. 16.", "chapter", ["JDG 5:25", "JDG 14:16"]),
        ("See chapter 20.", "chapter", ["JDG 20"]),
    ],
)
def test_a_note_cites_its_own_book_by_verse_or_chapter(
    brenton, inventory, text, relative, expected
):
    [citation] = scan(text, brenton, HOME, "x", inventory)
    assert citation.relative == relative
    assert citation.book == "JDG"
    assert read([citation])[0][1] == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("as Mat. 18.28", ["MAT 18:28"]),
        ("see Matth. 10.9", ["MAT 10:9"]),
        ("1. Cor. 8.11", ["1CO 8:11"]),
        # The King James Bible's names and numbers, carried into the edition's.
        ("Gr. made, 1 Sam. 12.6", ["1SA 12:6"]),
        ("Esai 55.3", ["ISA 55:3"]),
        ("Deut. 1.31", ["DEU 1:31"]),
        ("2. Macc 7.27", ["2MA 7:27"]),
    ],
)
def test_the_margin_of_1611_cites_as_the_king_james_bible_does(
    george, inventory, text, expected
):
    [citation] = scan(text, george, parse_verse("MAT 1:1"), "x", inventory)
    assert read([citation])[0][1] == expected


def test_a_citation_by_the_king_james_numbering_is_carried_verse_by_verse(
    inventory, patched
):
    books = patched(citations, "DATA")["dialects"]["george"]["books"]
    books.update({"Joel": "JOL", "Psal": "PSA", "Jer": "JER", "Mal": "MAL"})
    george = citations.dialect("george")
    home = parse_verse("ACT 2:17")
    cases = {
        "Joel 2.28-32": ["JOL 3:1-5"],
        "Psal. 34.12-16": ["PSA 33:13-17"],
        "Jer. 31.31-34": ["JER 38:31-34"],
        # Into two places, where the edition has the verses apart.
        "Jer. 25.13-16": ["JER 25:13", "JER 32:15-16"],
        "Mal. 4.4-6": ["MAL 4:6", "MAL 4:4-5"],
    }
    for text, expected in cases.items():
        [citation] = scan(text, george, home, "x", inventory)
        assert read([citation])[0][1] == expected, text
    with pytest.raises(CheckFailed, match="Verses the edition lacks: JER 33:14-16"):
        scan("Jer. 33.14-16", george, home, "x", inventory)


@pytest.mark.parametrize(
    "text,unread",
    [
        ("See Nowhere 1. 1", "1. 1"),
        ("See Heb. 2. 6-9-11", "2. 6"),
        ("Vide supra, 13. 22.", "13. 22"),
        ("See chap. x. 9", "chap. x. 9|x. 9"),
    ],
)
def test_what_looks_like_a_citation_is_read_or_refused(
    brenton, inventory, text, unread
):
    with pytest.raises(CheckFailed, match=rf"can't be read: x \(({unread})"):
        scan(text, brenton, HOME, "x", inventory)


@pytest.mark.parametrize(
    "text",
    ["Alex. 187 years.", "Alex. 62,500.", "Heb. and Alex. 60 cubits.", "p. 92."],
)
def test_figures_alone_are_no_citation(brenton, inventory, text):
    assert scan(text, brenton, HOME, "x", inventory) == []


def test_what_is_cited_must_be_printed(brenton, inventory):
    with pytest.raises(CheckFailed, match=r"doesn't print: x \(Rom. 17. 1: ROM 17\)"):
        scan("See Rom. 17. 1.", brenton, HOME, "x", inventory)
    with pytest.raises(CheckFailed, match=r"\(Rom. 16. 27,28: ROM 16:28\)"):
        scan("See Rom. 16. 27,28.", brenton, HOME, "x", inventory)
    with pytest.raises(CheckFailed, match=r"\(ver. 99: JDG 13:99\)"):
        scan("See ver. 99.", brenton, HOME, "x", inventory)


def decided(patched, decision):
    patched(citations, "DATA")["decisions"]["x"] = decision


def test_a_decision_reads_a_citation_by_another_numbering(brenton, inventory, patched):
    text = "Comp. Jer. 9. 24."
    [as_written] = scan(text, brenton, HOME, "y", inventory)
    assert read([as_written])[0][1] == ["JER 9:24"]
    decided(patched, {"source": "Jer. 9. 24", "numbering": "kjv", "why": "x"})
    [citation] = scan(text, brenton, HOME, "x", inventory)
    assert read([citation])[0][1] == ["JER 9:23"]
    assert citation.numbering == "kjv"


def test_a_psalm_may_be_cited_by_the_greek_number_and_the_english_verse(
    brenton, inventory, patched
):
    decided(patched, {"source": "Ps. 91. 10", "numbering": "kjv-verses", "why": "x"})
    [citation] = scan("see Ps. 91. 10.", brenton, HOME, "x", inventory)
    assert read([citation])[0][1] == ["PSA 91:11"]


def test_a_psalm_may_be_cited_by_the_hebrew_number(brenton, inventory, patched):
    decided(patched, {"source": "Ps. 110", "numbering": "hebrew", "why": "x"})
    [citation] = scan("See Ps. 110.", brenton, HOME, "x", inventory)
    assert citation.items == ((Item(109),),)
    # Its verses aren't the King James Bible's, so none can be carried.
    decided(patched, {"source": "Ps. 110. 3", "numbering": "hebrew", "why": "x"})
    with pytest.raises(CheckFailed, match="Verses by the Hebrew's numbering"):
        scan("See Ps. 110. 3.", brenton, HOME, "x", inventory)


def test_a_decision_may_say_that_figures_are_no_citation(brenton, inventory, patched):
    with pytest.raises(CheckFailed, match=r"doesn't print: y \(Heb. 300: HEB 300\)"):
        scan("Heb. 300. Alex. 500.", brenton, HOME, "y", inventory)
    decided(patched, {"source": "Heb. 300", "not_a_citation": True, "why": "x"})
    assert scan("Heb. 300. Alex. 500.", brenton, HOME, "x", inventory) == []


def test_a_decision_may_cite_what_the_edition_does_not_print(
    brenton, inventory, patched
):
    decided(
        patched,
        {"source": "Verse 99", "unprinted": True, "print": "Verse 99", "why": "x"},
    )
    [citation] = scan("Verse 99 is not in Vat.", brenton, HOME, "x", inventory)
    assert (citation.items, citation.printed) == ((), "Verse 99")


def test_a_decision_may_name_the_passages_itself(brenton, inventory, patched):
    decided(
        patched,
        {"source": "13. 22", "passages": "ISA 13:22", "print": "13:22", "why": "x"},
    )
    [citation] = scan("Vide supra, 13. 22.", brenton, HOME, "x", inventory)
    assert read([citation])[0][1] == ["ISA 13:22"]
    assert citation.printed == "13:22"


def test_a_decision_may_read_several_books_as_one_citation(
    george, inventory, patched, archives
):
    decided(
        patched,
        {
            "source": "Zac. 3.8 esay 11.1",
            "passages": "ZEC 3:8; ISA 11:1",
            "print": "{ZEC} 3:8; {ISA} 11:1",
            "why": "x",
        },
    )
    [citation] = scan("branch, Zac. 3.8 esay 11.1", george, HOME, "x", inventory)
    assert read([citation])[0][1] == ["ZEC 3:8"]
    assert list(map(str, citation.passages)) == ["ZEC 3:8", "ISA 11:1"]
    books = edition.books(archives)
    assert citations.printed(citation, books) == "Zacharias 3:8; Esaias 11:1"
    # Each must be printed, whatever book it is of.
    decided(
        patched,
        {
            "source": "Zac. 3.8 esay 11.1",
            "passages": "ZEC 3:8; ISA 99:1",
            "print": "x",
            "why": "x",
        },
    )
    with pytest.raises(CheckFailed, match="doesn't print: x .*ISA 99"):
        scan("branch, Zac. 3.8 esay 11.1", george, HOME, "x", inventory)


PRINTED = [
    ("See Rom. 4. 7,8.", "Romans 4:7, 8"),
    ("See Heb. 2. 6-9.", "Hebrews 2:6–9"),
    ("See 2 Kings 22. 16.", "2 Kingdoms 22:16"),
    ("See Hab. 2. 3.", "Abbacum 2:3"),
    ("See Ps. 118. 32.", "Psalm 118:32"),
    ("See also Ps. 68; 79, titles", "Psalms 68; 79"),
    ("as in Gen. 43.", "Genesis 43"),
    ("See Col. 2. ult.", "Colossians 2:23"),
    ("See ver. 6.", "verse 6"),
    ("For vv. 2-5, see above.", "verses 2–5"),
    ("See v 8, 9.", "verses 8, 9"),
    ("Verse 5 is read.", "Verse 5"),
    ("See chap 6. 13,15.", "chapter 6:13, 15"),
    ("See chap 5. 25; 14. 16.", "chapter 5:25; 14:16"),
    ("See chapter 20.", "chapter 20"),
]


@pytest.mark.parametrize("text,expected", PRINTED)
def test_a_citation_prints_as_the_edition_cites(
    brenton, inventory, archives, text, expected
):
    [citation] = scan(text, brenton, HOME, "x", inventory)
    assert citations.printed(citation, edition.books(archives)) == expected


def test_a_notes_citations_are_references_of_their_own(brenton, inventory, archives):
    pieces = [
        ("label", "Gr. "),
        ("cited", "seed"),
        ("text", "; see "),
        ("xt", "Rom. 9. 29"),
    ]
    plain = "".join(text for _, text in pieces)
    found = scan(plain, brenton, HOME, "x", inventory)
    assert citations.normalized(pieces, found, edition.books(archives)) == [
        ("label", "Gr. "),
        ("cited", "seed"),
        ("text", "; see "),
        ("xt", "Romans 9:29"),
    ]
    # One that eBible leaves among the words, or marks in part, is marked whole.
    pieces = [
        ("text", "See chap "),
        ("xt", "6. 13,15"),
        ("text", ". Also 1 Cor 2. 16."),
    ]
    plain = "".join(text for _, text in pieces)
    found = scan(plain, brenton, HOME, "x", inventory)
    assert citations.normalized(pieces, found, edition.books(archives)) == [
        ("text", "See "),
        ("xt", "chapter 6:13, 15"),
        ("text", ". Also "),
        ("xt", "1 Corinthians 2:16"),
        ("text", "."),
    ]


def test_what_the_edition_does_not_print_stays_among_its_words(
    brenton, inventory, archives, patched
):
    decided(
        patched,
        {"source": "Verse 99", "unprinted": True, "print": "Verse 99", "why": "x"},
    )
    pieces = [("text", "Verse 99 is not in Vat.")]
    found = scan(pieces[0][1], brenton, HOME, "x", inventory)
    assert citations.normalized(pieces, found, edition.books(archives)) == pieces


def test_several_decisions_on_one_note_form_a_list(brenton, inventory, patched):
    decided(
        patched,
        [
            {"source": "Heb. 300", "not_a_citation": True, "why": "x"},
            {"source": "Jer. 9. 24", "numbering": "kjv", "why": "x"},
        ],
    )
    found = scan("Heb. 300. Comp. Jer. 9. 24.", brenton, HOME, "x", inventory)
    assert read(found) == [("Jer. 9. 24", ["JER 9:23"])]


@pytest.mark.parametrize(
    "decision,refusal",
    [
        ({"source": "Jer. 9. 24", "numbering": "kjv"}, "without a reason"),
        ({"source": "Jer. 9. 25", "numbering": "kjv", "why": "x"}, "not found once"),
        ({"source": "Jer. 9. 24", "why": "x"}, "decides nothing, or too much"),
        (
            {"source": "Jer. 9. 24", "numbering": "kjv", "print": "x", "why": "x"},
            "decides nothing, or too much",
        ),
        (
            {"source": "Jer. 9. 24", "numbering": "brenton", "why": "x"},
            "of no other numbering",
        ),
        (
            {"source": "Jer. 9. 24", "numbering": "english", "why": "x"},
            "of no other numbering",
        ),
        ({"source": "Comp.", "numbering": "kjv", "why": "x"}, "of no other numbering"),
        (
            {"source": "Jer. 9. 24", "passages": "JER 9:23", "why": "x"},
            "prints nothing",
        ),
    ],
)
def test_a_malformed_decision_is_refused(
    brenton, inventory, patched, decision, refusal
):
    decided(patched, decision)
    with pytest.raises(CheckFailed, match=refusal):
        scan("Comp. Jer. 9. 24.", brenton, HOME, "x", inventory)


def test_decisions_may_not_overlap(brenton, inventory, patched):
    decided(
        patched,
        [
            {"source": "Jer. 9. 24", "numbering": "kjv", "why": "x"},
            {"source": "9. 24", "not_a_citation": True, "why": "x"},
        ],
    )
    with pytest.raises(CheckFailed, match="decisions that overlap: x"):
        scan("Comp. Jer. 9. 24.", brenton, HOME, "x", inventory)


def test_a_dialect_says_how_it_numbers(patched):
    del patched(citations, "DATA")["dialects"]["brenton"]["numbering"]
    with pytest.raises(CheckFailed, match="without its numbering or numerals"):
        citations.dialect("brenton")


def test_every_decision_and_name_is_used(monkeypatch, patched):
    monkeypatch.setattr(validate.paths, "BUILD_DIR", validate.paths.BUILD_DIR / "test")
    data = patched(citations, "DATA")
    data["decisions"]["GEN 1:1"] = {"source": "x", "not_a_citation": True, "why": "x"}
    with pytest.raises(CheckFailed, match=r"Unused citation decisions: \['GEN 1:1'\]"):
        validate.validate()
    del data["decisions"]["GEN 1:1"]
    data["dialects"]["brenton"]["books"]["Nowhere"] = "GEN"
    with pytest.raises(CheckFailed, match=r"Unused names.*'brenton', 'Nowhere'"):
        validate.validate()


def test_every_note_is_read(prepared):
    read = [
        operation
        for unit in prepared.values()
        for operation in unit.transformations
        if operation["operation"] == "read citations"
    ]
    assert {entry["dialect"] for entry in read} == {"brenton", "george"}
    assert sum(len(entry["citations"]) for entry in read) == 377
    assert citations.unused(read) == ([], [])
