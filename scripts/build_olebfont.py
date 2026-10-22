#!/usr/bin/env python3
"""Assemble OLEBFont, the edition's text family, when the image is built.

Where the host provided the four faces of Valkyrie OT, OLEBFont is Valkyrie
untouched, with the superior lowercase letters and the superior colon its
sups feature lacks taken from newpx's npxsups, scaled and raised to Valkyrie's
own superior figures. Otherwise it is Utopia with Utopia-sized, hinted Erewhon
and Erewhon Math additions: Utopia programs and subroutines remain intact,
donor subroutines are expanded before scaling coordinates, width operands and
hint dictionaries by 100/94, and separate CID font dictionaries retain each
source's hint environment. Either way the family is OLEBFont, with the same
features, and the Greek face paired with it is installed beside it.
"""

from __future__ import annotations

import csv
import math
import shutil
import sys
import unicodedata
import zipfile
from argparse import ArgumentParser, Namespace
from collections.abc import Iterator, Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import IO, Any

from font_sources import math_donors, normalized_donor
from fontTools.cffLib import CharStrings, FDArrayIndex, FDSelect, FontDict
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.misc.fixedTools import otRound
from fontTools.misc.psCharStrings import T2CharString
from fontTools.otlLib.builder import buildPairPosGlyphs
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.reorderGlyphs import reorderGlyphs
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable

FAMILY = "OLEBFont"
STYLES = ("Regular", "Italic", "Bold", "BoldItalic")
DIGITS = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
)
SUPERIOR_CODES = (0x00B9, 0x00B2, 0x00B3)
FEATURES = ("onum", "lnum", "pnum", "tnum", "sups", "smcp", "c2sc")
EREWHON_MEMBER = "erewhon/opentype/Erewhon-{}.otf"
# The faces make bootstrap collects from the host, by their PostScript names.
VALKYRIE_FACE = "ValkyrieOTA{}.otf"
NEWPX_MEMBER = "newpx/opentype/npxsups-{}.otf"
# The superior letters the edition sets: verse suffixes and note callers.
SUPERIOR_LETTERS = "abcdefghijklmnopqrstuvwxyz"
# newpx names its superiors .sup; Valkyrie names its superior figures .sups.
DONOR_SUFFIX, SUFFIX = ".sup", ".sups"
# The Greek paired with each base, as its archive names the faces.
DIDOT_FACES = (
    "GFSDidot.otf",
    "GFSDidotItalic.otf",
    "GFSDidotBold.otf",
    "GFSDidotBoldItalic.otf",
)
HERAKLIT_FACES = ("GFSHeraklit.otf",)
# XeTeX takes a font's interword glue from its space advance: the stretch is
# half of it and the shrink a third. Utopia's word space is widened by this
# much, keeping those proportions; Valkyrie's is left as designed.
WORD_SPACE = (6, 5)
# The sidecar beside each face: every slot, its source, and how it was placed.
COLUMNS = (
    "GID",
    "Glyph",
    "Unicode",
    "SourceFont",
    "SourceGlyph",
    "Scale",
    "Raise",
    "Advance",
    "LSB",
)
EPOCH = 2082844800  # 1970-01-01 in the head table's seconds

# Common (left, right) allowances between proportional oldstyle figures, in
# output units. These affect pair positioning, never the glyph advances.
FIGURE_SPACING = {
    "Regular": {
        "zero.oldstyle": (10, 0),
        "one.oldstyle": (15, 15),
        "two.oldstyle": (30, 15),
        "three.oldstyle": (30, 0),
        "six.oldstyle": (30, 0),
        "eight.oldstyle": (30, 0),
        "nine.oldstyle": (0, 25),
    },
    "Italic": {
        "one.oldstyle": (0, 10),
        "two.oldstyle": (20, 0),
        "three.oldstyle": (15, 0),
        "six.oldstyle": (20, 0),
        "eight.oldstyle": (20, 0),
        "nine.oldstyle": (0, 10),
    },
}

# Pair exceptions, added to the common allowances; columns follow STYLES.
# Digit pairs identify the proportional .oldstyle glyphs only.
FIGURE_KERNS = {
    "02": (-20, -30, 0, 0),
    "06": (0, 15, 0, 15),
    "10": (-30, -25, -30, -15),
    "12": (-30, -30, 0, 0),
    "13": (-30, -15, 0, 0),
    "16": (-50, -35, -20, -15),
    "17": (-30, -40, -15, -15),
    "18": (-50, -45, -20, -15),
    "19": (-40, -30, -30, -20),
    "20": (5, 0, 0, 0),
    "26": (20, 0, 0, 0),
    "32": (0, -15, 20, 15),
    "34": (40, 15, 20, 0),
    "38": (0, -20, 0, 0),
    "42": (15, 0, 20, 20),
    "44": (15, 15, 20, 15),
    "49": (-20, -15, -20, -15),
    "54": (20, 0, 0, 0),
    "56": (30, 15, 0, 0),
    "58": (0, -20, 0, 0),
    "59": (-15, -15, -15, -15),
    "60": (20, 15, 0, 15),
    "63": (-15, -15, -15, 0),
    "69": (20, 0, 0, 0),
    "70": (-15, -15, -15, -15),
    "71": (-15, -15, -15, -15),
    "72": (-10, -10, 0, 0),
    "73": (-10, -10, 0, 0),
    "74": (-70, -70, -55, -55),
    "75": (-5, -5, 0, 0),
    "76": (-15, -5, -15, -15),
    "78": (-25, -35, -15, -15),
    "79": (-5, 5, -15, -15),
    "80": (20, 15, 0, 0),
    "86": (-20, -10, 0, 0),
    "87": (10, 0, 0, 0),
    "89": (20, 0, 0, 0),
    "90": (5, 0, 0, 0),
    "91": (-15, -25, -15, -15),
    "93": (-15, -15, -15, -15),
    "94": (-5, -15, -15, -15),
    "95": (-15, -15, -15, -15),
    "96": (-15, 0, 0, 0),
    "97": (-15, -15, -15, -15),
    "98": (-5, 10, 0, 0),
}


