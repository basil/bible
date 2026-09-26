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


# Rendered PDF


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
