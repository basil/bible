"""The PTXprint project is written for the fonts the image installed."""

from pathlib import Path

import pytest

from bible import export, pipeline, typeface, usj
from bible.checks import CheckFailed
from bible.pipeline import Edition
from bible.project import project_settings, running_heads, style_mods, write_project


def test_running_heads_use_the_selected_chapters(edition: Edition) -> None:
    doc = edition.documents["DAG"]
    before = usj.serialize(doc)
    assert running_heads([("DAG", doc)]) == (
        "\\BibleRunningHead{Daniel}{0}{Susanna}\n"
        "\\BibleRunningHead{Daniel}{13}{Bel and the Dragon}\n"
    )
    assert running_heads([("DAG", pipeline.sample_chapters("DAG", doc, [13]))]) == (
        "\\BibleRunningHead{Daniel}{13}{Bel and the Dragon}\n"
    )
    assert running_heads([("DAG", pipeline.sample_chapters("DAG", doc, [1, 12]))]) == ""
    assert usj.serialize(doc) == before


@pytest.mark.parametrize("heading", ["", "\\cl\n"])
def test_hidden_chapter_requires_a_heading(heading: str) -> None:
    doc = usj.parse("\\id DAG\n\\h Daniel\n\\c 0\n\\cp \u200b\n" + heading)
    with pytest.raises(CheckFailed, match="Unnumbered chapter has no heading: 0"):
        running_heads([("DAG", doc)])


def test_project_sets_greek_in_the_installed_face(
    edition: Edition, tmp_path: Path
) -> None:
    project, ids = write_project(
        "sample", tmp_path, [("GEN", usj.parse("\\id GEN\n"))], edition
    )
    assert ids == ["GEN"]
    settings = project_settings(project)
    for key in ("fontregular", "fontbold", "fontitalic", "fontbolditalic"):
        assert settings["document"][key].startswith("OLEBFont|")
        assert settings["document"][key].endswith("|onum=1|pnum=1")
    assert "<DefaultFont>OLEBFont</DefaultFont>" in (
        project / "Settings.xml"
    ).read_text(encoding="utf-8")
    styles = (project / "shared/ptxprint/Bible/ptxprint-mods.sty").read_text(
        encoding="utf-8"
    )
    assert styles == style_mods()
    assert styles.count("\\Marker wg\n") == 1
    assert styles.endswith(f"\n\\Marker wg\n\\FontName {typeface.greek_family()}\n")
    assert typeface.greek_family() in ("GFS Didot", "GFS Heraklit")


@pytest.mark.parametrize("mode", ["sample", "pdf"])
def test_only_the_sample_title_page_is_marked(
    edition: Edition, tmp_path: Path, mode: str
) -> None:
    project, _ = write_project(
        mode, tmp_path, [("GEN", usj.parse("\\id GEN\n"))], edition
    )
    subtitle = project_settings(project)["vars"]["subtitle"]
    assert subtitle.endswith("TYPESETTING SAMPLE: selected chapters") == (
        mode == "sample"
    )


def test_standard_peripherals_get_unique_ptxprint_transport_aliases(
    edition: Edition, tmp_path: Path
) -> None:
    documents = export.grouped(edition, export.prepared(edition, "sample"))
    project, ids = write_project("sample", tmp_path, documents, edition)
    config = project / "shared/ptxprint/Bible"
    assert (config / "ptxprint-mods.tex").read_text().endswith(running_heads(documents))
    assert (config / "running-heads.tex").is_file()
    assert len(ids) == len(set(ids))
    divisions = []
    for (source, original), physical in zip(documents, ids):
        logical = usj.parse(usj.serialize(original))
        published = usj.parse((project / f"{physical}.usfm").read_text())
        assert usj.with_code(published, logical["content"][0]["code"]) == logical
        if source not in edition.scripture:
            code = logical["content"][0]["code"]
            assert code in {"FRT", "INT", "BAK"}
            # The back matter's run is PTXprint's own back matter book.
            assert physical == "BAK" if code == "BAK" else physical.startswith("XX")
            divisions += [n["id"] for n in logical["content"] if n["type"] == "periph"]
    assert divisions == [
        n["id"] for _, doc in documents for n in doc["content"] if n["type"] == "periph"
    ]