def figure_kerns(style: str) -> dict[tuple[str, str], int]:
    # Refuse a misspelled face or figure, and an allowance of nothing.
    assert set(FIGURE_SPACING) <= set(STYLES)
    assert all(
        set(allowances) <= {d + ".oldstyle" for d in DIGITS}
        and all(map(any, allowances.values()))
        for allowances in FIGURE_SPACING.values()
    )
    assert all(
        len(pair) == 2
        and set(pair) <= set("0123456789")
        and len(values) == len(STYLES)
        and any(values)
        for pair, values in FIGURE_KERNS.items()
    )
    spacing, column = FIGURE_SPACING.get(style, {}), STYLES.index(style)
    pairs = {}
    for i, a in enumerate(DIGITS):
        for j, b in enumerate(DIGITS):
            left, right = a + ".oldstyle", b + ".oldstyle"
            value = (
                spacing.get(left, (0, 0))[1]
                + spacing.get(right, (0, 0))[0]
                + FIGURE_KERNS.get(f"{i}{j}", (0, 0, 0, 0))[column]
            )
            if value:
                pairs[left, right] = value
    return pairs


def rename(value: Any, names: Mapping[str, str]) -> Any:
    """Remap glyph references throughout decoded OpenType structures."""
    if isinstance(value, str):
        return names.get(value, value)
    if isinstance(value, list):
        return [rename(v, names) for v in value]
    if isinstance(value, dict):
        return {names.get(k, k): rename(v, names) for k, v in value.items()}
    if hasattr(value, "__dict__"):
        for k, v in vars(value).copy().items():
            # A feature, script, or language tag may spell a glyph's name
            # ("zero" is both the digit and the slashed-zero feature).
            if not k.endswith("Tag"):
                setattr(value, k, rename(v, names))
    return value


def languages(script: Any) -> Iterator[tuple[str | None, Any]]:
    """Each language system present, by tag; the default's tag is None."""
    if script.DefaultLangSys is not None:
        yield None, script.DefaultLangSys
    for r in script.LangSysRecord:
        yield r.LangSysTag, r.LangSys


def union(a: list[int], b: list[int]) -> list[int]:
    return sorted(set(a + b))


def append_layout(base: Any, extra: Any) -> None:
    """Extend each language's features while retaining its original lookups.

    A feature tag can have several records for different language systems.
    Merge only the records active in that language: exposing two active kern
    records makes HarfBuzz choose one and can suppress the original kerning.
    """
    offset = len(base.LookupList.Lookup)
    base.LookupList.Lookup.extend(extra.LookupList.Lookup)
    base.LookupList.LookupCount = len(base.LookupList.Lookup)
    feature_offset = len(base.FeatureList.FeatureRecord)
    records = base.FeatureList.FeatureRecord + extra.FeatureList.FeatureRecord
    for rec in extra.FeatureList.FeatureRecord:
        rec.Feature.LookupListIndex = [n + offset for n in rec.Feature.LookupListIndex]
    for rec in extra.ScriptList.ScriptRecord:
        for _, lang in languages(rec.Script):
            assert lang.ReqFeatureIndex == 65535
            lang.FeatureIndex = [n + feature_offset for n in lang.FeatureIndex]
        existing = next(
            (r for r in base.ScriptList.ScriptRecord if r.ScriptTag == rec.ScriptTag),
            None,
        )
        if existing is None:
            base.ScriptList.ScriptRecord.append(rec)
            continue
        script = existing.Script
        targets = dict(languages(script))
        new_records = {r.LangSysTag: r for r in rec.Script.LangSysRecord}
        # Read the original default before the donor's default joins it below.
        original_default = (
            list(script.DefaultLangSys.FeatureIndex) if None in targets else []
        )
        for tag, lang in languages(rec.Script):
            if tag in targets:
                target = targets[tag]
                target.FeatureIndex = union(target.FeatureIndex, lang.FeatureIndex)
                continue
            # A newly imported language previously used the original
            # script's default features. Retain those original lookups.
            lang.FeatureIndex = union(original_default, lang.FeatureIndex)
            if tag is None:
                script.DefaultLangSys = lang
            else:
                script.LangSysRecord.append(new_records[tag])
        existing.Script.LangSysRecord.sort(key=lambda r: r.LangSysTag)
        existing.Script.LangSysCount = len(existing.Script.LangSysRecord)
    # Canonicalize one feature record per active tag per language. Sharing
    # identical variants keeps tables compact without losing language choices.
    variants: dict[tuple[str, tuple[int, ...]], Any] = {}
    assignments = []
    for rec in base.ScriptList.ScriptRecord:
        for _, lang in languages(rec.Script):
            assert lang.ReqFeatureIndex == 65535
            by_tag: dict[str, list[Any]] = {}
            for i in lang.FeatureIndex:
                feature = records[i]
                by_tag.setdefault(feature.FeatureTag, []).append(feature)
            keys = []
            for tag, group in sorted(by_tag.items()):
                lookups = list(
                    dict.fromkeys(n for r in group for n in r.Feature.LookupListIndex)
                )
                key = tag, tuple(lookups)
                if key not in variants:
                    feature = deepcopy(group[0])
                    feature.Feature.LookupListIndex = lookups
                    feature.Feature.LookupCount = len(lookups)
                    variants[key] = feature
                keys.append(key)
            assignments.append((lang, keys))
    all_keys = sorted(variants)
    indices = {key: i for i, key in enumerate(all_keys)}
    base.FeatureList.FeatureRecord = [variants[key] for key in all_keys]
    base.FeatureList.FeatureCount = len(all_keys)
    for lang, lang_keys in assignments:
        lang.FeatureIndex = [indices[key] for key in lang_keys]
        lang.FeatureCount = len(lang.FeatureIndex)
    base.ScriptList.ScriptRecord.sort(key=lambda r: r.ScriptTag)
    base.ScriptList.ScriptCount = len(base.ScriptList.ScriptRecord)


