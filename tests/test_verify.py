"""The checks on PTXprint's processed text and on the rendered PDF."""

from __future__ import annotations

import configparser
from collections.abc import Callable, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

import pytest

import bible.policy
from bible import export, pipeline, project, typeface, usj, verify
from bible.checks import CheckFailed
from bible.files import read_json

SOURCE_USFM = (
    "\\id GEN\n\\c 1\n\\p\n"
    "\\v 1 In the beginning\\f + \\fr 1:1 \\ft Or, first\\f* \\add God\\add* made.\n"
)


@pytest.fixture
def processed(tmp_path: Path) -> Callable[[str], None]:
    """A minimal generated project, and a function to write PTXprint's output."""
    root = tmp_path / project.PROJECT_DIR
    local = root / project.PROCESSED_DIR
    local.mkdir(parents=True)
    project.project_usfm(root, "GEN").write_text(SOURCE_USFM, encoding="utf-8")
    (local / "Bible_ptxp.tex").write_text(
        "%\\OmitCallerInNote{f}\n\\AutoCallers{f}{1,2,3}\n",
        encoding="utf-8",
    )

    def write(output: str) -> None:
        project.processed_usfm(root, "GEN").write_text(output, encoding="utf-8")
        verify.check_processed(root, tmp_path, ["GEN"])

    return write


def test_processed_output_unchanged(
    processed: Callable[[str], None], tmp_path: Path
) -> None:
    processed(SOURCE_USFM.replace("\n\\p\n", "\n\\p "))
    (record,) = read_json(tmp_path / "processed-integrity.json")
    assert record["id"] == "GEN"
    assert record["chapters"] == {"1": ["1"]}
    assert record["preserved_markers"] == {"f": 1, "f*": 1, "add": 1, "add*": 1}


@pytest.mark.parametrize(
    "before,after,refusal",
    [
        ("\\f + \\fr 1:1 \\ft Or, first\\f*", "", "printable content"),
        ("\\add God\\add*", "God", "notes, styles or tables"),
        ("\\v 1 ", "\\v 2 ", "chapter/verse labels"),
    ],
)
def test_processed_output_that_changes_the_text_is_refused(
    processed: Callable[[str], None], before: str, after: str, refusal: str
) -> None:
    with pytest.raises(CheckFailed, match=f"PTXprint changed {refusal}: GEN"):
        processed(SOURCE_USFM.replace(before, after))


def test_printed_origins_lose_their_chapter(declared: bible.policy.Policy) -> None:
    # What verify compares PTXprint's copy against is the exported text.
    doc = usj.parse(
        "\\id GEN\n\\c 9\n\\p\n"
        "\\v 12 And God\\f - \\fr 9:12 \\ft See \\xt Hebrews 12:29\\f* said"
        "\\x - \\xo 9:12a \\xt Psalm 1:2\\x* to Noe.\\f + \\fr 3:0 \\ft A title\\f*\n"
    )
    # An edition of no books: exporting reads only which units are scripture.
    none: MappingProxyType[str, Any] = MappingProxyType({})
    unit = pipeline.Edition(
        policy=declared,
        read=cast(Any, None),
        documents=none,
        scripture=frozenset({"GEN"}),
        authored=frozenset(),
        names=none,
        books=cast(Any, None),
        inventory=none,
        notes=none,
        summary=none,
        met=none,
        byzantine=cast(Any, None),
        numbering_page=cast(Any, None),
        variants_page=cast(Any, None),
        variants=(),
        glossary=cast(Any, None),
        ccel=cast(Any, None),
    )
    assert usj.serialize(export.document("GEN", doc, unit)).split("\\v 12 ")[1] == (
        "And God\\f - \\fr 12 \\ft See \\xt Hebrews 12:29\\f* said"
        "\\x - \\xo 12a \\xt Psalm 1:2\\x* to Noe.\\f + \\ft A title\\f*\n"
    )


