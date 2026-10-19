"""The PTXprint project is written for the fonts the image installed."""

from pathlib import Path

from bible import export, typeface, usj
from bible.pipeline import Edition
from bible.project import project_settings, style_mods, write_project


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


def test_standard_peripherals_get_unique_ptxprint_transport_aliases(
    edition: Edition, tmp_path: Path
) -> None:
    documents = export.grouped(edition, export.prepared(edition, "sample"))
    project, ids = write_project("sample", tmp_path, documents, edition)
    assert len(ids) == len(set(ids))
    divisions = []
    for (source, original), physical in zip(documents, ids):
        logical = usj.parse(usj.serialize(original))
        published = usj.parse((project / f"{physical}.usfm").read_text())
        assert usj.with_code(published, logical["content"][0]["code"]) == logical
        if source not in edition.scripture:
            assert logical["content"][0]["code"] in {"FRT", "INT"}
            assert physical.startswith("XX")
            divisions += [n["id"] for n in logical["content"] if n["type"] == "periph"]
    assert divisions == [
        n["id"] for _, doc in documents for n in doc["content"] if n["type"] == "periph"
    ]