def donor_positioning(
    donor: TTFont,
    names: Mapping[str, str],
    original: set[str],
    inventory: Sequence[str],
) -> Any:
    """Keep donor pair adjustments only where at least one glyph was added."""
    table = rename(deepcopy(donor["GPOS"].table), names)
    glyph_ids = {g: i for i, g in enumerate(inventory)}
    for lookup in table.LookupList.Lookup:
        if lookup.LookupType in (4, 6):
            # Every combining mark in the pinned donor is added. Consequently
            # these attachments cannot alter an original-to-original pair.
            for st in lookup.SubTable:
                marks = st.MarkCoverage if lookup.LookupType == 4 else st.Mark1Coverage
                assert not (set(marks.glyphs) & original)
            continue
        assert lookup.LookupType == 2 and lookup.LookupFlag == 0
        # The first subtable that covers a pair decides it, even at zero. A
        # glyph subtable covers the pairs it lists; a class subtable covers
        # every pair whose left glyph it lists, so no later subtable is read
        # for that glyph. Flattened pairs have no such order: keep each pair's
        # deciding value only.
        subtables = []
        decided: set[tuple[str, str]] = set()
        closed: set[str] = set()
        for st in lookup.SubTable:
            pairs = {}
            if st.Format == 1:
                for left, pairset in zip(st.Coverage.glyphs, st.PairSet):
                    if left in closed:
                        continue
                    for pair in pairset.PairValueRecord:
                        key = left, pair.SecondGlyph
                        if key in decided:
                            continue
                        decided.add(key)
                        if left not in original or pair.SecondGlyph not in original:
                            pairs[key] = (pair.Value1, pair.Value2)
            else:
                assert st.Format == 2
                # Most class pairs are zero: find each row's adjusting
                # classes once instead of testing every glyph pair's cell.
                right_classes = [
                    (g, st.ClassDef2.classDefs.get(g, 0)) for g in inventory
                ]
                adjusting = [
                    {
                        i
                        for i, cell in enumerate(row.Class2Record)
                        if any(
                            v and any(vars(v).values())
                            for v in (cell.Value1, cell.Value2)
                        )
                    }
                    for row in st.Class1Record
                ]
                for left in st.Coverage.glyphs:
                    if left in closed:
                        continue
                    class1 = st.ClassDef1.classDefs.get(left, 0)
                    cells = st.Class1Record[class1].Class2Record
                    for right, class2 in right_classes:
                        if (
                            class2 in adjusting[class1]
                            and (left, right) not in decided
                            and not (left in original and right in original)
                        ):
                            cell = cells[class2]
                            pairs[left, right] = (cell.Value1, cell.Value2)
                closed.update(st.Coverage.glyphs)
            subtables.extend(buildPairPosGlyphs(pairs, glyph_ids))
        lookup.SubTable = subtables
        lookup.SubTableCount = len(subtables)
    return table


def figure_positioning(
    style: str, names: Mapping[str, str], inventory: Sequence[str]
) -> Any:
    pairs = figure_kerns(style)
    fea = "languagesystem DFLT dflt;\nlanguagesystem latn dflt;\nfeature kern {\n"
    fea += "".join(
        f" pos {names[left]} {names[right]} {value};\n"
        for (left, right), value in pairs.items()
    )
    fea += "} kern;\n"
    extra = TTFont()
    extra.setGlyphOrder(list(inventory))
    addOpenTypeFeaturesFromString(extra, fea)
    return extra["GPOS"].table


def feature_mapping(font: TTFont, tag: str) -> dict[str, str]:
    """The single substitutions a font's feature makes, by source glyph."""
    table = font["GSUB"].table
    mapping: dict[str, str] = {}
    for rec in table.FeatureList.FeatureRecord:
        if rec.FeatureTag != tag:
            continue
        for i in rec.Feature.LookupListIndex:
            lookup = table.LookupList.Lookup[i]
            assert lookup.LookupType == 1
            for st in lookup.SubTable:
                mapping.update(st.mapping)
    return mapping


def substitution_layout(
    inventory: Sequence[str],
    mappings: Mapping[str, Mapping[str, str | Sequence[str]]],
) -> Any:
    """A GSUB table of substitutions, one feature per tag: a glyph by one
    glyph, or, where the target is a sequence, by several."""
    fea = "languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n"
    for tag, mapping in mappings.items():
        fea += f"feature {tag} {{\n"
        fea += "".join(
            f" sub {a} by {b if isinstance(b, str) else ' '.join(b)};\n"
            for a, b in sorted(mapping.items())
            if a != b
        )
        fea += f"}} {tag};\n"
    extra = TTFont()
    extra.setGlyphOrder(list(inventory))
    addOpenTypeFeaturesFromString(extra, fea)
    return extra["GSUB"].table


