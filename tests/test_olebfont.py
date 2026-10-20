"""Inspect the installed OLEBFont faces and shape them through HarfBuzz.

The image assembled them from Valkyrie OT or from Utopia; the tests that
belong to one recipe are skipped under the other, and the rest hold for both.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import unicodedata
import zipfile
from collections.abc import Iterable, Sequence
from copy import deepcopy
from functools import cache
from io import BytesIO
from pathlib import Path
from typing import IO, Any, TypedDict, cast

import pytest
from build_olebfont import (
    DIGITS,
    EREWHON_MEMBER,
    FAMILY,
    NEWPX_MEMBER,
    STYLES,
    SUFFIX,
    SUPERIOR_CODES,
    SUPERIOR_LETTERS,
    VALKYRIE_FACE,
    WORD_SPACE,
    append_layout,
    assemble_utopia,
    assemble_valkyrie,
    donor_names,
    figure_kerns,
    font_file,
    ink,
    install_chapter,
    rename,
    style_name,
    superior_placements,
)
from font_sources import MATH_MEMBERS, OLDSTYLE_SHIFTS, archive_font, normalized_donor
from fontTools.cffLib.specializer import programToCommands
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.misc.fixedTools import otRound
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.otBase import OTTableWriter

from bible import export, paths, typeface
from bible.byzantine import variants
from bible.pipeline import Edition

FONTS = paths.FONTS / "olebfont"
EREWHON = paths.FONT_ARCHIVES / "erewhon.zip"
MATH = paths.FONT_ARCHIVES / "erewhon-math.zip"
NEWPX = paths.FONT_ARCHIVES / "newpx.zip"


def utopia(style: str) -> Path:
    return paths.UTOPIA / f"dist/Utopia-{style}.otf"


def valkyrie(style: str) -> Path:
    return paths.VALKYRIE / VALKYRIE_FACE.format(style)


def recipe() -> str:
    """Which base the installed OLEBFont was assembled from, as its
    description says."""
    with TTFont(FONTS / font_file("Regular"), lazy=True) as font:
        description = font["name"].getDebugName(10)
    return "valkyrie" if description.startswith("Valkyrie") else "utopia"


RECIPE = recipe()
utopia_only = pytest.mark.skipif(
    RECIPE != "utopia", reason="OLEBFont was assembled from Valkyrie OT"
)
valkyrie_only = pytest.mark.skipif(
    RECIPE != "valkyrie", reason="OLEBFont was assembled from Utopia"
)


class GlyphPosition(TypedDict):
    g: int
    cl: int
    ax: int
    ay: int
    dx: int
    dy: int


type Outline = list[tuple[str, tuple[tuple[float, float], ...]]]
type Program = list[int | float | str | bytes]


@pytest.fixture
def donor_path(style: str, tmp_path: Path) -> Path:
    path = tmp_path / f"Erewhon-{style}.otf"
    with zipfile.ZipFile(EREWHON) as archive:
        path.write_bytes(archive.read(EREWHON_MEMBER.format(style)))
    return path


@pytest.fixture
def scaled_donor(style: str, donor_path: Path) -> Path:
    path = donor_path.with_name("scaled.otf")
    normalized_donor(TTFont(donor_path), style).save(path)
    return path


def outline(
    glyphs: Any, name: str
) -> list[tuple[str, tuple[tuple[float, float], ...]]]:
    pen = RecordingPen()
    glyphs[name].draw(pen)
    return cast(Outline, pen.value)


def assert_outlines(
    a: Sequence[tuple[str, Sequence[tuple[float, float]]]],
    b: Sequence[tuple[str, Sequence[tuple[float, float]]]],
) -> None:
    assert len(a) == len(b)
    for (op_a, points_a), (op_b, points_b) in zip(a, b):
        assert op_a == op_b
        assert len(points_a) == len(points_b)
        for p, q in zip(points_a, points_b):
            # Serialized Type 2 operands have 16 fractional bits. Errors in
            # relative operands accumulate along a contour.
            assert p == pytest.approx(q, abs=0.002)


def assert_programs(
    a: Sequence[int | float | str | bytes], b: Sequence[int | float | str | bytes]
) -> None:
    assert len(a) == len(b)
    for x, y in zip(a, b):
        if isinstance(x, (float, int)):
            assert x == pytest.approx(y, abs=1 / 65536)
        else:
            assert x == y


def program(cs: Any) -> list[int | float | str | bytes]:
    cs.decompile()
    return cast(Program, cs.program)


@cache
def shape(path: Path, text: str, features: str) -> list[GlyphPosition]:
    return cast(
        list[GlyphPosition],
        json.loads(
            subprocess.check_output(
                [
                    "hb-shape",
                    str(path),
                    text,
                    "--features=" + features,
                    "--output-format=json",
                    "--no-glyph-names",
                ],
                text=True,
            )
        ),
    )


def shape_lines(
    path: Path, lines: Iterable[str], features: str
) -> list[list[GlyphPosition]]:
    """Shape each line by itself, in one run."""
    shaped = subprocess.run(
        [
            "hb-shape",
            str(path),
            "--features=" + features,
            "--output-format=json",
            "--no-glyph-names",
        ],
        input="\n".join(lines),
        capture_output=True,
        text=True,
        check=True,
    )
    return [json.loads(line) for line in shaped.stdout.splitlines()]


def glyph_ids(base: TTFont, donor: TTFont) -> dict[str, int]:
    """The combined font's glyph index for each source glyph name."""
    donor_map, added = donor_names(base, donor)
    # The inventory follows donor order after the 229 authoritative glyphs.
    ids = {g: i for i, g in enumerate(base.getGlyphOrder())}
    ids.update({g: len(base.getGlyphOrder()) + i for i, g in enumerate(added)})
    ids.update({g: ids[donor_map[g]] for g in donor_map if donor_map[g] in ids})
    return ids