# Rendered PDF
@pytest.mark.parametrize(
    "page,main,expected",
    [
        (1, 101, "i"),
        (7, 101, "vii"),
        (49, 101, "xlix"),
        (100, 101, "c"),
        (101, 101, "1"),
        (103, 101, "3"),
    ],
)
def test_preliminary_and_scripture_folios(page: int, main: int, expected: str) -> None:
    assert verify.folio(page, main) == expected


@pytest.mark.parametrize(
    "page,recto,accepted",
    [
        ("1480appendix1481readings", True, True),
        ("appendix1480readings1481", False, True),
        # Numbers in the outer margin.
        ("1480appendix1481readings", False, False),
        ("appendix1480readings1481", True, False),
        ("1480appendix1482readings", True, False),
        ("appendix1480readings1482", False, False),
        # A number with another figure beside it.
        ("11480appendix1481readings", True, False),
        ("appendix14801readings1481", False, False),
    ],
)
def test_contents_page_numbers_in_the_inner_margin(
    page: str, recto: bool, accepted: bool
) -> None:
    entries = [("appendix", "1480"), ("readings", "1481")]
    assert verify.numbered(page, entries, recto) == accepted


# Two contents pages, as pdftotext reads them, a recto and its verso, ending
# and beginning with "Introduction", which "Historical Introduction" contains.
CONTENTS = [
    ("introduction", "historicalintroduction", "1"),
    ("XXB", "preface", "5"),
    ("XXE", "introduction", "9"),
]


def test_a_title_within_another_on_the_page_before_is_not_taken_for_it() -> None:
    verify.check_contents(
        ["1historicalintroduction5preface", "introduction9"], CONTENTS, 5
    )
    verify.check_contents(["1historicalintroduction5preface9introduction"], CONTENTS, 5)
    with pytest.raises(CheckFailed, match="missing in PDF: XXE"):
        verify.check_contents(["1historicalintroduction5preface", "9"], CONTENTS, 5)
    # The verso gives its number in the outer margin.
    with pytest.raises(CheckFailed, match="last page of the contents"):
        verify.check_contents(
            ["1historicalintroduction5preface", "9introduction"], CONTENTS, 5
        )


# The publication page as the layout's settings give it, and as pdftotext
# reads it: the license notice broken across lines.
SETTINGS = configparser.ConfigParser(interpolation=None)
SETTINGS.read_dict(
    {
        "project": {
            "copyright": "Copyright © 2026 Basil Crow",
            "license": "Creative Commons Attribution 4.0 International (CC BY 4.0). "
            "https://creativecommons.org/licenses/by/4.0/",
        }
    }
)
PUBLICATION = (
    "Copyright © 2026 Basil Crow\n"
    "Creative Commons Attribution 4.0 International (CC BY 4.0).\n"
    "https://creativecommons.org/licenses/by/4.0/"
)
# The pages before the imprint: the half-title, its blank verso, and the title.
OPENING = "Half title\f\fTitle\f"


def test_layout_credit_in_the_introduction_passes() -> None:
    verify.check_publication(
        f"{OPENING}{PUBLICATION}\f"
        "The design is based on the Berean Standard Bible layout.",
        SETTINGS,
    )


def test_inherited_publication_identity_is_refused() -> None:
    with pytest.raises(CheckFailed, match="Inherited BSB publication text remains"):
        verify.check_publication(
            f"{OPENING}{PUBLICATION}\nBerean Standard\nBible\fIntroduction", SETTINGS
        )


def test_missing_edition_license_on_the_publication_page_is_refused() -> None:
    with pytest.raises(CheckFailed, match="omitted the edition license notice"):
        verify.check_publication(f"{OPENING}Publication\f{PUBLICATION}", SETTINGS)


