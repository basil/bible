"""The fonts the image installed, as the build reads them."""

import re
from pathlib import Path

import pytest
from build_olebfont import STYLES, font_file
from fontTools.ttLib import TTFont

from bible import paths, typeface
from bible.byzantine import variants
from bible.checks import CheckFailed
from bible.pipeline import Edition


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


RUNS = re.compile(r"\\\+?w[gh] .*?\\\+?w[gh]\*", re.S)


@pytest.fixture(scope="module")
def latin_characters(exported: dict[str, str]) -> set[str]:
    """Every character the exported edition prints outside the Greek and
    Hebrew runs, which their own fonts set: shared with the other export checks."""
    text = "".join(RUNS.sub("", document) for document in exported.values())
    return {c for c in text if not c.isspace()}


@pytest.mark.parametrize("style", STYLES)
def test_every_latin_character_of_the_edition_is_encoded(
    latin_characters: set[str], style: str
) -> None:
    """Outside the Greek and Hebrew runs, which their own fonts set, every
    character the exported edition prints has a glyph in every face."""
    characters = latin_characters
    assert len(characters) > 90
    with TTFont(typeface.LATIN / font_file(style)) as font:
        missing = characters - set(map(chr, font.getBestCmap()))
    assert missing == set()


# What each Greek face lacks of the variants' characters: GFS Heraklit has no
# stigma, the numeral of the Received Text's number of the beast at Revelation
# 13:18, which the browser sets from another font.
GREEK_GAPS = {"GFS Didot": set(), "GFS Heraklit": {"ϛ"}}


@pytest.mark.parametrize("bold", [False, True], ids=["regular", "bold"])
def test_installed_greek_covers_the_variants(edition: Edition, bold: bool) -> None:
    """The website sets the Greek lanes in the installed Greek face, and the
    words a correction of the English is about in its bold; where the family
    has no bold (Heraklit), the browser emboldens its one face."""
    faces = typeface.faces(typeface.GREEK)
    face = next((f for f in faces if typeface.style(f) == (700, "normal")), None)
    if bold and face is None:
        pytest.skip(f"{typeface.greek_family()} has no bold face")
    face = face if bold else faces[0]
    assert face is not None
    segments = [
        segment
        for _, lanes in edition.variants
        for lane in lanes
        if lane["language"] == "grc"
        for segment in lane["segments"]
    ]
    if bold:
        segments = [s for s in segments if not isinstance(s, str) and "about" in s]
    greek_chars = {
        ord(c)
        for segment in segments
        for side in ("from", "to")
        for c in variants.witness([segment], side)
        if not c.isspace()
    }
    assert greek_chars
    with TTFont(face) as font:
        cmap = font.getBestCmap()
    assert {chr(c) for c in greek_chars - cmap.keys()} == GREEK_GAPS[
        typeface.greek_family()
    ]
    # The premise of export.ELISION: no Greek face encodes the elision mark,
    # and every one encodes the apostrophe set in its place.
    assert 0x2BC not in cmap and 0x2019 in cmap