def substitutions(base: TTFont, donor: TTFont, names: Mapping[str, str]) -> None:
    """Rebuild numeral transitions and retain the donor's small-cap mappings.

    Explicit four-way transitions fix donor omissions (notably oldstyle one
    and regular-face lining six). Superscripts accept every numeral form, so
    inherited onum/pnum cannot break verse or note-origin figures.
    """
    mappings: dict[str, dict[str, str]] = {tag: {} for tag in FEATURES}
    for tag in ("smcp", "c2sc", "sups"):
        mappings[tag].update(
            {names[a]: names[b] for a, b in feature_mapping(donor, tag).items()}
        )
    for digit in DIGITS:
        tab = names[digit]
        prop, old, tabold, superior = (
            names[digit + suffix]
            for suffix in (".prop", ".oldstyle", ".taboldstyle", ".superior")
        )
        mappings["onum"].update({tab: tabold, prop: old})
        mappings["lnum"].update({tabold: tab, old: prop})
        mappings["pnum"].update({tab: prop, tabold: old})
        mappings["tnum"].update({prop: tab, old: tabold})
        mappings["sups"].update({g: superior for g in (tab, prop, old, tabold)})
    table = base["GSUB"].table
    original_count = len(table.LookupList.Lookup)
    assert all(l.LookupType == 4 for l in table.LookupList.Lookup)
    append_layout(table, substitution_layout(base.getGlyphOrder(), mappings))
    # Small-cap conversion must precede ordinary ligatures: otherwise "ffi"
    # in words such as "office" survives at full size. Original liga lookup
    # data remain intact and still shape ordinary text when smcp is disabled.
    added = len(table.LookupList.Lookup) - original_count
    table.LookupList.Lookup = (
        table.LookupList.Lookup[original_count:]
        + table.LookupList.Lookup[:original_count]
    )
    for rec in table.FeatureList.FeatureRecord:
        rec.Feature.LookupListIndex = [
            i + added if i < original_count else i - original_count
            for i in rec.Feature.LookupListIndex
        ]


def donor_names(base: TTFont, donor: TTFont) -> tuple[dict[str, str], list[str]]:
    """Map donor glyphs onto the base's names; list those the base lacks."""
    cmap = base.getBestCmap()
    names = {g: g for g in donor.getGlyphOrder()}
    for code, g in donor.getBestCmap().items():
        if code in cmap:
            names[g] = cmap[code]
    original = set(base.getGlyphOrder())
    return names, [g for g in donor.getGlyphOrder() if names[g] not in original]


def font_file(style: str) -> str:
    """A face's file, named as its PostScript name."""
    return f"{FAMILY}-{style}.otf"


def style_name(style: str) -> str:
    return {"BoldItalic": "Bold Italic"}.get(style, style)


def widened_space(cs: T2CharString, width: int, private: Any) -> T2CharString:
    """The space's charstring with its advance operand set to the widened
    width: the program is the advance and endchar, or endchar alone when the
    advance was the dictionary's default."""
    cs.decompile()
    program = cs.program
    assert program == ["endchar"] or (
        len(program) == 2
        and isinstance(program[0], (int, float))
        and program[1] == "endchar"
    ), program
    return T2CharString(
        program=[width - private.nominalWidthX, "endchar"],
        private=private,
        globalSubrs=cs.globalSubrs,
    )


def unicode_columns(cmap: Mapping[int, str]) -> dict[str, str]:
    """Each glyph's code points, as the sidecar lists them."""
    codes: dict[str, list[str]] = {}
    for code, name in sorted(cmap.items()):
        codes.setdefault(name, []).append(f"U+{code:04X}")
    return {name: " ".join(values) for name, values in codes.items()}


def write_face(base: TTFont, output: Path, rows: Sequence[Sequence[Any]]) -> None:
    """Save a face with its sidecar, and read it back whole to catch a
    dangling glyph, hint, or layout reference now."""
    base["head"].created = base["head"].modified = EPOCH
    if "FFTM" in base:
        del base["FFTM"]
    base.save(output)
    with output.with_suffix(".glyphs.csv").open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    check = TTFont(output, recalcTimestamp=False)
    for tag in check.keys():
        check[tag]
    for g in check.getGlyphSet().values():
        g.draw(RecordingPen())