@pytest.mark.parametrize(
    "words",
    [
        "See 1 Cor. 10:26, 28",
        "see chapter 6:13, 15; verse 3",
        "Ps. 117:22–23 (LXX ≠ Heb.)",
        "Heb. 5:6; 7:17, 21 (Heb. + LXX)",
        "Heb. 300. Alex. 500",
        "Alex. 187 years. Heb. Grammar, page 92",
        # The numbers that the appendix supplies a passage under.
        "17. 12And David son of an Ephrathite",
        "the days of Saul. 13And the three elder sons",
        "1870. it | 1844. It",
        # A verse's number, after the sentence before it.
        "and the evening star. 32 Or wilt thou",
        # License versions and dates followed by a printed note caller.
        "Creative Commons Attribution 4.0 International",
        "dated February 2021.4 The TCENT version",
        "The Greek New Testament According to Family 35. 3rd ed.",
    ],
)
def test_the_editions_citations_pass(words: str) -> None:
    verify.check_citations(words)


@pytest.mark.parametrize(
    "words",
    [
        "See Rom. 4. 7,8",
        "as Mat. 18.28",
        "afforded by Gen. xlvii. 31, compared",
        "Hebrews xi. 21",
        "2Ki. 19. 18",
        "1. Cor. 8.11",
        "See 1 Cor 2. 16. Gr.",
        "Exodus 28. 5",
        "Ps. 150. 6",
    ],
)
def test_a_citation_as_a_source_writes_it_is_refused(words: str) -> None:
    with pytest.raises(CheckFailed, match="not written as the edition cites"):
        verify.check_citations(f"12:3 lamb: {words} and so on")


@pytest.mark.parametrize("ids,chapters", [(["GEN"], None), (["MAL"], "3")])
def test_added_words_witness_may_be_left_out_of_the_sample_only(
    tmp_path: Path, ids: list[str], chapters: str | None
) -> None:
    if chapters:
        project.project_usfm(tmp_path, "MAL").write_text(
            f"\\id MAL\n\\c {chapters}\n\\p\n\\v 1 A.\n", encoding="utf-8"
        )
    verify.check_added_words_roman(tmp_path / "unused.pdf", "", tmp_path, ids, True)
    with pytest.raises(CheckFailed, match="Malachias 4:2 is not in the build"):
        verify.check_added_words_roman(
            tmp_path / "unused.pdf", "", tmp_path, ids, False
        )


def pdf_words(
    monkeypatch: pytest.MonkeyPatch,
    *pages: Sequence[tuple[str, float, float, float]],
    **size: float,
) -> None:
    """Have pdftotext report pages of words, each (text, left, top, right)."""
    attributes = "".join(f' {name}="{value}"' for name, value in size.items())
    body = "".join(
        f"<page{attributes}><block>"
        + "".join(
            f'<word xMin="{left}" yMin="{top}" xMax="{right}" yMax="{top + 10}">'
            f"{text}</word>"
            for text, left, top, right in page
        )
        + "</block></page>"
        for page in pages
    )
    monkeypatch.setattr(
        verify,
        "capture",
        lambda *args: (
            f'<html xmlns="{verify.XHTML[1:-1]}"><body><doc>{body}</doc></body></html>'
        ),
    )


def test_stream_text_parts_words_and_leaves_out_the_margins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The running head and the folio stand above and below the text block.
    words = [("Esaias", 13), ("as", 40), ("in", 40), ("Rom.", 40), ("4.", 52)]
    page = [(text, 34, top, 54) for text, top in [*words, ("7", 52), ("53", 556)]]
    pdf_words(monkeypatch, page, page, height=595)
    text = verify.stream_text("bible.pdf", 34, 51)
    assert text == "as in Rom. 4. 7\fas in Rom. 4. 7"
    with pytest.raises(CheckFailed, match="not written as the edition cites"):
        verify.check_citations(text)


def test_stream_text_keeps_inner_notes_out_of_body_sentences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The inner margin is on the left of an odd page and the right of an even.
    odd = [("the soul", 102, 40, 150), ("Vat. omits", 30, 40, 90)]
    even = [("the soul", 34, 40, 82), ("Vat. omits", 410, 40, 460)]
    pdf_words(
        monkeypatch,
        [*odd, ("of Jonathan", 102, 40, 160)],
        [*even, ("of Jonathan", 34, 40, 100)],
        width=499,
        height=709,
    )
    assert verify.stream_text("bible.pdf", 34, 51, 102) == (
        "the soul of Jonathan\n\nVat. omits\fthe soul of Jonathan\n\nVat. omits"
    )


