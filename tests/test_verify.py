"""The checks on PTXprint's processed text and on the rendered PDF."""

from __future__ import annotations

import configparser
from collections.abc import Callable, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

import bible.policy
from bible import pipeline, project, usj, verify
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
        "%\\OmitCallerInNote{f}\n\\AutoCallers{f}{1,2,3}\n", encoding="utf-8"
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
        declared, none, frozenset({"GEN"}), frozenset(), none, none, none, none
    )
    assert pipeline.exported("GEN", doc, unit).split("\\v 12 ")[1] == (
        "And God\\f - \\fr 12 \\ft See \\xt Hebrews 12:29\\f* said"
        "\\x - \\xo 12a \\xt Psalm 1:2\\x* to Noe.\\f + \\fr 0 \\ft A title\\f*\n"
    )


# Rendered PDF


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


def test_layout_credit_in_the_introduction_passes() -> None:
    verify.check_publication(
        f"Title\f{PUBLICATION}\f"
        "The design is based on the Berean Standard Bible layout.",
        SETTINGS,
    )


def test_inherited_publication_identity_is_refused() -> None:
    with pytest.raises(CheckFailed, match="Inherited BSB publication text remains"):
        verify.check_publication(
            f"Title\f{PUBLICATION}\nBerean Standard\nBible\fIntroduction", SETTINGS
        )


def test_missing_edition_license_on_the_publication_page_is_refused() -> None:
    with pytest.raises(CheckFailed, match="omitted the edition license notice"):
        verify.check_publication(f"Title\fPublication\f{PUBLICATION}", SETTINGS)


@pytest.mark.parametrize(
    "words",
    [
        "See 1 Cor. 10:26, 28",
        "see chapter 6:13, 15; verse 3",
        "Ps. 117:22–23 (LXX ≠ Heb.)",
        "Heb. 5:6; 7:17, 21 (Heb. + LXX)",
        "Heb. 300. Alex. 500",
        "Alex. 187 years. Heb. Grammar, p. 92",
        # The numbers that the appendix supplies a passage under.
        "17. 12And David son of an Ephrathite",
        "the days of Saul. 13And the three elder sons",
        "1870. it | 1844. It",
        # A verse's number, after the sentence before it.
        "and the evening star. 32 Or wilt thou",
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


def check_notes(tmp_path: Path, *notes: tuple[str, int, float, float]) -> None:
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
    verify.check_margin_notes(tmp_path, 561, 51)


def test_margin_notes_that_fit_in_order_pass(tmp_path: Path) -> None:
    check_notes(
        tmp_path,
        ("GEN2.19", 46, 561, 20),
        ("GEN2.20", 46, 541, 10),
        ("GEN2.23", 46, 71, 20),
        # Each page's margin is its own.
        ("GEN3.1", 47, 561, 20),
    )


@pytest.mark.parametrize(
    "notes",
    [
        # Off the foot of the text block, and off its head.
        [("GEN2.19", 46, 561, 20), ("GEN2.20", 46, 70, 20)],
        [("GEN2.20", 46, 562, 20)],
        # Over the note before it, and above it.
        [("GEN2.19", 46, 561, 20), ("GEN2.20", 46, 551, 10)],
        [("GEN2.19", 46, 551, 20), ("GEN2.20", 46, 561, 10)],
    ],
)
def test_a_margin_note_that_does_not_fit_is_refused(
    tmp_path: Path, notes: list[tuple[str, int, float, float]]
) -> None:
    with pytest.raises(CheckFailed, match="does not fit: page 46 GEN2.20"):
        check_notes(tmp_path, *notes)


def test_a_margin_note_record_in_another_form_is_refused(tmp_path: Path) -> None:
    (tmp_path / "Bible_ptxp.marginnotes").write_text(
        "\\@marginnote{GEN2.19}{f}{inner}{46}{-36765696}\n", encoding="utf-8"
    )
    with pytest.raises(CheckFailed, match="Could not read every margin note"):
        verify.check_margin_notes(tmp_path, 561, 51)