def assemble_utopia(
    utopia_path: str | Path,
    donor_path: str | Path | IO[bytes],
    output: Path,
    style: str,
    math_archive: str | Path,
) -> tuple[int, int]:
    base = TTFont(utopia_path, recalcTimestamp=False)
    donor = normalized_donor(TTFont(donor_path, recalcTimestamp=False), style)
    assert base["head"].unitsPerEm == donor["head"].unitsPerEm == 1000
    original = set(base.getGlyphOrder())
    cmap = base.getBestCmap().copy()
    donor_cmap = donor.getBestCmap()
    # The sole Utopia replacement: use Erewhon for encoded superscript 1/2/3
    # as well as sups, so the entire figure set has one designed size/position.
    replacements = {cmap[c]: donor_cmap[c] for c in SUPERIOR_CODES}
    names, added = donor_names(base, donor)
    assert len({names[g] for g in added}) == len(added)
    inventory = base.getGlyphOrder() + [names[g] for g in added]
    base.setGlyphOrder(inventory)
    base["hmtx"].metrics.update({names[g]: donor["hmtx"].metrics[g] for g in added})
    base["hmtx"].metrics.update(
        {g: donor["hmtx"].metrics[d] for g, d in replacements.items()}
    )
    # Utopia's word space, 225 units (210 in the bold faces), becomes 270
    # (252): what config/word-spacing.tex used to do to the glue at typesetting.
    space = cmap[0x20]
    space_width, space_bearing = base["hmtx"].metrics[space]
    space_width = space_width * WORD_SPACE[0] // WORD_SPACE[1]
    base["hmtx"].metrics[space] = space_width, space_bearing
    cmap.update({code: names[g] for code, g in donor_cmap.items() if code not in cmap})
    substitutions(base, donor, names)
    # Before the donor's layout: the Latin languages it imports then inherit
    # these pairs with the rest of the default's kerning.
    append_layout(base["GPOS"].table, figure_positioning(style, names, inventory))
    append_layout(
        base["GPOS"].table, donor_positioning(donor, names, original, inventory)
    )
    # Retain original ligature carets and classes. Donor classes/attachments
    # govern only added glyphs; donor marks have no original equivalents.
    gd = base["GDEF"].table
    dg = rename(deepcopy(donor["GDEF"].table), names)
    for key in ("GlyphClassDef", "MarkAttachClassDef"):
        old, new = getattr(gd, key), getattr(dg, key)
        if old is None:
            setattr(gd, key, new)
        elif new is not None:
            old.classDefs.update(
                {g: v for g, v in new.classDefs.items() if g not in original}
            )
    assert dg.AttachList is None
    if dg.LigCaretList is not None:
        extra = [
            (g, caret)
            for g, caret in zip(
                dg.LigCaretList.Coverage.glyphs, dg.LigCaretList.LigGlyph
            )
            if g not in original
        ]
        gd.LigCaretList.Coverage.glyphs.extend(g for g, _ in extra)
        gd.LigCaretList.LigGlyph.extend(c for _, c in extra)
        gd.LigCaretList.LigGlyphCount = len(gd.LigCaretList.LigGlyph)

    sources = [base["CFF "].cff[0], donor["CFF "].cff[0]]
    donor_source = {names[g]: (1, g) for g in added}
    donor_source.update({g: (1, d) for g, d in replacements.items()})
    math_added = 0
    math_names: dict[str, str] = {}
    # Normalization copies each face; the originals keep their names and notices.
    raw_maths = math_donors(math_archive, style)
    for index, raw_math in enumerate(raw_maths, 2):
        extra = normalized_donor(raw_math)
        old = set(inventory)
        mapping = {g: f"math{index}.{g}" for g in extra.getGlyphOrder()}
        mapping[".notdef"] = ".notdef"
        for g in mapping:
            if g in math_names:
                mapping[g] = math_names[g]
        for code, g in extra.getBestCmap().items():
            # Private-use numbers have font-local meanings. Erewhon's PUA
            # small caps must not replace unrelated Math construction pieces.
            if code in cmap and unicodedata.category(chr(code)) != "Co":
                mapping[g] = cmap[code]
        math_names.update(
            {g: target for g, target in mapping.items() if g not in math_names}
        )
        new = [g for g in extra.getGlyphOrder() if mapping[g] not in old]
        inventory.extend(mapping[g] for g in new)
        base.setGlyphOrder(inventory)
        base["hmtx"].metrics.update({mapping[g]: extra["hmtx"][g] for g in new})
        cmap.update(
            {c: mapping[g] for c, g in extra.getBestCmap().items() if c not in cmap}
        )
        donor_source.update({mapping[g]: (index, g) for g in new})
        sources.append(extra["CFF "].cff[0])
        math_added += len(new)
        # Only added inputs acquire math alternates; existing text features win.
        layout = rename(deepcopy(extra["GSUB"].table), mapping)
        for lookup in layout.LookupList.Lookup:
            for st in lookup.SubTable:
                if lookup.LookupType == 1:
                    st.mapping = {a: b for a, b in st.mapping.items() if a not in old}
                else:
                    assert lookup.LookupType == 3
                    st.alternates = {
                        a: b for a, b in st.alternates.items() if a not in old
                    }
        append_layout(base["GSUB"].table, layout)
        append_layout(
            base["GPOS"].table, donor_positioning(extra, mapping, old, inventory)
        )
        classes = extra["GDEF"].table.GlyphClassDef
        if classes is not None:
            gd.GlyphClassDef.classDefs.update(
                {
                    mapping[g]: v
                    for g, v in classes.classDefs.items()
                    if mapping[g] not in old
                }
            )
    # Format 4 cannot encode the supplementary mathematical alphabets. Keep
    # the legacy map and write complete Unicode maps for both BMP and UCS-4.
    for table in base["cmap"].tables:
        if table.isUnicode():
            table.cmap = {c: g for c, g in cmap.items() if c <= 0xFFFF}
    if max(cmap) > 0xFFFF:
        for platform, encoding in ((0, 4), (3, 10)):
            table = CmapSubtable.newSubtable(12)
            table.platformID, table.platEncID, table.language = platform, encoding, 0
            table.cmap = cmap.copy()
            base["cmap"].tables.append(table)

    cff = base["CFF "].cff
    top = cff[0]
    assert all(not len(source.GlobalSubrs) for source in sources)
    fdarray = FDArrayIndex()
    fdarray.strings = cff.strings
    fdarray.GlobalSubrs = cff.GlobalSubrs
    for i, source in enumerate(sources):
        fd = FontDict(strings=cff.strings, GlobalSubrs=cff.GlobalSubrs)
        fd.Private = source.Private
        fd.FontName = f"{FAMILY}-{style}-FD{i}"
        fdarray.append(fd)
    select = FDSelect(format=3)
    select.gidArray = [donor_source.get(g, (0, g))[0] for g in inventory]
    chars = CharStrings(None, inventory, cff.GlobalSubrs, None, select, fdarray)
    bounds = BoundsPen(None)
    for g, fd_index in zip(inventory, select.gidArray):
        _, source_g = donor_source.get(g, (0, g))
        cs = sources[fd_index].CharStrings[source_g]
        if g == space:
            cs = widened_space(cs, space_width, sources[0].Private)
        # seac composites cannot be represented in a CID charset. These pinned
        # fonts express their components through preserved local subroutines.
        pen = RecordingPen()
        cs.draw(pen)
        assert not any(op == "addComponent" for op, _ in pen.value), (style, g)
        pen.replay(bounds)
        cs.fdSelectIndex = fd_index
        chars[g] = cs
    top.CharStrings = chars
    top.FDArray, top.FDSelect = fdarray, select
    top.ROS = ("Adobe", "Identity", 0)
    top.CIDCount = len(inventory)
    del top.Private
    top.rawDict.pop("Private", None)
    if hasattr(top, "Encoding"):
        del top.Encoding
    top.rawDict.pop("Encoding", None)
    # CID names are serialized by CFF; remap all layout/cmap references once.
    cid = {g: ".notdef" if i == 0 else f"cid{i:05d}" for i, g in enumerate(inventory)}
    top.charset = [cid[g] for g in inventory]
    chars.charStrings = {cid[g]: cs for g, cs in chars.charStrings.items()}
    for tag in ("GSUB", "GPOS", "GDEF"):
        rename(base[tag].table, cid)
    for table in base["cmap"].tables:
        table.cmap = {code: cid[g] for code, g in table.cmap.items()}
    base["hmtx"].metrics = {cid[g]: v for g, v in base["hmtx"].metrics.items()}
    base.setGlyphOrder(top.charset)
    base["post"].formatType = 3.0
    # Utopia's vertical metrics stay authoritative, win metrics included: Math's
    # extensible delimiters would otherwise set the line height. Only the
    # bounding box grows to encompass additions.
    xmin, ymin, xmax, ymax = bounds.bounds
    top.FontBBox = [
        math.floor(xmin),
        math.floor(ymin),
        math.ceil(xmax),
        math.ceil(ymax),
    ]
    base["OS/2"].usFirstCharIndex, base["OS/2"].usLastCharIndex = min(cmap), min(
        max(cmap), 65535
    )
    base["OS/2"].recalcUnicodeRanges(base)
    base["OS/2"].recalcCodePageRanges(base)
    # Preserve legal notices while removing source family identification.
    legal = "\n\n".join(
        dict.fromkeys(
            n.toUnicode()
            for f in (base, donor, *raw_maths)
            for n in f["name"].names
            if n.nameID in (0, 7, 13)
        )
    )
    legal += f"\n\nReserved Font Names: Heuristica (Andrey V. Panov); Erewhon (Michael J. Sharpe).\n{FAMILY} additions are distributed under the SIL Open Font License 1.1; see OFL.txt. Adobe/TUG sublicensing notice: see Adobe-TUG-Utopia-LICENSE.txt."
    values = {
        0: legal,
        1: FAMILY,
        2: style_name(style),
        3: f"{FAMILY}-{style};1.000",
        4: f"{FAMILY} {style_name(style)}",
        5: "Version 1.000",
        6: f"{FAMILY}-{style}",
        7: legal,
        8: "Adobe Systems Incorporated; Michael Sharpe; OLEB",
        9: "Adobe Systems Incorporated; Michael Sharpe and Erewhon contributors",
        10: "Utopia with normalized Erewhon and Erewhon Math additions; assembled for the Orthodox Liturgical English Bible.",
        13: legal,
        14: "https://tug.org/fonts/utopia/",
        16: FAMILY,
        17: style_name(style),
    }
    base["name"].names = []
    for name_id, value in values.items():
        base["name"].setName(value, name_id, 3, 1, 0x409)
    cff.fontNames = [f"{FAMILY}-{style}"]
    top.FamilyName, top.FullName = FAMILY, f"{FAMILY} {style_name(style)}"
    top.Notice = legal
    top.version = "1.000"
    reorderGlyphs(base, base.getGlyphOrder())
    # Preserve readable names and provenance beside the CID font.
    codes = unicode_columns(cmap)
    labels = [f"Utopia-{style}", f"Erewhon-{style}"]
    labels.extend(f["name"].getDebugName(6) for f in raw_maths)
    rows = []
    for i, name in enumerate(inventory):
        index, source_g = donor_source.get(name, (0, name))
        rows.append(
            (
                i,
                cid[name],
                codes.get(name, ""),
                labels[index],
                source_g,
                "1" if index == 0 else "100/94",
                "0",
                *base["hmtx"][cid[name]],
            )
        )
    write_face(base, output, rows)
    return len(original), len(added) + math_added


