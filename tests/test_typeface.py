"""The fonts the image installed, as the build reads them."""

from pathlib import Path

import pytest

from bible import typeface
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
