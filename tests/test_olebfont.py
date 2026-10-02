"""Inspect serialized production fonts and shape them through HarfBuzz."""

import csv
import json
import subprocess
import unicodedata
import zipfile
from copy import deepcopy
from functools import cache
from io import BytesIO

import pytest
from build_olebfont import (
    DIGITS,
    EREWHON_MEMBER,
    FAMILY,
    STYLES,
    SUPERIOR_CODES,
    append_layout,
    assemble,
    donor_names,
    font_file,
    rename,
)
from font_sources import MATH_MEMBERS, archive_font, normalized_donor
from fontTools.cffLib.specializer import programToCommands
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.misc.fixedTools import otRound
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.otBase import OTTableWriter

from bible import paths

FONTS = paths.FONTS / "olebfont"
EREWHON = paths.FONT_ARCHIVES / "erewhon.zip"
MATH = paths.FONT_ARCHIVES / "erewhon-math.zip"


def utopia(style):
    return paths.UTOPIA / f"dist/Utopia-{style}.otf"


@pytest.fixture
def donor_path(style, tmp_path):
    path = tmp_path / f"Erewhon-{style}.otf"
    with zipfile.ZipFile(EREWHON) as archive:
        path.write_bytes(archive.read(EREWHON_MEMBER.format(style)))
    return path


@pytest.fixture
def scaled_donor(style, donor_path):
    path = donor_path.with_name("scaled.otf")
    normalized_donor(TTFont(donor_path), style).save(path)
    return path


def outline(glyphs, name):
    pen = RecordingPen()
    glyphs[name].draw(pen)
    return pen.value


def assert_outlines(a, b):
    assert len(a) == len(b)
    for (op_a, points_a), (op_b, points_b) in zip(a, b):
        assert op_a == op_b
        assert len(points_a) == len(points_b)
        for p, q in zip(points_a, points_b):
            # Serialized Type 2 operands have 16 fractional bits. Errors in
            # relative operands accumulate along a contour.
            assert p == pytest.approx(q, abs=0.002)


def assert_programs(a, b):
    assert len(a) == len(b)
    for x, y in zip(a, b):
        if isinstance(x, (float, int)):
            assert x == pytest.approx(y, abs=1 / 65536)
        else:
            assert x == y


def program(cs):
    cs.decompile()
    return cs.program


@cache
def shape(path, text, features):
    return json.loads(
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
    )


def shape_lines(path, lines, features):
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


def glyph_ids(base, donor):
    """The combined font's glyph index for each source glyph name."""
    donor_map, added = donor_names(base, donor)
    # The inventory follows donor order after the 229 authoritative glyphs.
    ids = {g: i for i, g in enumerate(base.getGlyphOrder())}
    ids.update({g: len(base.getGlyphOrder()) + i for i, g in enumerate(added)})
    ids.update({g: ids[donor_map[g]] for g in donor_map if donor_map[g] in ids})
    return ids


@pytest.mark.parametrize("style", STYLES)
def test_original_typography_and_hint_dependencies(style, donor_path):
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
    for g in old_order:
        replaced = g in replacements
        source, source_g = (donor, replacements[g]) if replaced else (base, g)
        target_g = mapping[g]
        assert_outlines(
            outline(glyphs[id(source)], source_g), outline(glyphs[id(result)], target_g)
        )
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
    for key in (1, 16):
        assert result["name"].getDebugName(key) == FAMILY
    assert result["name"].getDebugName(6) == f"{FAMILY}-{style}"
    assert result["head"].macStyle == base["head"].macStyle
    assert result["OS/2"].fsSelection == base["OS/2"].fsSelection
    assert "Reserved Font Names" in result["name"].getDebugName(13)


@pytest.mark.parametrize("style", STYLES)
def test_numerals_smallcaps_and_shaping(style, scaled_donor):
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


