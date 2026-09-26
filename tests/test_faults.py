"""Fault injection: each guard must refuse a deliberately damaged input."""

import pytest

import pipeline
from pipeline import CheckFailed, scripture_unit as unit

BAD_SHA256 = "0" * 64


def with_source(archives, source, code, edit):
    """A copy of the archives with one source file's text edited."""
    member, raw, text = archives[source][code]
    return {
        **archives,
        source: {**archives[source], code: (member, raw, edit(text))},
    }


# Pinned inputs


def test_font_archive_checksum(patched):
    patched("DEPS")["erewhon"]["sha256"] = BAD_SHA256
    with pytest.raises(CheckFailed, match="Checksum mismatch: sources/erewhon.zip"):
        pipeline.validate()


def test_source_archive_checksum(patched):
    patched("SOURCES")["kjv"]["sha256"] = BAD_SHA256
    with pytest.raises(CheckFailed, match="Checksum mismatch: sources/engkjvcpb"):
        pipeline.validate()


def test_source_member_checksum(patched):
    patched("SOURCES")["kjv"]["files"]["MAT"]["sha256"] = BAD_SHA256
    with pytest.raises(CheckFailed, match="Changed source: kjv/MAT"):
        pipeline.validate()


def test_source_inventory(patched):
    patched("SOURCES")["brenton"]["files"]["PSA"]["chapters"].pop("151")
    with pytest.raises(CheckFailed, match="Changed inventory: brenton/PSA"):
        pipeline.validate()


def test_archive_member_list(patched):
    files = patched("SOURCES")["kjv"]["files"]
    files["XXX"] = files["MAT"]
    with pytest.raises(CheckFailed, match="Archive inventory changed"):
        pipeline.validate()


def test_marginal_notes_checksum(patched):
    patched("SOURCES")["marginal_notes"]["sha256"] = BAD_SHA256
    with pytest.raises(CheckFailed, match="Checksum mismatch: sources/exhaustive"):
        pipeline.marginal_notes()


# Marginal notes


def test_marginal_notes_parse():
    notes = pipeline.marginal_notes()
    assert sum(len(n) for n in notes.values()) == pipeline.EXPECTED_NT_MARGINAL_NOTES


def test_unused_correction(patched):
    patched("MARGINAL_NOTES")["corrections"]["MAT 1:1 nothing"] = {
        "from": "a",
        "to": "b",
    }
    with pytest.raises(
        CheckFailed, match=r"Unused marginal note corrections: \['MAT 1:1 nothing'\]"
    ):
        pipeline.marginal_notes()


def test_correction_that_does_not_apply(patched):
    patched("MARGINAL_NOTES")["corrections"]["MAT 23:18 guilty"][
        "from"
    ] = "no such text"
    with pytest.raises(
        CheckFailed, match="correction does not apply: MAT 23:18 guilty"
    ):
        pipeline.marginal_notes()


def test_transcribers_remark_left_in_note(patched):
    # This correction removes "[symbol in wrong place in 1611]".
    del patched("MARGINAL_NOTES")["corrections"]["MAT 5:15 a bushel"]
    with pytest.raises(
        CheckFailed, match="Transcriber's remark left in marginal note: MAT 5:15"
    ):
        pipeline.marginal_notes()


def test_unused_anchor(patched):
    patched("MARGINAL_NOTES")["anchors"]["MAT 1:1 nothing"] = {"anchor": "nothing"}
    with pytest.raises(CheckFailed, match="Unused marginal note anchors"):
        pipeline.marginal_notes()


def test_missing_anchor_verse(archives, patched):
    patched("MARGINAL_NOTES")["anchors"]["MAT 12:14 held a counsel"]["verse"] = "12:99"
    with pytest.raises(CheckFailed, match="verse missing: MAT 12:14 held a counsel"):
        pipeline.scripture_text(unit("MAT"), archives)


def test_wrong_anchor(archives, patched):
    # George's lemma reads "counsel" where the Cambridge text has "council".
    del patched("MARGINAL_NOTES")["anchors"]["MAT 12:14 held a counsel"]
    with pytest.raises(
        CheckFailed, match=r"not found exactly once: MAT 12:14 held a counsel \(0\)"
    ):
        pipeline.scripture_text(unit("MAT"), archives)