@utopia_only
@pytest.mark.parametrize("style", STYLES)
def test_original_typography_and_hint_dependencies(
    style: str, donor_path: Path
) -> None:
    # Keep this contract independent of the builder's exception list: adding
    # another replacement there must fail rather than broaden this test.
    assert SUPERIOR_CODES == (0x00B9, 0x00B2, 0x00B3)
    base = TTFont(utopia(style))
    donor = normalized_donor(TTFont(donor_path), style)
    result = TTFont(FONTS / font_file(style))
    old_order, order = base.getGlyphOrder(), result.getGlyphOrder()
    mapping = dict(zip(old_order, order))
    rt = result["CFF "].cff[0]
    # Compare untouched serialized subroutines before glyph drawing lazily
    # decompiles them; dependencies and their original indices must survive.
    for source, fd in zip((base,), rt.FDArray):
        assert [cs.bytecode for cs in source["CFF "].cff[0].Private.Subrs] == [
            cs.bytecode for cs in fd.Private.Subrs
        ]
    base_cmap, donor_cmap, result_cmap = (
        f.getBestCmap() for f in (base, donor, result)
    )
    glyphs = {id(f): f.getGlyphSet() for f in (base, donor, result)}
    replacements = {base_cmap[c]: donor_cmap[c] for c in SUPERIOR_CODES}
    space = base_cmap[0x20]
    for g in old_order:
        replaced = g in replacements
        source, source_g = (donor, replacements[g]) if replaced else (base, g)
        target_g = mapping[g]
        assert_outlines(
            outline(glyphs[id(source)], source_g), outline(glyphs[id(result)], target_g)
        )
        if g == space:
            # The word space is widened by a fifth, in the advance and in the
            # charstring's operand alike; Utopia's 225 and 210 become 270 and 252.
            width, bearing = base["hmtx"][g]
            widened = width * WORD_SPACE[0] // WORD_SPACE[1]
            assert (width, widened) in ((225, 270), (210, 252))
            assert result["hmtx"][target_g] == (widened, bearing)
            assert program(rt.CharStrings[target_g]) == [
                widened - rt.FDArray[0].Private.nominalWidthX,
                "endchar",
            ]
            continue
        assert source["hmtx"][source_g] == result["hmtx"][target_g], g
        assert_programs(
            program(source["CFF "].cff[0].CharStrings[source_g]),
            program(rt.CharStrings[target_g]),
        )
        if replaced:
            assert rt.FDSelect.gidArray[result.getGlyphID(target_g)] == 1
    for code, g in base_cmap.items():
        assert result_cmap[code] == mapping[g]
    for tag in ("GSUB", "GPOS"):
        # Compile the preserved lookups with the combined glyph IDs;
        # every original ligature, value record and kerning pair must match.
        table = rename(deepcopy(base[tag].table), mapping)
        if tag == "GSUB":
            indices = sorted(
                {
                    i
                    for r in result[tag].table.FeatureList.FeatureRecord
                    if r.FeatureTag == "liga"
                    for i in r.Feature.LookupListIndex
                }
            )
            original_lookups = [result[tag].table.LookupList.Lookup[i] for i in indices]
        else:
            original_lookups = result[tag].table.LookupList.Lookup
        for old, new in zip(table.LookupList.Lookup, original_lookups):
            a, b = OTTableWriter(), OTTableWriter()
            old.compile(a, result)
            new.compile(b, result)
            assert a.getAllData() == b.getAllData()
    for key in ("ascent", "descent", "lineGap"):
        assert getattr(result["hhea"], key) == getattr(base["hhea"], key)
    for key in (
        "sTypoAscender",
        "sTypoDescender",
        "sTypoLineGap",
        "sCapHeight",
        "sxHeight",
    ):
        assert getattr(result["OS/2"], key) == getattr(base["OS/2"], key)
    assert rt.ROS == ("Adobe", "Identity", 0)
    assert len(rt.FDArray) == 4
    for i, source in enumerate((base, donor)):
        private = source["CFF "].cff[0].Private
        target = rt.FDArray[i].Private
        # CFF compilation omits explicit values equal to specification defaults.
        for key in (private.rawDict.keys() | target.rawDict.keys()) - {"Subrs"}:
            a, b = getattr(private, key), getattr(target, key)
            assert (
                a == pytest.approx(b, abs=0.0001)
                if isinstance(a, (int, float, list))
                else a == b
            )
        assert len(getattr(private, "Subrs", [])) == len(getattr(target, "Subrs", []))
    # Added glyphs retain donor outlines, programs and spacing too.
    _, added = donor_names(base, donor)
    for source_g, target_g in zip(added, order[len(old_order) :]):
        assert_outlines(
            outline(glyphs[id(donor)], source_g), outline(glyphs[id(result)], target_g)
        )
        expected_width, bearing = donor["hmtx"][source_g]
        expected_program = program(donor["CFF "].cff[0].CharStrings[source_g]).copy()
        assert (expected_width, bearing) == result["hmtx"][target_g]
        assert_programs(expected_program, program(rt.CharStrings[target_g]))
    assert donor_cmap.keys() <= result_cmap.keys()
    for name_id in (1, 16):
        assert result["name"].getDebugName(name_id) == FAMILY
    assert result["name"].getDebugName(6) == f"{FAMILY}-{style}"
    assert result["head"].macStyle == base["head"].macStyle
    assert result["OS/2"].fsSelection == base["OS/2"].fsSelection
    assert "Reserved Font Names" in result["name"].getDebugName(13)


