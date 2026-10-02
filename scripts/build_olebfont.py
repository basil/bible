#!/usr/bin/env python3
"""Assemble OLEBFont with Utopia-sized, hinted Erewhon and Math additions.

Utopia programs and subroutines remain intact. Donor subroutines are expanded
before scaling coordinates, width operands and hint dictionaries by 100/94.
Separate CID font dictionaries retain each source's hint environment.
"""

import csv
import math
import shutil
import unicodedata
import zipfile
from argparse import ArgumentParser
from copy import deepcopy
from pathlib import Path

from font_sources import math_donors, normalized_donor
from fontTools.cffLib import CharStrings, FDArrayIndex, FDSelect, FontDict
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.otlLib.builder import buildPairPosGlyphs
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
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


def rename(value, names):
    """Remap glyph references throughout decoded OpenType structures."""
    if isinstance(value, str):
        return names.get(value, value)
    if isinstance(value, list):
        return [rename(v, names) for v in value]
    if isinstance(value, dict):
        return {names.get(k, k): rename(v, names) for k, v in value.items()}
    if hasattr(value, "__dict__"):
        for k, v in vars(value).copy().items():
            # A feature, script or language tag may spell a glyph's name
            # ("zero" is both the digit and the slashed-zero feature).
            if not k.endswith("Tag"):
                setattr(value, k, rename(v, names))
    return value


def languages(script):
    """Each language system present, by tag; the default's tag is None."""
    if script.DefaultLangSys is not None:
        yield None, script.DefaultLangSys
    for r in script.LangSysRecord:
        yield r.LangSysTag, r.LangSys


def union(a, b):
    return sorted(set(a + b))


def append_layout(base, extra):
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
    variants = {}
    assignments = []
    for rec in base.ScriptList.ScriptRecord:
        for _, lang in languages(rec.Script):
            assert lang.ReqFeatureIndex == 65535
            by_tag = {}
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
    keys = sorted(variants)
    indices = {key: i for i, key in enumerate(keys)}
    base.FeatureList.FeatureRecord = [variants[key] for key in keys]
    base.FeatureList.FeatureCount = len(keys)
    for lang, lang_keys in assignments:
        lang.FeatureIndex = [indices[key] for key in lang_keys]
        lang.FeatureCount = len(lang.FeatureIndex)
    base.ScriptList.ScriptRecord.sort(key=lambda r: r.ScriptTag)
    base.ScriptList.ScriptCount = len(base.ScriptList.ScriptRecord)


def donor_positioning(donor, names, original, inventory):
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
        decided, closed = set(), set()
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