def ink(glyphs: Any, name: str) -> tuple[float, float, float, float]:
    """A glyph's ink bounds: xmin, ymin, xmax, ymax."""
    pen = BoundsPen(glyphs)
    glyphs[name].draw(pen)
    assert pen.bounds is not None, name
    x0, y0, x1, y1 = pen.bounds
    return x0, y0, x1, y1


def superior_placements(
    base: TTFont, donor: TTFont
) -> dict[str, tuple[str, float, float]]:
    """Where each donor superior goes, as (donor glyph, scale, raise): one
    transform for all of them, which lays the donor's superior figure box on
    the base's, measured on the superior one of each (flat-topped, without
    overshoot), so that each letter and the colon stand to the base's figures
    as they stand to the donor's own: the same x-height, capital height and
    baseline in proportion. Nothing is stretched or placed by hand."""
    _, bottom, _, top = ink(base.getGlyphSet(), "one" + SUFFIX)
    _, donor_bottom, _, donor_top = ink(donor.getGlyphSet(), "one" + DONOR_SUFFIX)
    scale = (top - bottom) / (donor_top - donor_bottom)
    raise_ = bottom - donor_bottom * scale
    return {
        glyph + SUFFIX: (glyph + DONOR_SUFFIX, scale, raise_)
        for glyph in (*SUPERIOR_LETTERS, "colon")
    }


