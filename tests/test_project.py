"""The PTXprint project is written for the fonts the image installed."""

from pathlib import Path

from bible import typeface
from bible.pipeline import Edition
from bible.project import project_settings, style_mods, write_project


def test_project_sets_greek_in_the_installed_face(
    edition: Edition, tmp_path: Path
) -> None:
    project, ids = write_project("sample", tmp_path, [("GEN", "\\id GEN\n")], edition)
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