@utopia_only
@pytest.mark.parametrize("style", STYLES)
def test_numerals_smallcaps_and_shaping(style: str, scaled_donor: Path) -> None:
    path = FONTS / font_file(style)
    donor = TTFont(scaled_donor)
    ids = glyph_ids(TTFont(utopia(style)), donor)
    for features, suffix in [
        ("onum=1,pnum=1", ".oldstyle"),
        ("onum=1,tnum=1", ".taboldstyle"),
        ("lnum=1,pnum=1", ".prop"),
        ("lnum=1,tnum=1", ""),
        ("sups=1", ".superior"),
        ("onum=1,pnum=1,sups=1", ".superior"),
        ("onum=1,tnum=1,sups=1", ".superior"),
    ]:
        shaped = shape(path, "0123456789", features)
        assert [g["g"] for g in shaped] == [ids[d + suffix] for d in DIGITS], features
        widths = [g["ax"] for g in shaped]
        if suffix in ("", ".taboldstyle"):
            assert len(set(widths)) == 1
        if suffix in (".oldstyle", ".prop"):
            assert len(set(widths)) > 1
        for digit, item in zip(DIGITS, shaped):
            if suffix == ".superior":
                assert item["ax"] == donor["hmtx"][digit + suffix][0]
                assert item["dy"] == 0  # elevation is designed into the outline
    unicode_superscripts = shape(path, "¹²³", "")
    assert [g["g"] for g in unicode_superscripts] == [
        ids[d + ".superior"] for d in DIGITS[1:4]
    ]
    text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    assert [g["g"] for g in shape(path, text, "c2sc=1")] == [
        ids[c + ".sc"] for c in text
    ]
    assert [g["g"] for g in shape(path, text.lower(), "smcp=1")] == [
        ids[c + ".sc"] for c in text
    ]
    # Small caps must also work in words that otherwise trigger liga.
    for text in ("office", "afflict", "fulfilled"):
        assert [g["g"] for g in shape(path, text, "smcp=1")] == [
            ids[c.upper() + ".sc"] for c in text
        ]
    # Donor positioning must survive for imported small-cap pairs.
    for text in ("AV", "To", "Wa"):
        expected = [
            item | {"g": ids[donor.getGlyphOrder()[item["g"]]]}
            for item in shape(scaled_donor, text, "smcp=1,c2sc=1")
        ]
        assert shape(path, text, "smcp=1,c2sc=1") == expected
    # Preserve actual Utopia kerning under the default shaping path.
    for text in ("AV", "To", "Wa", "ffi", "ffl"):
        assert shape(utopia(style), text, "") == shape(path, text, "")


@utopia_only
@pytest.mark.parametrize("style", STYLES)
def test_oldstyle_figure_kerning(style: str) -> None:
    path = FONTS / font_file(style)
    kerns = figure_kerns(style)
    digits = list("0123456789")
    pairs = [a + b for a in digits for b in digits]
    for features in (
        "onum=1,pnum=1",
        "onum=1,tnum=1",
        "lnum=1,pnum=1",
        "onum=1,pnum=1,sups=1",
    ):
        singles = shape_lines(path, digits, features)
        shaped = shape_lines(path, pairs, features)
        for pair, items in zip(pairs, shaped, strict=True):
            separate = sum(singles[int(d)][0]["ax"] for d in pair)
            left, right = (DIGITS[int(d)] + ".oldstyle" for d in pair)
            expected = kerns.get((left, right), 0) if features == "onum=1,pnum=1" else 0
            assert sum(item["ax"] for item in items) - separate == expected, pair


@utopia_only
def test_regular_oldstyle_figures_are_centred() -> None:
    path = FONTS / font_file("Regular")
    with path.with_suffix(".glyphs.csv").open() as stream:
        names = {
            row["SourceGlyph"]: row["Glyph"]
            for row in csv.DictReader(stream)
            if row["SourceFont"] == "Erewhon-Regular"
        }
    with TTFont(path) as font:
        glyphs = font.getGlyphSet()
        for name in OLDSTYLE_SHIFTS:
            target = names[name]
            width, lsb = font["hmtx"].metrics[target]
            bounds = BoundsPen(glyphs)
            glyphs[target].draw(bounds)
            assert bounds.bounds is not None
            x0, _, x1, _ = bounds.bounds
            assert abs(x0 - lsb) <= 1
            assert abs(width - x1 - x0) <= 1, name


