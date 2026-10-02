#!/usr/bin/env python3
"""Inventory every glyph slot (including unencoded alternates) in pinned faces."""

from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from argparse import ArgumentParser
from io import BytesIO
from pathlib import Path
from typing import TypedDict

from font_sources import UTOPIA_STD_TO_UTOPIA
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont


class Measurement(TypedDict):
    bounds: tuple[float, float, float, float] | None
    hmtx: tuple[int, int]


class Face(TypedDict):
    font: str | None
    member: str
    sha256: str
    glyphs: int
    encoded_glyphs: int
    unicode_mappings: int
    SizeType: str
    scale_to_utopia: float
    reference_measurements: dict[str, Measurement]


def inventory(utopia: Path, archives: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    inputs = [
        (p.name, p.read_bytes(), "Utopia")
        for p in sorted((utopia / "dist").glob("*.otf"))
    ]
    for family in ("erewhon", "erewhon-math"):
        with zipfile.ZipFile(archives / f"{family}.zip") as z:
            inputs.extend(
                (
                    member,
                    z.read(member),
                    "UtopiaStd",
                )
                for member in sorted(z.namelist())
                if member.endswith(".otf")
            )
    summary: list[Face] = []
    with (output / "glyphs.csv").open("w", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(
            (
                "Font",
                "GID",
                "Glyph",
                "Unicode",
                "SizeType",
                "SizeTypeBasis",
                "ScaleToUtopia",
                "UPEM",
                "Advance",
                "LSB",
                "XMin",
                "YMin",
                "XMax",
                "YMax",
            )
        )
        for member, data, size_type in inputs:
            font = TTFont(BytesIO(data), recalcTimestamp=False)
            name = font["name"].getDebugName(6)
            glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
            codes: dict[str, list[str]] = {}
            for code, g in cmap.items():
                codes.setdefault(g, []).append(f"U+{code:04X}")
            measurements: dict[str, Measurement] = {}
            for i, g in enumerate(font.getGlyphOrder()):
                pen = BoundsPen(glyphs)
                glyphs[g].draw(pen)
                bounds = pen.bounds
                if g in (cmap.get(0x48), cmap.get(0x78), cmap.get(0x30)):
                    measurements[g] = {"bounds": bounds, "hmtx": font["hmtx"][g]}
                writer.writerow(
                    (
                        name,
                        i,
                        g,
                        " ".join(codes.get(g, [])),
                        size_type,
                        "font design convention; see font-normalization.md",
                        "1" if size_type == "Utopia" else "100/94",
                        font["head"].unitsPerEm,
                        *font["hmtx"][g],
                        *(
                            (round(v, 6) for v in bounds)
                            if bounds
                            else ("", "", "", "")
                        ),
                    )
                )
            summary.append(
                {
                    "font": name,
                    "member": member,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "glyphs": len(font.getGlyphOrder()),
                    "encoded_glyphs": len(codes),
                    "unicode_mappings": len(cmap),
                    "SizeType": size_type,
                    "scale_to_utopia": (
                        1 if size_type == "Utopia" else UTOPIA_STD_TO_UTOPIA
                    ),
                    "reference_measurements": measurements,
                }
            )
    result = {
        "faces": summary,
        "total_glyph_slots": sum(f["glyphs"] for f in summary),
        "SizeType_counts": {
            t: sum(f["glyphs"] for f in summary if f["SizeType"] == t)
            for t in ("Utopia", "UtopiaStd")
        },
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "faces"}, indent=2))


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--utopia", type=Path, required=True)
    parser.add_argument("--archives", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inventory(args.utopia, args.archives, args.output)


if __name__ == "__main__":
    main()