def ligatures(font: TTFont, tag: str) -> dict[str, list[str]]:
    """The ligatures a font's feature forms, each by its components."""
    table = font["GSUB"].table
    formed: dict[str, list[str]] = {}
    for rec in table.FeatureList.FeatureRecord:
        if rec.FeatureTag != tag:
            continue
        for i in rec.Feature.LookupListIndex:
            lookup = table.LookupList.Lookup[i]
            assert lookup.LookupType == 4
            for st in lookup.SubTable:
                for first, entries in st.ligatures.items():
                    for entry in entries:
                        formed[entry.LigGlyph] = [first, *entry.Component]
    return formed


def superior_substitutions(
    base: TTFont, added: Sequence[str]
) -> dict[str, str | Sequence[str]]:
    """What sups must also map: each added superior from its letter or colon;
    the ligatures the font forms of those letters first (fi, fl), each by its
    letters' superiors, since the added lookup runs after the ligatures'; and
    every form of a figure the font's own sups leaves out (its oldstyle,
    tabular and tall figures), so that onum and pnum cannot keep a verse
    number from its superior."""
    mapping: dict[str, str | Sequence[str]] = {g.removesuffix(SUFFIX): g for g in added}
    for ligature, components in ligatures(base, "liga").items():
        if all(c in mapping for c in components):
            mapping[ligature] = [c + SUFFIX for c in components]
    existing = feature_mapping(base, "sups")
    for g in base.getGlyphOrder():
        stem, _, suffix = g.partition(".")
        parts = suffix.split(".") if suffix else []
        if (
            stem in DIGITS
            and g not in existing
            and not {"sups", "subs", "numr", "dnom"} & set(parts)
        ):
            target = f"{stem}.smcp{SUFFIX}" if "smcp" in parts else stem + SUFFIX
            assert target in existing.values(), target
            mapping[g] = target
    return mapping


def assemble_valkyrie(
    valkyrie_path: str | Path,
    donor_path: str | Path | IO[bytes],
    output: Path,
    style: str,
) -> tuple[int, int]:
    base = TTFont(valkyrie_path, recalcTimestamp=False)
    donor = TTFont(donor_path, recalcTimestamp=False)
    assert base["head"].unitsPerEm == donor["head"].unitsPerEm == 1000
    original = base.getGlyphOrder()
    placements = superior_placements(base, donor)
    assert not set(placements) & set(original)
    inventory = original + list(placements)
    cff = base["CFF "].cff
    top = cff[0]
    private = top.Private
    chars = CharStrings(None, inventory, cff.GlobalSubrs, private, None, None)
    for g in original:
        chars[g] = top.CharStrings[g]
    donor_glyphs = donor.getGlyphSet()
    for g, (source_g, scale, dy) in placements.items():
        width = otRound(donor["hmtx"][source_g][0] * scale)
        outline = RecordingPen()
        donor_glyphs[source_g].draw(TransformPen(outline, (scale, 0, 0, scale, 0, dy)))
        # The pen writes the operand as given: the advance less the nominal.
        pen = T2CharStringPen(width - private.nominalWidthX, None)
        outline.replay(pen)
        chars[g] = pen.getCharString(private, cff.GlobalSubrs)
        # The side bearing of the glyph as written, which the pen rounded.
        bounds = BoundsPen(None)
        chars[g].draw(bounds)
        base["hmtx"].metrics[g] = width, otRound(bounds.bounds[0])
    top.CharStrings = chars
    top.charset = inventory
    base.setGlyphOrder(inventory)
    # Valkyrie has no GDEF: every glyph is a base glyph, the added ones too.
    assert "GDEF" not in base
    append_layout(
        base["GSUB"].table,
        substitution_layout(
            inventory, {"sups": superior_substitutions(base, list(placements))}
        ),
    )
    # Valkyrie's own notices stay, as its licence requires; the donor's joins
    # them, and the family takes the edition's name.
    name = base["name"]
    donor_notice = donor["name"].getDebugName(0)
    values = {
        1: FAMILY,
        2: style_name(style),
        3: f"{FAMILY}-{style}",
        4: f"{FAMILY} {style_name(style)}",
        6: f"{FAMILY}-{style}",
        10: "Valkyrie OT with superior letters and a superior colon from newpx's npxsups, scaled to its superior figures; assembled for the Orthodox Liturgical English Bible.",
        13: f"{name.getDebugName(13)}\n\nSuperior letters and colon: {donor_notice}",
        16: FAMILY,
        17: style_name(style),
    }
    name.names = [n for n in name.names if n.nameID not in values]
    for name_id, value in values.items():
        name.setName(value, name_id, 3, 1, 0x409)
    cff.fontNames = [f"{FAMILY}-{style}"]
    top.FamilyName, top.FullName = FAMILY, f"{FAMILY} {style_name(style)}"
    notice = getattr(top, "Notice", None) or name.getDebugName(0)
    top.Notice = f"{notice}. Superior letters and colon: {donor_notice}"
    codes = unicode_columns(base.getBestCmap())
    rows: list[tuple[Any, ...]] = [
        (i, g, codes.get(g, ""), f"ValkyrieOTA{style}", g, "1", "0", *base["hmtx"][g])
        for i, g in enumerate(original)
    ]
    rows.extend(
        (
            i,
            g,
            "",
            f"npxsups-{style}",
            source_g,
            repr(scale),
            repr(dy),
            *base["hmtx"][g],
        )
        for i, (g, (source_g, scale, dy)) in enumerate(
            placements.items(), len(original)
        )
    )
    write_face(base, output, rows)
    return len(original), len(placements)


