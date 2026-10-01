"""The checks on PTXprint's processed text and on the rendered PDF."""

import pytest

from bible import project, verify
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
    assert record["preserved_markers"] == {"f": 1, "f*": 1, "add": 1, "add*": 1}


def test_processed_output_deleted_footnote(processed):
    with pytest.raises(CheckFailed, match="PTXprint changed printable content: GEN"):
        processed(SOURCE_USFM.replace("\\f + \\fr 1:1 \\ft Or, first\\f*", ""))


def test_processed_output_dropped_style(processed):
    with pytest.raises(
        CheckFailed, match="PTXprint changed notes, styles or tables: GEN"
    ):
        processed(SOURCE_USFM.replace("\\add God\\add*", "God"))


def test_processed_output_relabelled_verse(processed):
    with pytest.raises(CheckFailed, match="PTXprint changed chapter/verse labels: GEN"):
        processed(SOURCE_USFM.replace("\\v 1 ", "\\v 2 "))


def test_printed_origins_lose_only_their_chapter():
    prepared = (
        "\\f - \\fr 9:12 \\ft See \\xt Hebrews 12:29\\f*"
        "\\x - \\xo 1:2a \\xt Psalm 1:2\\x*"
    )
    assert project.ORIGIN_CHAPTER.sub(r"\1", prepared) == (
        "\\f - \\fr 12 \\ft See \\xt Hebrews 12:29\\f*"
        "\\x - \\xo 2a \\xt Psalm 1:2\\x*"
    )


def test_an_origin_that_names_no_verse_is_not_printed():
    prepared = "its use.\\f + \\fr 1:0 \\ft In accounting for the quotation\\f*"
    assert project.EMPTY_ORIGIN.sub("", prepared) == (
        "its use.\\f + \\ft In accounting for the quotation\\f*"
    )
    assert not project.EMPTY_ORIGIN.search("\\f - \\fr 1:10 \\ft or\\f*")


def test_only_front_matter_loses_an_origin_that_names_no_verse():
    prepared = "\\f + \\fr 3:0 \\ft A title\\f*"
    log = []

    def record(operation, **details):
        log.append((operation, details))

    assert project.printed_origins({"id": "XXB"}, prepared, record) == (
        "\\f + \\ft A title\\f*"
    )
    assert project.printed_origins(
        {"id": "PSA", "section": "old-testament"}, prepared, record
    ) == ("\\f + \\fr 0 \\ft A title\\f*")
    assert [operation for operation, _ in log] == [
        "omit note origins that name no verse",
        "print note origins without their chapter",
    ]


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
        "A talent is 187 pounds 10 shillings",
        "1870. it | 1844. It",
        "about the year 280 BC. The Jews",
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
        "See 2 Cor. 9. 7. Compare Heb.",
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


def test_added_words_witness_may_be_left_out_of_the_sample(tmp_path):
    verify.check_added_words_roman(None, "", tmp_path, ["GEN"], True)


def test_added_words_witness_must_be_in_the_full_bible(tmp_path):
    with pytest.raises(CheckFailed, match="Malachias 4:2 is not in the build"):
        verify.check_added_words_roman(None, "", tmp_path, ["GEN"], False)


def test_added_words_witness_chapter_must_be_in_the_full_bible(tmp_path):
    project.project_usfm(tmp_path, "MAL").write_text(
        "\\id MAL\n\\c 3\n\\p\n\\v 1 A.\n", encoding="utf-8"
    )
    with pytest.raises(CheckFailed, match="Malachias 4:2 is not in the build"):
        verify.check_added_words_roman(None, "", tmp_path, ["MAL"], False)


def test_stream_text_parts_words_and_leaves_out_the_margins(monkeypatch):
    def word(text, y):
        return f'<word xMin="34" yMin="{y}" xMax="54" yMax="{y + 10}">{text}</word>'

    words = [("Esaias", 13), ("as", 40), ("in", 40), ("Rom.", 40), ("4.", 52)]
    page = "".join(word(*w) for w in [*words, ("7", 52), ("53", 556)])
    monkeypatch.setattr(
        verify,
        "capture",
        lambda *args: (
            f'<html xmlns="{verify.XHTML[1:-1]}"><body><doc>'
            f'<page height="595">{page}</page><page height="595">{page}</page>'
            "</doc></body></html>"
        ),
    )
    text = verify.stream_text("bible.pdf", 34, 51)
    assert text == "as in Rom. 4. 7\fas in Rom. 4. 7"
    with pytest.raises(CheckFailed, match="not written as the edition cites"):
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