@utopia_only
@pytest.mark.parametrize("style", STYLES)
def test_added_glyphs_are_positioned_as_the_donor_positions_them(
    style: str, scaled_donor: Path
) -> None:
    # Every pair of the donor's letters, not a few witnesses: a donor subtable
    # that settles a pair at zero must still keep a later one from moving it.
    donor, base = TTFont(scaled_donor), TTFont(utopia(style))
    result = TTFont(FONTS / font_file(style))
    ids = glyph_ids(base, donor)
    donor_order, first_added = donor.getGlyphOrder(), len(base.getGlyphOrder())
    donor_widths = [donor["hmtx"][g][0] for g in donor_order]
    widths = [result["hmtx"][g][0] for g in result.getGlyphOrder()]

    def adjustments(
        shaped: Sequence[GlyphPosition], widths: Sequence[int]
    ) -> list[tuple[int, int, int, int]]:
        # The sources' unadjusted widths differ; compare what is added to them.
        return [(i["ax"] - widths[i["g"]], i["ay"], i["dx"], i["dy"]) for i in shaped]

    letters = sorted(
        chr(c)
        for c in donor.getBestCmap()
        if unicodedata.name(chr(c), "").startswith("LATIN ")
    )
    pairs = [a + b for a in letters for b in letters]
    checked = 0
    for features in ("", "smcp=1,c2sc=1"):
        for pair, expected, shaped in zip(
            pairs,
            shape_lines(scaled_donor, pairs, features),
            shape_lines(FONTS / font_file(style), pairs, features),
        ):
            # Pairs of original glyphs keep Utopia's own positioning, and the
            # donor's long-s ligatures are not imported.
            if all(item["g"] < first_added for item in shaped) or [
                item["g"] for item in shaped
            ] != [ids[donor_order[item["g"]]] for item in expected]:
                continue
            checked += 1
            assert adjustments(shaped, widths) == adjustments(expected, donor_widths), (
                pair,
                features,
            )
    assert checked > 500_000


def test_rename_leaves_layout_tags_alone() -> None:
    # "zero" names both a digit's glyph and the slashed-zero feature.
    font = TTFont()
    font.setGlyphOrder([".notdef", "zero", "zero.slash"])
    addOpenTypeFeaturesFromString(
        font,
        "languagesystem DFLT dflt;\nfeature zero { sub zero by zero.slash; } zero;\n",
    )
    table = rename(font["GSUB"].table, {"zero": "cid00001", "zero.slash": "cid00002"})
    assert [r.FeatureTag for r in table.FeatureList.FeatureRecord] == ["zero"]
    assert table.LookupList.Lookup[0].SubTable[0].mapping == {"cid00001": "cid00002"}


def test_an_imported_language_keeps_only_the_original_default_features() -> None:
    def layout(features: str) -> Any:
        font = TTFont()
        font.setGlyphOrder([".notdef", "A", "B"])
        addOpenTypeFeaturesFromString(font, features)
        return font["GSUB"].table

    base = layout(
        "languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n"
        "feature liga { sub A by B; } liga;\n"
    )
    # The donor gives Turkish its small capitals, and not the default's ss01.
    donor = layout(
        "languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n"
        "languagesystem latn TRK;\n"
        "feature smcp { sub B by A; } smcp;\n"
        "feature ss01 { script latn; language dflt; sub A by B; } ss01;\n"
    )
    append_layout(base, donor)
    latin = next(
        r.Script for r in base.ScriptList.ScriptRecord if r.ScriptTag == "latn"
    )

    def tags(lang: Any) -> list[str]:
        return sorted(
            base.FeatureList.FeatureRecord[i].FeatureTag for i in lang.FeatureIndex
        )

    assert tags(latin.DefaultLangSys) == ["liga", "smcp", "ss01"]
    assert [r.LangSysTag for r in latin.LangSysRecord] == ["TRK "]
    assert tags(latin.LangSysRecord[0].LangSys) == ["liga", "smcp"]


def test_deterministic_build(tmp_path: Path) -> None:
    """Assembling the installed recipe again from its sources gives the
    installed bytes, sidecar included."""

    def assemble(f: IO[bytes], path: Path, style: str) -> None:
        if RECIPE == "valkyrie":
            assemble_valkyrie(valkyrie(style), f, path, style)
        else:
            assemble_utopia(utopia(style), f, path, style, MATH)

    archive, member = (
        (NEWPX, NEWPX_MEMBER) if RECIPE == "valkyrie" else (EREWHON, EREWHON_MEMBER)
    )
    with zipfile.ZipFile(archive) as z:
        for style in STYLES:
            path = tmp_path / font_file(style)
            with z.open(member.format(style)) as f:
                assemble(f, path, style)
            assert path.read_bytes() == (FONTS / path.name).read_bytes()
            report = path.with_suffix(".glyphs.csv")
            assert report.read_bytes() == (FONTS / report.name).read_bytes()