def install_greek(archive: Path, members: Sequence[str], output: Path) -> None:
    """The Greek faces, copied from their archive as they are."""
    with zipfile.ZipFile(archive) as z:
        for member in members:
            (output / member).write_bytes(z.read(member))


def build_utopia(args: Namespace, fonts: Path) -> None:
    with zipfile.ZipFile(args.erewhon) as archive:
        for style in STYLES:
            target = fonts / font_file(style)
            with archive.open(EREWHON_MEMBER.format(style)) as source:
                original, added = assemble_utopia(
                    args.utopia / "dist" / f"Utopia-{style}.otf",
                    source,
                    target,
                    style,
                    args.erewhon_math,
                )
            print(
                f"{target.name}: {original} Utopia slots (three superscripts replaced), {added} normalized Erewhon / Math additions"
            )
        (fonts / "OFL.txt").write_bytes(archive.read("erewhon/doc/OFL.txt"))
    with zipfile.ZipFile(args.erewhon_math) as archive:
        (fonts / "Erewhon-Math-README.md").write_bytes(
            archive.read("erewhon-math/README.md")
        )
    shutil.copyfile(args.utopia / "COPYING", fonts / "Adobe-Utopia-COPYING.txt")
    for name in ("OLEBFont-NOTICE.txt", "Adobe-TUG-Utopia-LICENSE.txt"):
        shutil.copyfile(Path(__file__).with_name(name), fonts / name)


def build_valkyrie(args: Namespace, fonts: Path) -> None:
    with zipfile.ZipFile(args.newpx) as archive:
        for style in STYLES:
            target = fonts / font_file(style)
            with archive.open(NEWPX_MEMBER.format(style)) as source:
                original, added = assemble_valkyrie(
                    args.valkyrie / VALKYRIE_FACE.format(style), source, target, style
                )
            print(
                f"{target.name}: {original} Valkyrie glyphs, {added} npxsups superiors"
            )
        (fonts / "MANIFEST-newpx.txt").write_bytes(
            archive.read("newpx/doc/MANIFEST-newpx.txt")
        )
    shutil.copyfile(
        Path(__file__).with_name("OLEBFont-Valkyrie-NOTICE.txt"),
        fonts / "OLEBFont-NOTICE.txt",
    )


def install_chapter(archive: Path, output: Path) -> None:
    """Install newpx's original upright text face and its licensing notices."""
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for member in (
            "newpx/opentype/TeXGyrePagellaX-Regular.otf",
            "newpx/doc/MANIFEST-newpx.txt",
            "newpx/README",
        ):
            (output / Path(member).name).write_bytes(z.read(member))


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--utopia", type=Path, required=True)
    parser.add_argument("--valkyrie", type=Path, required=True)
    parser.add_argument("--erewhon", type=Path, required=True)
    parser.add_argument("--erewhon-math", type=Path, required=True)
    parser.add_argument("--newpx", type=Path, required=True)
    parser.add_argument("--gfs-didot", type=Path, required=True)
    parser.add_argument("--gfs-heraklit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fonts, greek = args.output / "olebfont", args.output / "greek"
    for directory in (fonts, greek):
        directory.mkdir(parents=True, exist_ok=True)
    provided = sorted(p.name for p in args.valkyrie.glob("*.otf"))
    expected = sorted(VALKYRIE_FACE.format(style) for style in STYLES)
    if provided == expected:
        build_valkyrie(args, fonts)
        install_chapter(args.newpx, args.output / "chapter")
        install_greek(args.gfs_heraklit, HERAKLIT_FACES, greek)
        print(f"{FAMILY} assembled from Valkyrie OT, with GFS Heraklit for Greek")
    elif not provided:
        build_utopia(args, fonts)
        install_greek(args.gfs_didot, DIDOT_FACES, greek)
        print(f"{FAMILY} assembled from Utopia, with GFS Didot for Greek")
    else:
        sys.exit(
            f"Incomplete Valkyrie OT in {args.valkyrie}: found {provided}, "
            f"need all of {expected} or none. Run make bootstrap again after "
            "installing all four faces, or none."
        )


if __name__ == "__main__":
    main()