def test_ambiguous_anchor(archives, patched):
    # "of" occurs more than once in Matthew 6:1; the override picks the second.
    del patched("MARGINAL_NOTES")["anchors"]["MAT 6:1 of"]
    with pytest.raises(
        CheckFailed, match=r"not found exactly once: MAT 6:1 of \([2-9]\)"
    ):
        pipeline.scripture_text(unit("MAT"), archives)


def test_anchor_inside_added_words(archives, patched):
    # "it" is the second of Mark 3:21's added words "of it".
    patched("MARGINAL_NOTES")["anchors"]["MRK 3:21 friends"] = {"anchor": "it"}
    with pytest.raises(
        CheckFailed, match="caller inside a character span: MRK 3:21 friends"
    ):
        pipeline.scripture_text(unit("MRK"), archives)


# Scripture preparation


def test_scripture_unit_outside_both_testaments(patched):
    patched("EDITION")["scripture"][0]["section"] = "old_testment"
    with pytest.raises(CheckFailed, match=r"outside both testaments: \['GEN'\]"):
        pipeline.ordered_entries()


def test_divided_source_must_be_printed_whole(patched):
    patched("EDITION")
    unit("EZR")["chapters"] = [1, 9]
    with pytest.raises(CheckFailed, match="not printed whole: brenton/EZR"):
        pipeline.validate()


def test_manifest_chapters_must_exist(archives):
    entry = {**unit("NEH"), "chapters": [11, 24]}
    with pytest.raises(CheckFailed, match="chapters outside the source: NEH"):
        pipeline.scripture_text(entry, archives)


def test_malachias_chapter_boundary(archives):
    damaged = with_source(
        archives,
        "brenton",
        "MAL",
        lambda t: t.replace("\\v 19 For, behold", "\\v 19 For, lo"),
    )
    with pytest.raises(CheckFailed, match="Malachias chapter boundary changed"):
        pipeline.scripture_text(unit("MAL"), damaged)


def test_song_of_the_three_children_boundary(archives):
    damaged = with_source(
        archives,
        "brenton",
        "DAG",
        lambda t: t.replace("Then Azarias stood up", "Azarias stood up"),
    )
    with pytest.raises(
        CheckFailed, match="Song of the Three Children boundary changed"
    ):
        pipeline.scripture_text(unit("DAG"), damaged)


def test_relabelled_note_reference(archives):
    # Nehemias relabels chapter markers only; a note would keep its source chapter.
    damaged = with_source(
        archives,
        "brenton",
        "EZR",
        lambda t: t.replace(
            "son of Chelcia.", "son of Chelcia.\\f + \\fr 11:1 \\ft x\\f*", 1
        ),
    )
    with pytest.raises(
        CheckFailed, match="Note reference disagrees with its verse: NEH"
    ):
        pipeline.scripture_text(unit("NEH"), damaged)


def test_cambridge_text_must_not_already_have_notes(archives):
    damaged = with_source(
        archives,
        "kjv",
        "MAT",
        lambda t: t.replace("\\v 2 ", "\\v 2 \\f + \\ft x\\f* ", 1),
    )
    with pytest.raises(CheckFailed, match="already has footnotes: MAT"):
        pipeline.scripture_text(unit("MAT"), damaged)


# PTXprint's processed output


SOURCE_USFM = (
    "\\id GEN\n\\c 1\n\\p\n"
    "\\v 1 In the beginning\\f + \\fr 1:1 \\ft Or, first\\f* \\add God\\add* made.\n"
)


@pytest.fixture
def processed(tmp_path):
    """A minimal generated project, and a function to write PTXprint's output."""
    project = tmp_path / pipeline.PROJECT_DIR
    local = project / pipeline.PROCESSED_DIR
    local.mkdir(parents=True)
    pipeline.project_usfm(project, "GEN").write_text(SOURCE_USFM, encoding="utf-8")
    (local / "Bible_ptxp.tex").write_text(
        "%\\OmitCallerInNote{f}\n%\\OmitCallerInNote{x}\n", encoding="utf-8"
    )

    def write(output):
        pipeline.processed_usfm(project, "GEN").write_text(output, encoding="utf-8")
        pipeline.check_processed(project, tmp_path, ["GEN"])

    return write


def test_processed_output_unchanged(processed, tmp_path):
    processed(SOURCE_USFM.replace("\n\\p\n", "\n\\p "))
    (record,) = pipeline.read_json(tmp_path / "processed-integrity.json")
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
