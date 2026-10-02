"""Pinned donor size conventions and hint-preserving normalization.

SizeType describes the design's em convention, not the height of an individual
symbol: a superscript and an extensible delimiter still belong to their font's
size convention. See docs/font-normalization.md for evidence and limits.
"""

import zipfile
from copy import deepcopy
from io import BytesIO

from fontTools.cffLib.specializer import commandsToProgram, programToCommands
from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import ScalerVisitor

UTOPIA_STD_TO_UTOPIA = 100 / 94
MATH_MEMBERS = ("erewhon-math/Erewhon-Math.otf", "erewhon-math/Erewhon-Math-Bold.otf")


def archive_font(archive, member):
    with zipfile.ZipFile(archive) as z:
        return TTFont(BytesIO(z.read(member)), recalcTimestamp=False)


def scaled_stems(args, factor):
    """Scale edge locations while retaining Type 2 ghost-hint sentinels.

    A -20 hint names its first edge; a -21 hint names its second edge.
    Re-encode deltas from the previous pair's second edge after scaling.
    Adobe Type 2 specification, section 4.3 (5177.Type2.pdf).
    """
    assert len(args) % 2 == 0
    old_end = new_end = 0
    result = []
    for delta, width in zip(args[::2], args[1::2]):
        start = old_end + delta
        if width == -21:
            new_start, new_width = (start + width) * factor - width, width
        elif width == -20:
            new_start, new_width = start * factor, width
        else:
            assert width >= 0, width
            new_start, new_width = start * factor, width * factor
        result.extend((new_start - new_end, new_width))
        old_end, new_end = start + width, new_start + new_width
    return result


def normalized_donor(font, style=None):
    """Enlarge a UtopiaStd donor at unchanged UPEM; keep its Type 2 hints.

    Expand subroutines before scaling so call indices and hintmask bytes cannot
    accidentally be treated as coordinates. Preserve fractional coordinates;
    round only integer OpenType metrics. Utopia itself never enters this path.
    """
    font = deepcopy(font)
    top = font["CFF "].cff[0]
    assert font["head"].unitsPerEm == 1000
    # Repair the known advance before applying the common normalization.
    if style == "Italic":
        width, bearing = font["hmtx"]["zero.taboldstyle"]
        assert width == 498
        # The other nine tabular oldstyle figures set the advance to match.
        assert {
            font["hmtx"][g][0]
            for g in font.getGlyphOrder()
            if g.endswith(".taboldstyle") and g != "zero.taboldstyle"
        } == {500}
        font["hmtx"]["zero.taboldstyle"] = 500, bearing
    scaler = ScalerVisitor(UTOPIA_STD_TO_UTOPIA)
    for tag in ("hmtx", "GPOS", "GDEF", "MATH", "BASE"):
        if tag in font:
            scaler.visit(font[tag])
    font["CFF "].cff.desubroutinize()
    private = top.Private
    for attr in (
        "BlueValues",
        "OtherBlues",
        "FamilyBlues",
        "FamilyOtherBlues",
        "StdHW",
        "StdVW",
        "StemSnapH",
        "StemSnapV",
        "defaultWidthX",
        "nominalWidthX",
        "BlueShift",
        "BlueFuzz",
    ):
        value = getattr(private, attr, None)
        if value is not None:
            setattr(
                private,
                attr,
                (
                    [v * UTOPIA_STD_TO_UTOPIA for v in value]
                    if isinstance(value, list)
                    else value * UTOPIA_STD_TO_UTOPIA
                ),
            )
    private.BlueScale /= UTOPIA_STD_TO_UTOPIA
    for name in font.getGlyphOrder():
        cs = top.CharStrings[name]
        commands = programToCommands(cs.program)
        for index, (op, args) in enumerate(commands):
            assert op not in ("callsubr", "callgsubr", "blend", "vsindex")
            if op in ("hstem", "hstemhm", "vstem", "vstemhm"):
                args[:] = scaled_stems(args, UTOPIA_STD_TO_UTOPIA)
                continue
            # Operands left on the stack before the first mask are implicit
            # vertical stems. Scaling them linearly below is correct only
            # without ghost sentinels; the pinned sources have none there.
            if (
                op == ""
                and index + 1 < len(commands)
                and commands[index + 1][0] in ("hintmask", "cntrmask")
            ):
                assert not any(w in (-20, -21) for w in args[1::2]), (name, args)
            for i, value in enumerate(args):
                if isinstance(value, (int, float)):
                    args[i] = value * UTOPIA_STD_TO_UTOPIA
                else:
                    assert isinstance(value, bytes), (name, op, value)
        # The initial empty command is the optional advance-width operand.
        if commands and commands[0][0] == "":
            assert len(commands[0][1]) == 1
            commands.pop(0)
        commands.insert(0, ("", [font["hmtx"][name][0] - private.nominalWidthX]))
        cs.program = commandsToProgram(commands)
        cs.bytecode = None
    top.FontBBox = [v * UTOPIA_STD_TO_UTOPIA for v in top.FontBBox]
    return font


def math_donors(archive, style):
    """No italic math face exists. Use upright symbols, never synthesize slant.

    Bold Math has limited coverage; use Regular Math for its missing glyphs.
    Mathematical alphabet codepoints retain their explicitly designed style.
    """
    members = list(MATH_MEMBERS)
    if style in ("Bold", "BoldItalic"):
        members.reverse()
    return [archive_font(archive, member) for member in members]