def test_stream_text_keeps_a_heading_apart_from_the_following_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_words(
        monkeypatch,
        [("2 Chronicles", 100, 40, 200), ("27. 8", 100, 72, 150)],
        height=709,
    )
    xml = verify.capture()
    monkeypatch.setattr(
        verify,
        "capture",
        lambda *args: xml.replace("</word><word", "</word></block><block><word"),
    )
    text = verify.stream_text("bible.pdf", 34, 51)
    assert text == "2 Chronicles\n\n27. 8"
    verify.check_citations(text)


def check_notes(tmp_path: Path, *notes: tuple[str, int, float, float]) -> list[str]:
    """Check notes given as (reference, page, top, depth), in points, against
    a text block from 51 to 561 points above the foot of the page."""
    (tmp_path / "Bible_ptxp.marginnotes").write_text(
        "".join(
            f"\\@marginnote{{{ref}}}{{f}}{{inner}}{{bottom}}{{8.5pt}}{{68.3pt}}"
            f"{{0.00000pt}}{{{depth:.5f}pt}}{{0.00000pt}}{{0.00000pt}}"
            f"{{{page}}}{{6712846}}{{{top * 65536}}}\n"
            for ref, page, top, depth in notes
        ),
        encoding="utf-8",
    )
    return verify.margin_overflow(tmp_path, 561, 51)


def test_margin_notes_that_fit_in_order_pass(tmp_path: Path) -> None:
    assert not check_notes(
        tmp_path,
        ("GEN2.19", 46, 561, 20),
        ("GEN2.20", 46, 541, 10),
        ("GEN2.23", 46, 71, 20),
        # Each page's margin is its own.
        ("GEN3.1", 47, 561, 20),
    )


@pytest.mark.parametrize(
    "notes,found",
    [
        # Off the foot of the text block, and off its head.
        ([("GEN2.19", 46, 561, 20), ("GEN2.20", 46, 70, 20)], "GEN2.20"),
        ([("GEN2.20", 46, 562, 20)], "GEN2.20"),
        # Pushed off the foot of the page itself.
        ([("GEN2.19", 46, 561, 20), ("GEN2.20", 46, -10, 20)], "GEN2.20"),
        # Over the note before it, and over the note placed above it.
        ([("GEN2.19", 46, 561, 20), ("GEN2.20", 46, 551, 10)], "GEN2.20"),
        ([("GEN2.19", 46, 551, 20), ("GEN2.20", 46, 560, 20)], "GEN2.19"),
    ],
)
def test_a_margin_note_that_does_not_fit_is_found(
    tmp_path: Path, notes: list[tuple[str, int, float, float]], found: str
) -> None:
    assert check_notes(tmp_path, *notes) == [f"page 46 {found}"]


def test_a_margin_note_moved_to_a_later_page_is_found(tmp_path: Path) -> None:
    """PTXprint sets a note an overfull margin has no room for at the head of
    a later page, and records the move; the note's own record keeps its
    verse's page and place."""
    check_notes(tmp_path, ("GEN2.19", 46, 561, 20), ("GEN2.20", 46, 541, 10))
    records = tmp_path / "Bible_ptxp.marginnotes"
    records.write_text(
        records.read_text(encoding="utf-8")
        + "\\@marginnotepush{GEN2.20}{f}{47}{0}{right}\n"
        # A move of another kind of note at the verse is not this note's.
        + "\\@marginnotepush{GEN2.19}{x}{47}{0}{right}\n",
        encoding="utf-8",
    )
    assert verify.margin_overflow(tmp_path, 561, 51) == ["page 46 GEN2.20"]