@pytest.mark.parametrize("style", STYLES)
def test_added_glyphs_are_positioned_as_the_donor_positions_them(style, scaled_donor):
    # Every pair of the donor's letters, not a few witnesses: a donor subtable
    # that settles a pair at zero must still keep a later one from moving it.
    donor, base = TTFont(scaled_donor), TTFont(utopia(style))
    result = TTFont(FONTS / font_file(style))
    ids = glyph_ids(base, donor)
    donor_order, first_added = donor.getGlyphOrder(), len(base.getGlyphOrder())
    donor_widths = [donor["hmtx"][g][0] for g in donor_order]
    widths = [result["hmtx"][g][0] for g in result.getGlyphOrder()]

    def adjustments(shaped, widths):
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


def test_rename_leaves_layout_tags_alone():
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


def test_an_imported_language_keeps_only_the_original_default_features():
    def layout(features):
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

    def tags(lang):
        return sorted(
            base.FeatureList.FeatureRecord[i].FeatureTag for i in lang.FeatureIndex
        )

    assert tags(latin.DefaultLangSys) == ["liga", "smcp", "ss01"]
    assert [r.LangSysTag for r in latin.LangSysRecord] == ["TRK "]
    assert tags(latin.LangSysRecord[0].LangSys) == ["liga", "smcp"]


def test_deterministic_build(tmp_path):
    with zipfile.ZipFile(EREWHON) as z:
        for style in STYLES:
            path = tmp_path / font_file(style)
            with z.open(EREWHON_MEMBER.format(style)) as f:
                assemble(utopia(style), f, path, style, MATH)
            assert path.read_bytes() == (FONTS / path.name).read_bytes()
            report = path.with_suffix(".glyphs.csv")
            assert report.read_bytes() == (FONTS / report.name).read_bytes()


@pytest.mark.parametrize("style", STYLES)
def test_every_selected_glyph_has_correct_source_and_scale(style):
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
        factor = 1 if row["SizeType"] == "Utopia" else 100 / 94
        pen = RecordingPen()
        glyph_sets[row["SourceFont"]][g].draw(
            TransformPen(pen, (factor, 0, 0, factor, 0, 0))
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
            otRound(bearing * factor),
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
            for (a, args), (b, actual) in zip(source_commands, target_commands):
                assert a == b
                if a in ("hstem", "hstemhm", "vstem", "vstemhm"):
                    # Decode absolute hint edges independently of the builder's
                    # delta re-encoding, including both ghost directions.
                    source_edge = target_edge = 0
                    assert len(args) == len(actual)
                    for j in range(0, len(args), 2):
                        source_edge += args[j]
                        target_edge += actual[j]
                        width, actual_width = args[j + 1], actual[j + 1]
                        if width == -21:
                            assert actual_width == -21
                            assert target_edge - 21 == pytest.approx(
                                (source_edge - 21) * factor, abs=0.002
                            )
                        else:
                            assert target_edge == pytest.approx(
                                source_edge * factor, abs=0.002
                            )
                            assert actual_width == pytest.approx(
                                -20 if width == -20 else width * factor,
                                abs=1 / 65536,
                            )
                        source_edge += width
                        target_edge += actual_width
                else:
                    assert_programs(
                        [
                            v * factor if isinstance(v, (int, float)) else v
                            for v in args
                        ],
                        actual,
                    )
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


def test_inverse_scale_restores_legacy_reference_geometry():
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


def test_inventory_is_complete_and_reproducible(tmp_path):
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


def test_ghost_hint_markers_and_edges_survive_scaling():
    from font_sources import scaled_stems

    # Bottom edge at zero, then a real stem at 218, then a top edge at 650.
    assert scaled_stems([21, -21, 218, 43, 389, -20], 2) == [21, -21, 436, 86, 778, -20]
    # An edge following a ghost must use the preserved sentinel in its delta.
    assert scaled_stems([100, -20, 40, 10], 2) == [200, -20, 60, 20]
