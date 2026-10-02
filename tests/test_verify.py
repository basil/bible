"""The checks on PTXprint's processed text and on the rendered PDF."""

from types import SimpleNamespace

import pytest

from bible import pipeline, project, usj, verify
from bible.checks import CheckFailed
from bible.files import read_json

SOURCE_USFM = (
    "\\id GEN\n\\c 1\n\\p\n"
    "\\v 1 In the beginning\\f + \\fr 1:1 \\ft Or, first\\f* \\add God\\add* made.\n"
)


@pytest.fixture
def processed(tmp_path):
    """A minimal generated project, and a function to write PTXprint's output."""
    root = tmp_path / project.PROJECT_DIR
    local = root / project.PROCESSED_DIR
    local.mkdir(parents=True)
    project.project_usfm(root, "GEN").write_text(SOURCE_USFM, encoding="utf-8")
    (local / "Bible_ptxp.tex").write_text("%\\OmitCallerInNote{f}\n", encoding="utf-8")

    def write(output):
        project.processed_usfm(root, "GEN").write_text(output, encoding="utf-8")
        verify.check_processed(root, tmp_path, ["GEN"])

    return write


def test_processed_output_unchanged(processed, tmp_path):
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
    processed, before, after, refusal
):
    with pytest.raises(CheckFailed, match=f"PTXprint changed {refusal}: GEN"):
        processed(SOURCE_USFM.replace(before, after))


def test_printed_origins_lose_their_chapter_and_front_matter_its_empty_ones():
    # What verify compares PTXprint's copy against is the exported text.
    doc = usj.parse(
        "\\id GEN\n\\c 9\n\\p\n"
        "\\v 12 And God\\f - \\fr 9:12 \\ft See \\xt Hebrews 12:29\\f* said"
        "\\x - \\xo 9:12a \\xt Psalm 1:2\\x* to Noe.\\f + \\fr 3:0 \\ft A title\\f*\n"
    )

    def exported(code, scripture):
        unit = SimpleNamespace(scripture=frozenset(scripture), authored=frozenset())
        return pipeline.exported(code, doc, unit).split("\\v 12 ")[1]

    assert exported("GEN", {"GEN"}) == (
        "And God\\f - \\fr 12 \\ft See \\xt Hebrews 12:29\\f* said"
        "\\x - \\xo 12a \\xt Psalm 1:2\\x* to Noe.\\f + \\fr 0 \\ft A title\\f*\n"
    )
    # Front matter has no verses: an origin that names none isn't printed.
    assert exported("XXB", set()).endswith("to Noe.\\f + \\ft A title\\f*\n")
    assert "\\fr 12 \\ft See" in exported("XXB", set())


# Rendered PDF


@pytest.mark.parametrize(
    "words",
    [
        "See Romans 4:7, 8",
        "see chapter 6:13, 15; verse 3",
        "Psalm 117:22–23 (LXX against Heb.)",
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
def test_the_editions_citations_pass(words):
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
def test_a_citation_as_a_source_writes_it_is_refused(words):
    with pytest.raises(CheckFailed, match="not written as the edition cites"):
        verify.check_citations(f"12:3 lamb: {words} and so on")


@pytest.mark.parametrize("ids,chapters", [(["GEN"], None), (["MAL"], "3")])
def test_added_words_witness_may_be_left_out_of_the_sample_only(
    tmp_path, ids, chapters
):
    if chapters:
        project.project_usfm(tmp_path, "MAL").write_text(
            f"\\id MAL\n\\c {chapters}\n\\p\n\\v 1 A.\n", encoding="utf-8"
        )
    verify.check_added_words_roman(None, "", tmp_path, ids, True)
    with pytest.raises(CheckFailed, match="Malachias 4:2 is not in the build"):
        verify.check_added_words_roman(None, "", tmp_path, ids, False)


def pdf_words(monkeypatch, *pages, **size):
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


def test_stream_text_parts_words_and_leaves_out_the_margins(monkeypatch):
    # The running head and the folio stand above and below the text block.
    words = [("Esaias", 13), ("as", 40), ("in", 40), ("Rom.", 40), ("4.", 52)]
    page = [(text, 34, top, 54) for text, top in [*words, ("7", 52), ("53", 556)]]
    pdf_words(monkeypatch, page, page, height=595)
    text = verify.stream_text("bible.pdf", 34, 51)
    assert text == "as in Rom. 4. 7\fas in Rom. 4. 7"
    with pytest.raises(CheckFailed, match="not written as the edition cites"):
        verify.check_citations(text)


def test_stream_text_keeps_inner_notes_out_of_body_sentences(monkeypatch):
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


def test_stream_text_keeps_a_heading_apart_from_the_following_numbers(monkeypatch):
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


def check_notes(tmp_path, *notes):
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


def test_margin_notes_that_fit_in_order_pass(tmp_path):
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
def test_a_margin_note_that_does_not_fit_is_refused(tmp_path, notes):
    with pytest.raises(CheckFailed, match="does not fit: page 46 GEN2.20"):
        check_notes(tmp_path, *notes)


def test_a_margin_note_record_in_another_form_is_refused(tmp_path):
    (tmp_path / "Bible_ptxp.marginnotes").write_text(
        "\\@marginnote{GEN2.19}{f}{inner}{46}{-36765696}\n", encoding="utf-8"
    )
    with pytest.raises(CheckFailed, match="Could not read every margin note"):
        verify.check_margin_notes(tmp_path, 561, 51)
