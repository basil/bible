"""Inspect serialized production fonts and shape them through HarfBuzz."""

from copy import deepcopy
from functools import cache
import json
import subprocess
import unicodedata
import zipfile

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.otBase import OTTableWriter
import pytest

from bible import paths
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

FONTS = paths.FONTS / "olebfont"
EREWHON = paths.FONT_ARCHIVES / "erewhon.zip"


def utopia(style):
    return paths.UTOPIA / f"dist/Utopia-{style}.otf"


@pytest.fixture
def donor_path(style, tmp_path):
    path = tmp_path / f"Erewhon-{style}.otf"
    with zipfile.ZipFile(EREWHON) as archive:
        path.write_bytes(archive.read(EREWHON_MEMBER.format(style)))
    return path


def outline(glyphs, name):
    pen = RecordingPen()
    glyphs[name].draw(pen)
    return pen.value


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
    donor = TTFont(donor_path)
    result = TTFont(FONTS / font_file(style))
    old_order, order = base.getGlyphOrder(), result.getGlyphOrder()
    mapping = dict(zip(old_order, order))
    rt = result["CFF "].cff[0]
    # Compare untouched serialized subroutines before glyph drawing lazily
    # decompiles them; dependencies and their original indices must survive.
    for source, fd in zip((base, donor), rt.FDArray):
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
        assert outline(glyphs[id(source)], source_g) == outline(
            glyphs[id(result)], target_g
        ), g
        assert source["hmtx"][source_g] == result["hmtx"][target_g], g
        assert program(source["CFF "].cff[0].CharStrings[source_g]) == program(
            rt.CharStrings[target_g]
        ), g
        if replaced:
            assert rt.FDSelect.gidArray[result.getGlyphID(target_g)] == 1
    for code, g in base_cmap.items():
        assert result_cmap[code] == mapping[g]
    for tag in ("GSUB", "GPOS"):
        # Compile the preserved lookups with the combined glyph IDs;
        # every original ligature, value record and kerning pair must match.
        table = rename(deepcopy(base[tag].table), mapping)
        original_lookups = (
            result[tag].table.LookupList.Lookup[-len(table.LookupList.Lookup) :]
            if tag == "GSUB"
            else result[tag].table.LookupList.Lookup
        )
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
    assert len(rt.FDArray) == 2
    for i, source in enumerate((base, donor)):
        private = source["CFF "].cff[0].Private
        target = rt.FDArray[i].Private
        # CFF compilation omits explicit values equal to specification defaults.
        for key in (private.rawDict.keys() | target.rawDict.keys()) - {"Subrs"}:
            assert getattr(private, key) == getattr(target, key)
        assert len(private.Subrs) == len(target.Subrs)
    # Added glyphs retain donor outlines, programs and spacing too.
    _, added = donor_names(base, donor)
    for source_g, target_g in zip(added, order[len(old_order) :]):
        assert outline(glyphs[id(donor)], source_g) == outline(
            glyphs[id(result)], target_g
        )
        expected_width, bearing = donor["hmtx"][source_g]
        expected_program = program(donor["CFF "].cff[0].CharStrings[source_g]).copy()
        if style == "Italic" and source_g == "zero.taboldstyle":
            expected_width = 500
            expected_program[0] += 2  # repair donor's anomalous tabular advance
        assert (expected_width, bearing) == result["hmtx"][target_g]
        assert expected_program == program(rt.CharStrings[target_g])
    assert donor_cmap.keys() <= result_cmap.keys()
    for key in (1, 16):
        assert result["name"].getDebugName(key) == FAMILY
    assert result["name"].getDebugName(6) == f"{FAMILY}-{style}"
    assert result["head"].macStyle == base["head"].macStyle
    assert result["OS/2"].fsSelection == base["OS/2"].fsSelection
    assert "Reserved Font Names" in result["name"].getDebugName(13)


@pytest.mark.parametrize("style", STYLES)
def test_numerals_smallcaps_and_shaping(style, donor_path):
    path = FONTS / font_file(style)
    donor = TTFont(donor_path)
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
            for item in shape(donor_path, text, "smcp=1,c2sc=1")
        ]
        assert shape(path, text, "smcp=1,c2sc=1") == expected
    # Preserve actual Utopia kerning under the default shaping path.
    for text in ("AV", "To", "Wa", "ffi", "ffl"):
        assert shape(utopia(style), text, "") == shape(path, text, "")


@pytest.mark.parametrize("style", STYLES)
def test_added_glyphs_are_positioned_as_the_donor_positions_them(style, donor_path):
    # Every pair of the donor's letters, not a few witnesses: a donor subtable
    # that settles a pair at zero must still keep a later one from moving it.
    donor, base = TTFont(donor_path), TTFont(utopia(style))
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
            shape_lines(donor_path, pairs, features),
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
                assemble(utopia(style), f, path, style)
            assert path.read_bytes() == (FONTS / path.name).read_bytes()
