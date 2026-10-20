"""The fonts the image installed for the edition: OLEBFont, which the image
build assembled from Valkyrie OT where the host had its four faces and from
Utopia otherwise (scripts/build_olebfont.py), the Greek face it paired with
that base (GFS Heraklit with Valkyrie, GFS Didot with Utopia), and Ezra SIL
for Hebrew, plus newpx for Valkyrie's printed chapter numerals. The build
selects the chapter face from the installed Greek family's pairing."""

from __future__ import annotations

from pathlib import Path

from fontTools.ttLib import TTFont

from bible import paths
from bible.checks import require

LATIN = paths.FONTS / "olebfont"
GREEK = paths.FONTS / "greek"
HEBREW = paths.EZRA
FAMILY = "OLEBFont"
CHAPTER = paths.FONTS / "chapter/TeXGyrePagellaX-Regular.otf"


def faces(directory: Path) -> list[Path]:
    """The faces installed in a directory, refused when there are none."""
    found = sorted(directory.glob("*.otf"))
    require(found, f"No fonts installed in {directory}; run make bootstrap")
    return found


def installed() -> list[Path]:
    """The shared print/web faces; the chapter numeral face is print-only."""
    require(HEBREW.is_file(), f"Missing {HEBREW}; run make bootstrap")
    return [*faces(LATIN), *faces(GREEK), HEBREW]


def family(face: Path) -> str:
    """A face's family, as fontconfig, PTXprint and CSS name it."""
    with TTFont(face, lazy=True) as font:
        return str(font["name"].getDebugName(16) or font["name"].getDebugName(1))


def postscript_family(face: Path) -> str:
    """The prefix pdffonts prints for a face's family, from its PostScript
    name: GFSHeraklit for GFSHeraklit-Regular."""
    return postscript_name(face).split("-")[0]


def postscript_name(face: Path) -> str:
    """The exact face name written in a PDF's font inventory."""
    with TTFont(face, lazy=True) as font:
        return str(font["name"].getDebugName(6))


def style(face: Path) -> tuple[int, str]:
    """A face's CSS weight and style, from its subfamily name."""
    with TTFont(face, lazy=True) as font:
        subfamily = str(font["name"].getDebugName(17) or font["name"].getDebugName(2))
    return 700 if "Bold" in subfamily else 400, (
        "italic" if "Italic" in subfamily else "normal"
    )


def greek_face() -> Path:
    """The Greek face that names its family: the regular, where there are more."""
    return faces(GREEK)[0]


def greek_family() -> str:
    """The family the Greek is set in, in print and on the website."""
    return family(greek_face())


def chapter_face() -> Path:
    """Newpx with Valkyrie/Heraklit; OLEBFont Regular with Utopia/Didot."""
    face = (
        CHAPTER if greek_family() == "GFS Heraklit" else LATIN / "OLEBFont-Regular.otf"
    )
    require(face.is_file(), f"Missing chapter font {face}; run make bootstrap")
    return face
