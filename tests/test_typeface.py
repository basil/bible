"""The fonts the image installed, as the build reads them."""

from pathlib import Path

import pytest

from bible import paths, typeface
from bible.checks import CheckFailed


def test_installed_faces() -> None:
    faces = typeface.installed()
    assert [f.name for f in faces[:4]] == [
        f"OLEBFont-{style}.otf" for style in ("Bold", "BoldItalic", "Italic", "Regular")
    ]
    assert faces[-1] == typeface.HEBREW
    assert all(typeface.family(f) == typeface.FAMILY for f in faces[:4])
    assert all(typeface.postscript_family(f) == typeface.FAMILY for f in faces[:4])
    assert [typeface.style(f) for f in faces[:4]] == [
        (700, "normal"),
        (700, "italic"),
        (400, "italic"),
        (400, "normal"),
    ]
    assert typeface.family(typeface.HEBREW) == "Ezra SIL"
    assert typeface.postscript_family(typeface.HEBREW) == "EzraSIL"
    assert typeface.style(typeface.HEBREW) == (400, "normal")


def test_greek_face() -> None:
    """One Greek family, paired by the image build with OLEBFont's base."""
    faces = typeface.faces(typeface.GREEK)
    family = typeface.greek_family()
    assert family in ("GFS Didot", "GFS Heraklit")
    assert all(typeface.family(f) == family for f in faces)
    assert typeface.postscript_family(faces[0]) == family.replace(" ", "")
    assert len(faces) == (4 if family == "GFS Didot" else 1)


def test_missing_faces_stop_the_build(tmp_path: Path) -> None:
    with pytest.raises(
        CheckFailed, match="No fonts installed in .*; run make bootstrap"
    ):
        typeface.faces(tmp_path)


def test_installed_chapter_selection() -> None:
    face = typeface.chapter_face()
    assert typeface.style(face) == (400, "normal")
    if typeface.family(face) == typeface.FAMILY:
        # Utopia keeps its own numerals: the selection is OLEBFont Regular.
        assert face == typeface.LATIN / "OLEBFont-Regular.otf"
    else:
        assert typeface.family(face) == "TeX Gyre PagellaX"
        assert face == paths.FONTS / "chapter/TeXGyrePagellaX-Regular.otf"
        assert face not in typeface.installed()


@pytest.mark.parametrize("greek", ["GFS Heraklit", "GFS Didot"])
def test_chapter_selection_follows_font_pairing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, greek: str
) -> None:
    chapter = tmp_path / "chapter.otf"
    regular = tmp_path / "OLEBFont-Regular.otf"
    chapter.write_bytes(b"chapter")
    regular.write_bytes(b"regular")
    monkeypatch.setattr(typeface, "CHAPTER", chapter)
    monkeypatch.setattr(typeface, "LATIN", tmp_path)
    monkeypatch.setattr(typeface, "greek_family", lambda: greek)
    assert typeface.chapter_face() == (chapter if greek == "GFS Heraklit" else regular)


@pytest.mark.parametrize("greek", ["GFS Heraklit", "GFS Didot"])
def test_missing_chapter_stops_project_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, greek: str
) -> None:
    from bible.project import style_mods

    monkeypatch.setattr(typeface, "CHAPTER", tmp_path / "missing.otf")
    monkeypatch.setattr(typeface, "LATIN", tmp_path)
    monkeypatch.setattr(typeface, "greek_family", lambda: greek)
    other = (
        tmp_path / "OLEBFont-Regular.otf"
        if greek == "GFS Heraklit"
        else typeface.CHAPTER
    )
    other.write_bytes(b"other font")
    with pytest.raises(
        CheckFailed, match="Missing chapter font .*; run make bootstrap"
    ):
        style_mods()