def test_a_later_note_placed_above_an_earlier_one_fits(tmp_path: Path) -> None:
    """PTXprint may set a note of a chapter's opening paragraph above an
    earlier verse's; the notes are checked in the order they stand."""
    assert not check_notes(tmp_path, ("GEN2.19", 46, 541, 20), ("GEN2.20", 46, 561, 20))


@pytest.mark.parametrize(
    "record",
    [
        "\\@marginnote{GEN2.19}{f}{inner}{46}{-36765696}\n",
        "\\@marginnotepush{GEN2.19}{f}{47}\n",
    ],
)
def test_a_margin_note_record_in_another_form_is_refused(
    tmp_path: Path, record: str
) -> None:
    (tmp_path / "Bible_ptxp.marginnotes").write_text(record, encoding="utf-8")
    with pytest.raises(CheckFailed, match="Could not read every margin note"):
        verify.margin_overflow(tmp_path, 561, 51)


def test_a_colophon_follows_the_complete_final_verse() -> None:
    source = (
        "\\id HEB\n\\c 13\n\\p\\v 25 Grace be with you all. Amen.\n"
        "\\esb \\cat colophon\\cat*\n\\p Written to the Hebrews from Italy by Timothy.\n\\esbe\n"
    )
    verify.check_colophon_order(
        source,
        "Grace be with you all. Amen. Written to the Hebrews from Italy by Timothy.",
    )
    with pytest.raises(CheckFailed, match="before scripture ends"):
        verify.check_colophon_order(
            source,
            "Grace be with you all. Written to the Hebrews from Italy by Timothy. Amen.",
        )


def test_terminal_sidebars_print_in_their_order() -> None:
    source = (
        "\\id REV\n\\c 22\n\\p\\v 21 The grace be with you all. Amen.\n"
        "\\esb \\cat colophon\\cat*\n\\p Written from Patmos.\n\\esbe\n"
        "\\esb \\cat closing\\cat*\n\\p The end of the Holy Bible\n\\esbe\n"
    )
    verify.check_colophon_order(
        source,
        "The grace be with you all. Amen. Written from Patmos. The end of the Holy Bible",
    )
    with pytest.raises(CheckFailed, match="before scripture ends"):
        verify.check_colophon_order(
            source,
            "The grace be with you all. Amen. The end of the Holy Bible Written from Patmos.",
        )


@pytest.mark.parametrize(
    "fault",
    ["", "missing", "wrong_chapter", "substitute", "unembedded", "unselected_newpx"],
)
def test_pdf_fonts_require_embedded_chapter_face(fault: str) -> None:
    names = [
        "OLEBFont-Italic",
        typeface.postscript_family(typeface.greek_face()),
        "EzraSIL",
        typeface.postscript_name(typeface.chapter_face()),
    ]
    if fault == "unselected_newpx":
        if names[-1] != "OLEBFont-Regular":
            pytest.skip("newpx is selected with Valkyrie")
        names.append("TeXGyrePagellaX-Regular")
    elif fault == "missing":
        names.pop()
    elif fault == "wrong_chapter":
        names[-1] = "TeXGyrePagellaX-Bold"
    elif fault == "substitute":
        names.append("UnwantedFont-Regular")
    fonts = "name type encoding emb sub uni object ID\n---\n" + "\n".join(
        f"ABCDEF+{name} CID Type 0C Identity-H "
        f"{'no' if fault == 'unembedded' and name == names[-1] else 'yes'} yes yes 1 0"
        for name in names
    )
    if fault:
        refusal = {
            "missing": "Expected text/quotation fonts missing",
            "wrong_chapter": "Expected text/quotation fonts missing",
            "substitute": "Unexpected font family",
            "unselected_newpx": "Unexpected font family",
            "unembedded": "Unembedded PDF font",
        }[fault]
        with pytest.raises(CheckFailed, match=refusal):
            verify.check_fonts(fonts, "OLEBFont")
    else:
        verify.check_fonts(fonts, "OLEBFont")
