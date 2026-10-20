"""The PTXprint overrides in config/: each one must change something."""

from __future__ import annotations

import configparser
import io
import os
import re
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

from ptxprint.modelmap import ModelMap
from ptxprint.usxutils import merge_sty, simple_parse

from bible import paths
from bible.project import FRONT_TEMPLATE, bsb_baseline, style_mods

LAYOUT = paths.CONFIG_DIR / "layout.ini"


def read_cfg(text: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read_string(text)
    return cfg


def overlay_values() -> dict[str, str]:
    """Each "section/key" that layout.ini sets, with its value."""
    cfg = read_cfg(LAYOUT.read_text(encoding="utf-8"))
    return {f"{s}/{k}": v for s in cfg.sections() for k, v in cfg[s].items()}


def normalized(
    key: str, value: str
) -> bool | float | str | tuple[str | frozenset[str], ...]:
    """A cfg value as PTXprint reads it, by the kind of widget that holds it."""
    info = ModelMap.get(key)
    widget = info.widget if info and info.widget else ""
    value = value.strip()
    if widget.startswith("c_"):
        return configparser.ConfigParser.BOOLEAN_STATES.get(value.lower(), False)
    if widget.startswith("s_"):
        return float(value or 0)
    if widget.startswith("bl_"):
        # PTXprint writes "Charis| Italic Bold|..." but reads any word order.
        name, style, *rest = value.split("|")
        return (name, frozenset(style.split()), *rest)
    return value


def test_layout_overrides_only_non_default_values() -> None:
    baseline = read_cfg(bsb_baseline()[0])
    repeated = [
        f"{key} = {value}"
        for key, value in overlay_values().items()
        # A key BSB leaves out has no default headless PTXprint could compare:
        # it falls back to the Paratext settings.
        if baseline.has_option(*key.split("/", 1))
        and normalized(key, value) == normalized(key, baseline.get(*key.split("/", 1)))
    ]
    assert repeated == [], "layout.ini repeats BSB's defaults"


def test_layout_sets_every_key_of_a_shared_setting() -> None:
    # PTXprint writes a widget shared by several keys under each of them, and
    # on loading, whichever comes last in the file wins. The merged file keeps
    # BSB's order, so setting one key alone can be undone by BSB's value for
    # another.
    shared = defaultdict(set)
    for key, info in ModelMap.items():
        if "/" in key and not key.endswith("_") and info.widget:
            shared[info.widget].add(key)
    overlay = overlay_values()
    for key in overlay:
        group = shared[ModelMap[key].widget] if key in ModelMap else {key}
        assert group <= overlay.keys(), f"{key} is also stored as {group - {key}}"
        values = {normalized(k, overlay[k]) for k in group}
        assert len(values) == 1, f"{sorted(group)} disagree"


def test_publication_data_uses_project_license_fields() -> None:
    cfg = read_cfg(LAYOUT.read_text(encoding="utf-8"))
    front = FRONT_TEMPLATE.read_text(encoding="utf-8")
    assert cfg["project"]["copyright"] == "Copyright © 2026 Basil Crow"
    assert (
        "Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International"
        in cfg["project"]["license"]
    )
    assert (
        "https://creativecommons.org/licenses/by-nc-nd/4.0/"
        in cfg["project"]["license"]
    )
    assert (
        front.index("\\periph Title Page")
        < front.index("\\periph Publication Data")
        < front.index("\\periph Table of Contents")
    )
    assert "\\zcopyright" in front and "\\zlicense" in front
    assert "\\resetpagenums -1" in front
    assert cfg["project"]["ifcolophon"] == "False"


def style_value(value: str) -> str | float:
    try:
        return float(value)
    except ValueError:
        return value.strip()


def test_style_mods_override_only_non_default_fields() -> None:
    # The order template.tex loads them in; BSB leaves custom.sty off.
    src = paths.UPSTREAM / "src"
    with (src / "usfm_sb.sty").open(encoding="utf-8") as f:
        base = simple_parse(f)
    with (src / "ptx2pdf.sty").open(encoding="utf-8") as f:
        merge_sty(base, simple_parse(f))
    merge_sty(base, simple_parse(io.StringIO(bsb_baseline()[1])))
    mods = simple_parse(io.StringIO(style_mods()))
    repeated = [
        f"{marker} {field} {value}"
        for marker, fields in mods.items()
        for field, value in fields.items()
        if field != "marker" and field in base.get(marker, {})
        # An explicit FontSize clears an inherited FontScale in PTXprint.
        # Note origins need that reset to stay 9 pt inside smaller notes,
        # even when the numeric FontSize equals the underlying declaration.
        and not (field == "fontsize" and "fontscale" in base.get(marker, {}))
        and style_value(value) == style_value(base[marker][field])
    ]
    assert repeated == [], "ptxprint-mods.sty repeats the styles beneath it"


def test_chapter_figures_are_lining_despite_the_base_oldstyle_font(
    tmp_path: Path,
) -> None:
    # Exercise PTXprint's real font selection: removing onum from the style
    # feature list cannot disable +onum=1 embedded in the base font name, so
    # the chapter styles name the family directly. Oldstyle 3, 4 and 5
    # descend well below the baseline; lining figures do not.
    probe = tmp_path / "chapter-figures.tex"
    probe.write_text(
        r"""\input paratext2.tex
\def\regular{"OLEBFont:+onum=1:+pnum=1"}
\def\bold{"OLEBFont/B:+onum=1:+pnum=1"}
\def\italic{"OLEBFont/I:+onum=1:+pnum=1"}
\def\bolditalic{"OLEBFont/B/I:+onum=1:+pnum=1"}
\stylesheet{usfm_sb.sty}
\stylesheet{ptx2pdf.sty}
"""
        + rf"\stylesheet{{{paths.CONFIG_DIR / 'ptxprint-mods.sty'}}}"
        + r"""
\catcode`\@=11
\XeTeXuseglyphmetrics=3
\def\measure#1{%
  \s@tfont{#1}{#1}%
  \setbox0=\hbox{345}%
  \immediate\write16{DIGITS #1 \the\ht0\space\the\dp0}%
}
\measure{p}
\measure{c}
\measure{cl}
\s@ve@nd
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["xetex", "-interaction=nonstopmode", "-halt-on-error", probe.name],
        cwd=tmp_path,
        env={**os.environ, "TEXINPUTS": f"{paths.UPSTREAM / 'src'}//:"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    depths = {
        marker: float(depth) / float(height)
        for marker, height, depth in re.findall(
            r"DIGITS (p|c|cl) ([\d.]+)pt\s*([\d.]+)pt", result.stdout
        )
    }
    assert set(depths) == {"p", "c", "cl"}, result.stdout
    assert depths["p"] > 0.1
    assert depths["c"] < depths["p"] / 2
    assert depths["cl"] < depths["p"] / 2


def test_note_callers_follow_context_and_restart_without_margin_notes(
    tmp_path: Path,
) -> None:
    # Load the production customizations, including their relative protrusion
    # input, in a small PTXprint project independent of generated scripture.
    conf = tmp_path / "shared/ptxprint/Bible"
    conf.mkdir(parents=True)
    work = tmp_path / "local/ptxprint/Bible"
    work.mkdir(parents=True)
    shutil.copy(paths.CONFIG_DIR / "protrusion.tex", conf)
    (conf / "baseline.sty").write_text(bsb_baseline()[1], encoding="utf-8")
    (conf / "mods.sty").write_text(style_mods(), encoding="utf-8")
    (work / "front.usfm").write_text(
        r"""\id FRT
\periph Preface|id="preface"
\p Alpha\f + \ft First front note.\f* and beta\f + \ft Second front note.\f*.
\p Quotation\x + \xt Gen. 1:1\x*.
""",
        encoding="utf-8",
    )
    (work / "scripture.usfm").write_text(
        r"""\id PRO
\c 8
\p
\v 5 Alpha\f + \ft First scripture note.\f* and beta\f + \ft Second scripture note.\f*.
\p\pagebreak
\v 6 Gamma\f - \fr 6 \ft Callerless margin note.\f*.
\p\pagebreak
\v 7 Delta\f + \ft Restarted scripture note.\f*.
""",
        encoding="utf-8",
    )
    (work / "last.usfm").write_text(
        r"""\id MAT
\c 1
\p
\v 1 Epsilon\f + \ft New Testament note.\f*.
""",
        encoding="utf-8",
    )
    probe = work / "callers.tex"
    probe.write_text(
        r"""\input paratext2.tex
\input ptx-ptxprint.tex
\def\regular{"OLEBFont"}
\def\bold{"OLEBFont/B"}
\def\italic{"OLEBFont/I"}
\def\bolditalic{"OLEBFont/B/I"}
\FontSizeUnit=.75pt
\stylesheet{usfm_sb.sty}
\stylesheet{ptx2pdf.sty}
\stylesheet{../../../shared/ptxprint/Bible/baseline.sty}
\stylesheet{../../../shared/ptxprint/Bible/mods.sty}
\BodyColumns=1
\IntroColumns=1
\TitleColumns=1
\AutoCallers{f}{1,2,3,4,5,6,7,8,9}
\AutoCallers{x}{1,2,3,4,5,6,7,8,9}
\PageResetCallers{x}
"""
        + rf"\input {paths.CONFIG_DIR / 'ptxprint-mods.tex'}"
        + r"""
\NoStorePeriph{preface}
\nolotwritetrue
\catcode`\@=11
\def\ReportNote#1{%
  \immediate\write16{NOTE #1 [\them@rk] WIDTH \the\NoteCallerWidth\space GAP \the\NoteCallerSpace}%
}
\sethook{start}{f}{\ReportNote{f}}
\sethook{start}{x}{\ReportNote{x}}
\catcode`\@=12
\scripturebookfalse
\ptxfile{front.usfm}
\scripturebooktrue
\ptxfile{scripture.usfm}
\scripturebookfalse
\ptxfile{front.usfm}
\scripturebooktrue
\lastptxfiletrue
\ptxfile{last.usfm}
\end
""",
        encoding="utf-8",
    )
    records = []
    for _ in range(3):
        result = subprocess.run(
            ["xetex", "-interaction=nonstopmode", "-halt-on-error", probe.name],
            cwd=work,
            env={**os.environ, "TEXINPUTS": f"{paths.UPSTREAM / 'src'}//:"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout
        records.append((work / "callers.notepages").read_text(encoding="utf-8"))

    notes = re.findall(
        r"NOTE ([fx]) \[([^]]*)\] WIDTH ([\d.]+)pt GAP ([\d.]+)pt", result.stdout
    )
    assert [(kind, caller) for kind, caller, _, _ in notes] == [
        ("f", "1"),
        ("f", "2"),
        ("x", "1"),
        ("f", "a"),
        ("f", "b"),
        ("f", ""),
        ("f", "a"),
        ("f", "1"),
        ("f", "2"),
        ("x", "1"),
        ("f", "a"),
    ], result.stdout
    for _, caller, width, gap in notes:
        if caller:
            assert (float(width), float(gap)) == (0, 1)
        else:
            # Bottom-note spacing is local; margin notes keep their defaults.
            assert float(width) > 0
            assert float(gap) > 1
    assert records[1] == records[2]
    page_records = re.findall(r"\\noteonpage\{f\}\{(\d+)\}\{(-?\d+)\}", records[2])
    # Each automatic caller has exactly one record; the callerless note must
    # not overwrite its predecessor's page. This also checks the image patch.
    assert [int(number) for number, _ in page_records] == list(range(1, 9))
    assert int(page_records[4][1]) > int(page_records[3][1]) + 1
