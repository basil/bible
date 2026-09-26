"""Fault injection: each guard must refuse a deliberately damaged input."""

import copy
import json

import pytest

import pipeline
from pipeline import CheckFailed

BAD_SHA256 = "0" * 64


def unit(code):
    return next(u for u in pipeline.EDITION["scripture"] if u["id"] == code)


def with_source(archives, source, code, edit):
    """A copy of the archives with one source file's text edited."""
    member, raw, text = archives[source][code]
    return {
        **archives,
        source: {**archives[source], code: (member, raw, edit(text))},
    }


# Pinned inputs


def test_font_archive_checksum(monkeypatch):
    deps = copy.deepcopy(pipeline.DEPS)
    deps["erewhon"]["sha256"] = BAD_SHA256
    monkeypatch.setattr(pipeline, "DEPS", deps)
    with pytest.raises(
        CheckFailed, match="Archive checksum mismatch: sources/erewhon.zip"
    ):
        pipeline.validate()


def test_source_archive_checksum(sources):
    sources["kjv"]["sha256"] = BAD_SHA256
    with pytest.raises(
        CheckFailed, match="Archive checksum mismatch: sources/engkjvcpb"
    ):
        pipeline.validate()


def test_source_member_checksum(sources):
    sources["kjv"]["files"]["MAT"]["sha256"] = BAD_SHA256
    with pytest.raises(CheckFailed, match="Changed source: kjv/MAT"):
        pipeline.validate()


def test_source_inventory(sources):
    sources["brenton"]["files"]["PSA"]["chapters"].pop("151")
    with pytest.raises(CheckFailed, match="Changed inventory: brenton/PSA"):
        pipeline.validate()


def test_archive_member_list(sources):
    sources["kjv"]["files"]["XXX"] = sources["kjv"]["files"]["MAT"]
    with pytest.raises(CheckFailed, match="Archive inventory changed"):
        pipeline.validate()


def test_marginal_notes_checksum(sources):
    sources["marginal_notes"]["sha256"] = BAD_SHA256
    with pytest.raises(CheckFailed, match="Source checksum mismatch"):
        pipeline.marginal_notes()


# Marginal notes


def test_marginal_notes_parse():
    notes = pipeline.marginal_notes()
    assert sum(len(n) for n in notes.values()) == pipeline.EXPECTED_NT_MARGINAL_NOTES


def test_unused_correction(marginal_notes_config):
    marginal_notes_config["corrections"]["MAT 1:1 nothing"] = {"from": "a", "to": "b"}
    with pytest.raises(
        CheckFailed, match=r"Unused marginal note corrections: \['MAT 1:1 nothing'\]"
    ):
        pipeline.marginal_notes()


def test_correction_that_does_not_apply(marginal_notes_config):
    marginal_notes_config["corrections"]["MAT 23:18 guilty"]["from"] = "no such text"
    with pytest.raises(
        CheckFailed, match="correction does not apply: MAT 23:18 guilty"
    ):
        pipeline.marginal_notes()


def test_transcribers_remark_left_in_note(marginal_notes_config):
    # This correction removes "[symbol in wrong place in 1611]".
    del marginal_notes_config["corrections"]["MAT 5:15 a bushel"]
    with pytest.raises(
        CheckFailed, match="Transcriber's remark left in marginal note: MAT 5:15"
    ):
        pipeline.marginal_notes()


def test_unused_anchor(marginal_notes_config):
    marginal_notes_config["anchors"]["MAT 1:1 nothing"] = {"anchor": "nothing"}
    with pytest.raises(CheckFailed, match="Unused marginal note anchors"):
        pipeline.marginal_notes()


def test_missing_anchor_verse(archives, marginal_notes_config):
    marginal_notes_config["anchors"]["MAT 12:14 held a counsel"]["verse"] = "12:99"
    with pytest.raises(CheckFailed, match="verse missing: MAT 12:14 held a counsel"):
        pipeline.scripture_text(unit("MAT"), archives)


def test_wrong_anchor(archives, marginal_notes_config):
    # George's lemma reads "counsel" where the Cambridge text has "council".
    del marginal_notes_config["anchors"]["MAT 12:14 held a counsel"]
    with pytest.raises(
        CheckFailed, match=r"not found exactly once: MAT 12:14 held a counsel \(0\)"
    ):
        pipeline.scripture_text(unit("MAT"), archives)


def test_ambiguous_anchor(archives, marginal_notes_config):
    # "of" occurs more than once in Matthew 6:1; the override picks the second.
    del marginal_notes_config["anchors"]["MAT 6:1 of"]
    with pytest.raises(
        CheckFailed, match=r"not found exactly once: MAT 6:1 of \([2-9]\)"
    ):
        pipeline.scripture_text(unit("MAT"), archives)


def test_anchor_inside_added_words(archives, marginal_notes_config):
    # "it" is the second of Mark 3:21's added words "of it".
    marginal_notes_config["anchors"]["MRK 3:21 friends"] = {"anchor": "it"}
    with pytest.raises(
        CheckFailed, match="caller inside a character span: MRK 3:21 friends"
    ):
        pipeline.scripture_text(unit("MRK"), archives)


# Scripture preparation


def test_ezra_nehemiah_split_must_match_the_manifest(archives):
    entry = {**unit("EZR"), "chapters": [1, 11]}
    with pytest.raises(CheckFailed, match="Manifest chapters disagree"):
        pipeline.scripture_text(entry, archives)


def test_daniel_grouping_must_match_the_manifest(archives):
    entry = {**unit("DAG"), "source_parts": ["DAG"]}
    with pytest.raises(CheckFailed, match="source_parts disagree"):
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
    project = tmp_path / "projects/BIBLE"
    local = project / "local/ptxprint/Bible"
    local.mkdir(parents=True)
    (tmp_path / "order.json").write_text(json.dumps(["GEN"]))
    (project / "GEN.usfm").write_text(SOURCE_USFM, encoding="utf-8")
    (local / "Bible_ptxp.tex").write_text(
        "%\\OmitCallerInNote{f}\n%\\OmitCallerInNote{x}\n", encoding="utf-8"
    )

    def write(output):
        (local / "GEN-Bible.usfm").write_text(output, encoding="utf-8")
        pipeline.check_processed(project, tmp_path)

    return write


def test_processed_output_unchanged(processed, tmp_path):
    processed(SOURCE_USFM.replace("\n\\p\n", "\n\\p "))
    (record,) = json.loads((tmp_path / "processed-integrity.json").read_text())
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