@utopia_only
@pytest.mark.parametrize("style", STYLES)
def test_every_selected_glyph_has_correct_source_and_scale(style: str) -> None:
    result_path = FONTS / font_file(style)
    result = TTFont(result_path)
    sources = {"Utopia-" + style: TTFont(utopia(style))}
    with zipfile.ZipFile(EREWHON) as z:
        sources["Erewhon-" + style] = TTFont(
            BytesIO(z.read(EREWHON_MEMBER.format(style)))
        )
    for member in MATH_MEMBERS:
        f = archive_font(MATH, member)
        sources[f["name"].getDebugName(6)] = f
    with result_path.with_suffix(".glyphs.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len(result.getGlyphOrder())
    assert len(rows) > 4700
    for name, f in sources.items():
        if not name.startswith("Utopia-"):
            f["CFF "].cff.desubroutinize()
    glyph_sets = {name: f.getGlyphSet() for name, f in sources.items()}
    result_glyphs = result.getGlyphSet()
    result_cmap = result.getBestCmap()
    for row in rows:
        for code in row["Unicode"].split():
            assert result_cmap[int(code[2:], 16)] == row["Glyph"]
        source = sources[row["SourceFont"]]
        g, target = row["SourceGlyph"], row["Glyph"]
        assert row["Raise"] == "0"
        factor = 1 if row["Scale"] == "1" else 100 / 94
        assert row["Scale"] in ("1", "100/94")
        if target == result_cmap[0x20]:
            continue  # the widened word space, checked with the originals
        pen = RecordingPen()
        dx = OLDSTYLE_SHIFTS.get(g, 0) if row["SourceFont"] == "Erewhon-Regular" else 0
        glyph_sets[row["SourceFont"]][g].draw(
            TransformPen(pen, (factor, 0, 0, factor, dx, 0))
        )
        assert_outlines(pen.value, outline(result_glyphs, target))
        width, bearing = source["hmtx"][g]
        if (
            style == "Italic"
            and row["SourceFont"] == "Erewhon-Italic"
            and g == "zero.taboldstyle"
        ):
            width = 500
        assert result["hmtx"][target] == (
            otRound(width * factor),
            otRound(bearing * factor) + dx,
        )
        if factor != 1:
            source_commands = programToCommands(
                program(source["CFF "].cff[0].CharStrings[g])
            )
            target_cs = result["CFF "].cff[0].CharStrings[target]
            target_commands = programToCommands(program(target_cs))
            # Advances are separately checked above. Every other numeric
            # operand (including hints) scales; operators and masks survive.
            if source_commands and source_commands[0][0] == "":
                source_commands = source_commands[1:]
            assert target_commands[0][0] == ""
            target_commands = target_commands[1:]
            assert len(source_commands) == len(target_commands)
            moved = False
            for i, ((a, args), (b, actual)) in enumerate(
                zip(source_commands, target_commands)
            ):
                assert a == b
                shifted_vertical = a in ("vstem", "vstemhm") or (
                    a == ""
                    and i + 1 < len(source_commands)
                    and all(isinstance(v, (int, float)) for v in args)
                    and source_commands[i + 1][0] in ("hintmask", "cntrmask")
                )
                if a in ("hstem", "hstemhm", "vstem", "vstemhm") or shifted_vertical:
                    # Decode absolute hint edges independently of the builder's
                    # delta re-encoding, including both ghost directions.
                    source_edge = target_edge = 0
                    assert len(args) == len(actual)
                    for j in range(0, len(args), 2):
                        source_edge += args[j]
                        target_edge += actual[j]
                        shift = dx if shifted_vertical else 0
                        width, actual_width = args[j + 1], actual[j + 1]
                        if width == -21:
                            assert actual_width == -21
                            assert target_edge - 21 == pytest.approx(
                                (source_edge - 21) * factor + shift, abs=0.002
                            )
                        else:
                            assert target_edge == pytest.approx(
                                source_edge * factor + shift, abs=0.002
                            )
                            assert actual_width == pytest.approx(
                                -20 if width == -20 else width * factor,
                                abs=1 / 65536,
                            )
                        source_edge += width
                        target_edge += actual_width
                else:
                    scaled = [
                        v * factor if isinstance(v, (int, float)) else v for v in args
                    ]
                    # Only the first move carries the shift; later ones are relative.
                    if a.endswith("moveto") and not moved:
                        scaled[0] += dx
                        moved = True
                    assert_programs(scaled, actual)
            assert target_cs.width == pytest.approx(
                result["hmtx"][target][0], abs=1 / 65536
            )
    for label, source in sources.items():
        if label.startswith("Utopia-"):
            continue
        indices = {
            result["CFF "].cff[0].FDSelect.gidArray[int(r["GID"])]
            for r in rows
            if r["SourceFont"] == label
        }
        for index in indices:
            private = source["CFF "].cff[0].Private
            target_private = result["CFF "].cff[0].FDArray[index].Private
            for attr in (
                "BlueValues",
                "OtherBlues",
                "FamilyBlues",
                "FamilyOtherBlues",
                "StdHW",
                "StdVW",
                "StemSnapH",
                "StemSnapV",
                "BlueShift",
                "BlueFuzz",
                "nominalWidthX",
                "defaultWidthX",
            ):
                value = getattr(private, attr, None)
                if value is not None:
                    expected = (
                        [v * (100 / 94) for v in value]
                        if isinstance(value, list)
                        else value * (100 / 94)
                    )
                    assert getattr(target_private, attr) == pytest.approx(
                        expected, abs=0.0001
                    )
            assert target_private.BlueScale == pytest.approx(
                private.BlueScale * 0.94, abs=0.000001
            )
            assert not len(getattr(target_private, "Subrs", []))

    # Every source codepoint is covered, including supplementary alphabets.
    assert (
        set().union(*(set(f.getBestCmap()) for f in sources.values()))
        <= result.getBestCmap().keys()
    )
    assert any(t.format == 12 for t in result["cmap"].tables)
    # Explicit, independent preference check for all standardized codepoints.
    ordered_math = [
        sources[member.rsplit("/", 1)[-1][:-4]]
        for member in (MATH_MEMBERS[::-1] if "Bold" in style else MATH_MEMBERS)
    ]
    ordered = [sources["Utopia-" + style], sources["Erewhon-" + style], *ordered_math]
    selected = {int(c[2:], 16): row for row in rows for c in row["Unicode"].split()}
    for code, row in selected.items():
        if unicodedata.category(chr(code)) == "Co":
            continue
        expected = next(
            f
            for f in (ordered[1:] if code in SUPERIOR_CODES else ordered)
            if code in f.getBestCmap()
        )
        assert row["SourceFont"] == expected["name"].getDebugName(6)
    shaped = shape(result_path, chr(0x1D400) + chr(0x2211) + chr(0x27F6), "")
    assert all(g["g"] != 0 for g in shaped)


@utopia_only
def test_inverse_scale_restores_legacy_reference_geometry() -> None:
    # Compare actual curve bounds: contour starting points differ between
    # Utopia and Erewhon, even when they describe the same geometry.
    from fontTools.pens.boundsPen import BoundsPen

    for style in ("Regular", "Italic", "BoldItalic"):
        ut = TTFont(utopia(style))
        er = normalized_donor(
            archive_font(EREWHON, EREWHON_MEMBER.format(style)), style
        )
        ug, eg = ut.getGlyphSet(), er.getGlyphSet()
        uc, ec = ut.getBestCmap(), er.getBestCmap()
        for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0":
            original, restored = BoundsPen(ug), BoundsPen(eg)
            ug[uc[ord(char)]].draw(original)
            eg[ec[ord(char)]].draw(restored)
            assert original.bounds == pytest.approx(restored.bounds, abs=1.1), (
                style,
                char,
            )
            assert abs(ut["hmtx"][uc[ord(char)]][0] - er["hmtx"][ec[ord(char)]][0]) <= 1


def test_inventory_is_complete_and_reproducible(tmp_path: Path) -> None:
    from inventory_fonts import inventory

    inventory(paths.UTOPIA, paths.FONT_ARCHIVES, tmp_path)
    repeated = tmp_path / "repeated"
    inventory(paths.UTOPIA, paths.FONT_ARCHIVES, repeated)
    for name in ("glyphs.csv", "summary.json"):
        assert (tmp_path / name).read_bytes() == (repeated / name).read_bytes()
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert len(summary["faces"]) == 12
    assert summary["total_glyph_slots"] == 15485
    with (tmp_path / "glyphs.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == summary["total_glyph_slots"]
    for face in summary["faces"]:
        slots = [row for row in rows if row["Font"] == face["font"]]
        assert [int(row["GID"]) for row in slots] == list(range(face["glyphs"]))
        assert len({row["Glyph"] for row in slots}) == face["glyphs"]
        assert all(row["SizeType"] == face["SizeType"] for row in slots)
        assert (
            sum(len(row["Unicode"].split()) for row in slots)
            == face["unicode_mappings"]
        )


def test_ghost_hint_markers_and_edges_survive_scaling() -> None:
    from font_sources import scaled_stems

    # Bottom edge at zero, then a real stem at 218, then a top edge at 650.
    assert scaled_stems([21, -21, 218, 43, 389, -20], 2) == [21, -21, 436, 86, 778, -20]
    # An edge following a ghost must use the preserved sentinel in its delta.
    assert scaled_stems([100, -20, 40, 10], 2) == [200, -20, 60, 20]


def sidecar(style: str) -> list[dict[str, str]]:
    with (FONTS / font_file(style)).with_suffix(".glyphs.csv").open() as stream:
        return list(csv.DictReader(stream))


@pytest.mark.parametrize("style", STYLES)
def test_faces_are_named_and_featured_alike(style: str) -> None:
    """Whatever the base, the family is OLEBFont in every name, and the
    features the stylesheet and layout select are there."""
    with TTFont(FONTS / font_file(style)) as font:
        names = font["name"]
        assert names.getDebugName(1) == names.getDebugName(16) == FAMILY
        assert names.getDebugName(2) == names.getDebugName(17) == style_name(style)
        assert names.getDebugName(4) == f"{FAMILY} {style_name(style)}"
        assert names.getDebugName(6) == f"{FAMILY}-{style}"
        assert font["CFF "].cff.fontNames == [f"{FAMILY}-{style}"]
        features = {r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord}
        assert {"onum", "lnum", "pnum", "tnum", "sups"} <= features
        # The running heads and the headings set in small caps are
        # upright; Valkyrie's italics have none.
        if RECIPE == "utopia" or "Italic" not in style:
            assert {"smcp", "c2sc"} <= features
        assert "kern" in {
            r.FeatureTag for r in font["GPOS"].table.FeatureList.FeatureRecord
        }


@pytest.mark.parametrize("style", STYLES)
def test_sups_sets_every_label_the_edition_prints(style: str) -> None:
    """Verse numbers, note origins and callers are set with sups over
    oldstyle proportional figures: every digit in every form, the letter of
    a suffixed label, the colon of a chapter-and-verse label, in both
    recipes' designed superiors, never a shrunken or raised full-size glyph."""
    path = FONTS / font_file(style)
    rows = sidecar(style)
    # Erewhon's superiors, Valkyrie's figures and npxsups' letters, as the
    # sidecar names each glyph's source.
    superior = {".superior", SUFFIX, ".sup"}

    def source_glyphs(shaped: Sequence[GlyphPosition]) -> list[str]:
        return [rows[item["g"]]["SourceGlyph"] for item in shaped]

    for features in (
        "sups=1",
        "onum=1,pnum=1,sups=1",
        "onum=1,tnum=1,sups=1",
        "lnum=1,pnum=1,sups=1",
        "lnum=1,tnum=1,sups=1",
    ):
        # The ligatures a font forms (fi, fl) must come apart into superiors.
        for text in (
            "0123456789",
            "35a",
            "30:1",
            "23b",
            SUPERIOR_LETTERS,
            ":",
            "fi",
            "fl",
        ):
            shaped = shape(path, text, features)
            assert len(shaped) == len(text), (text, features)
            for char, g in zip(text, source_glyphs(shaped)):
                stem, dot, suffix = g.partition(".")
                assert dot + suffix in superior, (text, features, g)
                expected = {":": "colon"}.get(char, char)
                if char.isdigit():
                    expected = DIGITS[int(char)]
                assert stem == expected, (text, features, g)
            assert all(item["dy"] == 0 for item in shaped), (text, features)
    # The encoded superior figures are the glyphs sups selects.
    assert source_glyphs(shape(path, "¹²³", "")) == source_glyphs(
        shape(path, "123", "onum=1,pnum=1,sups=1")
    )
    # A superior letter is smaller than the letter it stands for.
    plain = {item["cl"]: item["ax"] for item in shape(path, SUPERIOR_LETTERS, "")}
    for item in shape(path, SUPERIOR_LETTERS, "sups=1"):
        assert item["ax"] < plain[item["cl"]]


RUNS = re.compile(r"\\\+?w[gh] .*?\\\+?w[gh]\*", re.S)


@pytest.fixture(scope="module")
def latin_characters(edition: Edition) -> set[str]:
    """Every character the exported edition prints outside the Greek and
    Hebrew runs, which their own fonts set: exported once for every face."""
    text = "".join(
        RUNS.sub("", document) for _, document in export.export(edition, "pdf")
    )
    return {c for c in text if not c.isspace()}


@pytest.mark.parametrize("style", STYLES)
def test_every_latin_character_of_the_edition_is_encoded(
    latin_characters: set[str], style: str
) -> None:
    """Outside the Greek and Hebrew runs, which their own fonts set, every
    character the exported edition prints has a glyph in every face."""
    characters = latin_characters
    assert len(characters) > 90
    with TTFont(FONTS / font_file(style)) as font:
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


def test_greek_is_paired_with_the_base() -> None:
    """GFS Heraklit goes with Valkyrie, GFS Didot with Utopia."""
    assert (
        typeface.greek_family()
        == {
            "valkyrie": "GFS Heraklit",
            "utopia": "GFS Didot",
        }[RECIPE]
    )


@valkyrie_only
@pytest.mark.parametrize("style", STYLES)
def test_valkyrie_is_untouched_but_for_its_names(style: str) -> None:
    """Every glyph, metric, feature and kerning pair of the base survives as
    it was, with the base's notices; only the family's names change and
    the superiors are added after the base's glyphs."""
    base = TTFont(valkyrie(style))
    result = TTFont(FONTS / font_file(style))
    order = base.getGlyphOrder()
    assert result.getGlyphOrder()[: len(order)] == order
    assert result.getBestCmap() == base.getBestCmap()
    base_glyphs, result_glyphs = base.getGlyphSet(), result.getGlyphSet()
    base_cff, result_cff = base["CFF "].cff[0], result["CFF "].cff[0]
    for g in order:
        assert base["hmtx"][g] == result["hmtx"][g], g
        assert_outlines(outline(base_glyphs, g), outline(result_glyphs, g))
        assert_programs(
            program(base_cff.CharStrings[g]), program(result_cff.CharStrings[g])
        )
    assert base["hmtx"]["space"] == result["hmtx"]["space"]
    for key in ("ascent", "descent", "lineGap"):
        assert getattr(result["hhea"], key) == getattr(base["hhea"], key)
    for key in (
        "fsType",
        "fsSelection",
        "sTypoAscender",
        "sTypoDescender",
        "sTypoLineGap",
        "usWinAscent",
        "usWinDescent",
        "sCapHeight",
        "sxHeight",
    ):
        assert getattr(result["OS/2"], key) == getattr(base["OS/2"], key)
    # The original lookups, compiled with the combined glyph ids, match.
    for tag in ("GSUB", "GPOS"):
        original = base[tag].table.LookupList.Lookup
        kept = result[tag].table.LookupList.Lookup[: len(original)]
        for old, new in zip(original, kept, strict=True):
            a, b = OTTableWriter(), OTTableWriter()
            old.compile(a, result)
            new.compile(b, result)
            assert a.getAllData() == b.getAllData()
    for text in ("AV", "To", "Wa", "ffi", "Office", "1234"):
        assert shape(valkyrie(style), text, "") == shape(
            FONTS / font_file(style), text, ""
        )
        assert shape(valkyrie(style), text, "onum=1,pnum=1") == shape(
            FONTS / font_file(style), text, "onum=1,pnum=1"
        )
    for name_id in (0, 7, 14):
        assert result["name"].getDebugName(name_id) == base["name"].getDebugName(
            name_id
        )
    licence = result["name"].getDebugName(13)
    assert licence.startswith(base["name"].getDebugName(13))
    assert "TeX Gyre" in licence and "Michael Sharpe" in licence
    assert "Valkyrie" not in (
        result["name"].getDebugName(1),
        result["name"].getDebugName(4),
    )


@valkyrie_only
@pytest.mark.parametrize("style", STYLES)
def test_superiors_are_the_donors_scaled_to_the_figures(style: str) -> None:
    """Each added superior is npxsups' letter or colon under the one
    transform superior_placements gives, which lays the donor's superior
    figures on the base's; and the sidecar records the placement."""
    base = TTFont(valkyrie(style))
    donor = archive_font(NEWPX, NEWPX_MEMBER.format(style))
    result = TTFont(FONTS / font_file(style))
    placements = superior_placements(base, donor)
    assert set(placements) == {c + SUFFIX for c in SUPERIOR_LETTERS} | {"colon.sups"}
    added = result.getGlyphOrder()[len(base.getGlyphOrder()) :]
    assert added == list(placements)
    donor_glyphs, result_glyphs = donor.getGlyphSet(), result.getGlyphSet()
    private = result["CFF "].cff[0].Private
    rows = {row["Glyph"]: row for row in sidecar(style)}
    _, bottom, _, top = ink(result_glyphs, "one" + SUFFIX)
    for g, (source_g, scale, dy) in placements.items():
        width = otRound(donor["hmtx"][source_g][0] * scale)
        # The charstring is the donor's outline transformed and written by
        # the same pen, which rounds to units and specializes the operators.
        pen = T2CharStringPen(width - private.nominalWidthX, None)
        donor_glyphs[source_g].draw(TransformPen(pen, (scale, 0, 0, scale, 0, dy)))
        expected = pen.getCharString(private, result["CFF "].cff.GlobalSubrs)
        assert program(result["CFF "].cff[0].CharStrings[g]) == program(expected)
        bounds = BoundsPen(None)
        expected.draw(bounds)
        assert result["hmtx"][g] == (width, otRound(bounds.bounds[0]))
        assert rows[g]["SourceFont"] == f"npxsups-{style}"
        assert rows[g]["SourceGlyph"] == source_g
        assert float(rows[g]["Scale"]) == pytest.approx(scale)
        assert float(rows[g]["Raise"]) == pytest.approx(dy)
    # One transform: the donor's superior one spans the base's superior one,
    # so every donated glyph keeps its proportion to the figures.
    _, donor_bottom, _, donor_top = ink(donor_glyphs, "one.sup")
    scales = {scale for _, scale, _ in placements.values()}
    raises = {dy for _, _, dy in placements.values()}
    assert len(scales) == len(raises) == 1
    (scale,), (dy,) = scales, raises
    assert (donor_top - donor_bottom) * scale == pytest.approx(top - bottom)
    assert donor_bottom * scale + dy == pytest.approx(bottom)
    for name in ("x", "colon"):
        _, g_bottom, _, g_top = ink(result_glyphs, name + SUFFIX)
        _, d_bottom, _, d_top = ink(donor_glyphs, name + ".sup")
        # Within the unit the pen rounds to.
        assert g_bottom == pytest.approx(d_bottom * scale + dy, abs=1)
        assert g_top == pytest.approx(d_top * scale + dy, abs=1)
    _, x_bottom, _, x_top = ink(result_glyphs, "x" + SUFFIX)
    assert bottom - 10 <= x_bottom and x_top < top
    for row in rows.values():
        if row["Glyph"] not in placements:
            assert (row["SourceFont"], row["Scale"], row["Raise"]) == (
                f"ValkyrieOTA{style}",
                "1",
                "0",
            )


def test_chapter_installation_preserves_archive_bytes(tmp_path: Path) -> None:
    install_chapter(NEWPX, tmp_path)
    with zipfile.ZipFile(NEWPX) as z:
        if RECIPE == "valkyrie":
            assert typeface.chapter_face().read_bytes() == z.read(
                "newpx/opentype/TeXGyrePagellaX-Regular.otf"
            )
        else:
            assert not (paths.FONTS / "chapter").exists()
            assert (
                typeface.chapter_face().read_bytes()
                == (FONTS / font_file("Regular")).read_bytes()
            )
        for member in (
            "newpx/opentype/TeXGyrePagellaX-Regular.otf",
            "newpx/doc/MANIFEST-newpx.txt",
            "newpx/README",
        ):
            assert (tmp_path / Path(member).name).read_bytes() == z.read(member)


def test_chapter_lining_proportional_figures() -> None:
    face = typeface.chapter_face()
    digits = "0123456789"
    lining = shape(face, digits, "lnum=1,pnum=1")
    oldstyle = shape(face, digits, "onum=1,pnum=1")
    tabular = shape(face, digits, "lnum=1,tnum=1")
    assert all(g["g"] for g in lining)
    assert [g["g"] for g in lining] != [g["g"] for g in oldstyle]
    assert len({g["ax"] for g in lining}) > 1
    assert len({g["ax"] for g in tabular}) == 1