def substitutions(base, donor, names):
    """Rebuild numeral transitions and retain the donor's small-cap mappings.

    Explicit four-way transitions fix donor omissions (notably oldstyle one
    and regular-face lining six). Superscripts accept every numeral form, so
    inherited onum/pnum cannot break verse or note-origin figures.
    """
    mappings = {tag: {} for tag in FEATURES}
    for rec in donor["GSUB"].table.FeatureList.FeatureRecord:
        if rec.FeatureTag not in ("smcp", "c2sc", "sups"):
            continue
        for i in rec.Feature.LookupListIndex:
            lookup = donor["GSUB"].table.LookupList.Lookup[i]
            assert lookup.LookupType == 1
            for st in lookup.SubTable:
                mappings[rec.FeatureTag].update(
                    {names[a]: names[b] for a, b in st.mapping.items()}
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
    fea = "languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n"
    for tag in FEATURES:
        fea += f"feature {tag} {{\n"
        fea += "".join(
            f" sub {a} by {b};\n" for a, b in sorted(mappings[tag].items()) if a != b
        )
        fea += f"}} {tag};\n"
    extra = TTFont()
    extra.setGlyphOrder(base.getGlyphOrder())
    addOpenTypeFeaturesFromString(extra, fea)
    table = base["GSUB"].table
    original_count = len(table.LookupList.Lookup)
    assert all(l.LookupType == 4 for l in table.LookupList.Lookup)
    append_layout(table, extra["GSUB"].table)
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


def donor_names(base, donor):
    """Map donor glyphs onto the base's names; list those the base lacks."""
    cmap = base.getBestCmap()
    names = {g: g for g in donor.getGlyphOrder()}
    for code, g in donor.getBestCmap().items():
        if code in cmap:
            names[g] = cmap[code]
    original = set(base.getGlyphOrder())
    return names, [g for g in donor.getGlyphOrder() if names[g] not in original]


def font_file(style):
    """A face's file, named as its PostScript name."""
    return f"{FAMILY}-{style}.otf"


def assemble(utopia_path, donor_path, output, style, math_archive):
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
    cmap.update({code: names[g] for code, g in donor_cmap.items() if code not in cmap})
    substitutions(base, donor, names)
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
    math_names = {}
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
    style_name = {"BoldItalic": "Bold Italic"}.get(style, style)
    values = {
        0: legal,
        1: FAMILY,
        2: style_name,
        3: f"{FAMILY}-{style};1.000",
        4: f"{FAMILY} {style_name}",
        5: "Version 1.000",
        6: f"{FAMILY}-{style}",
        7: legal,
        8: "Adobe Systems Incorporated; Michael Sharpe; OLEB",
        9: "Adobe Systems Incorporated; Michael Sharpe and Erewhon contributors",
        10: "Utopia with normalized Erewhon and Erewhon Math additions; assembled for the Orthodox Liturgical English Bible.",
        13: legal,
        14: "https://tug.org/fonts/utopia/",
        16: FAMILY,
        17: style_name,
    }
    base["name"].names = []
    for key, value in values.items():
        base["name"].setName(value, key, 3, 1, 0x409)
    cff.fontNames = [f"{FAMILY}-{style}"]
    top.FamilyName, top.FullName = FAMILY, f"{FAMILY} {style_name}"
    top.Notice = legal
    top.version = "1.000"
    base["head"].created = base["head"].modified = 2082844800  # 1970-01-01
    if "FFTM" in base:
        del base["FFTM"]
    reorderGlyphs(base, base.getGlyphOrder())
    base.save(output)
    # Preserve readable names and provenance beside the CID font.
    codes = {}
    for code, name in cmap.items():
        codes.setdefault(name, []).append(f"U+{code:04X}")
    labels = [f"Utopia-{style}", f"Erewhon-{style}"]
    labels.extend(f["name"].getDebugName(6) for f in raw_maths)
    with Path(output).with_suffix(".glyphs.csv").open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            (
                "GID",
                "Glyph",
                "Unicode",
                "SourceFont",
                "SourceGlyph",
                "SizeType",
                "ScaleToUtopia",
                "Advance",
                "LSB",
            )
        )
        for i, name in enumerate(inventory):
            index, source_g = donor_source.get(name, (0, name))
            writer.writerow(
                (
                    i,
                    cid[name],
                    " ".join(codes.get(name, [])),
                    labels[index],
                    source_g,
                    "Utopia" if index == 0 else "UtopiaStd",
                    "1" if index == 0 else "100/94",
                    *base["hmtx"][cid[name]],
                )
            )
    # Force full decompilation: catch dangling glyph or hint references now.
    check = TTFont(output, recalcTimestamp=False)
    for tag in check.keys():
        check[tag]
    for g in check.getGlyphSet().values():
        g.draw(RecordingPen())
    return len(original), len(added) + math_added


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--utopia", type=Path, required=True)
    parser.add_argument("--erewhon", type=Path, required=True)
    parser.add_argument("--erewhon-math", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.erewhon) as archive:
        for style in STYLES:
            target = args.output / font_file(style)
            with archive.open(EREWHON_MEMBER.format(style)) as source:
                original, added = assemble(
                    args.utopia / "dist" / f"Utopia-{style}.otf",
                    source,
                    target,
                    style,
                    args.erewhon_math,
                )
            print(
                f"{target.name}: {original} Utopia slots (three superscripts replaced), {added} normalized Erewhon / Math additions"
            )
        (args.output / "OFL.txt").write_bytes(archive.read("erewhon/doc/OFL.txt"))
    with zipfile.ZipFile(args.erewhon_math) as archive:
        (args.output / "Erewhon-Math-README.md").write_bytes(
            archive.read("erewhon-math/README.md")
        )
    shutil.copyfile(args.utopia / "COPYING", args.output / "Adobe-Utopia-COPYING.txt")
    for name in ("OLEBFont-NOTICE.txt", "Adobe-TUG-Utopia-LICENSE.txt"):
        shutil.copyfile(Path(__file__).with_name(name), args.output / name)


if __name__ == "__main__":
    main()
