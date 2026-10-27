"""The PTXprint overrides in config/: each one must change something."""

from __future__ import annotations

import configparser
import io
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import pytest
from ptxprint.modelmap import ModelMap
from ptxprint.usxutils import merge_sty, simple_parse

from bible import paths, typeface
from bible.project import FRONT_TEMPLATE, bsb_baseline, pagination, style_mods

LAYOUT = paths.CONFIG_DIR / "layout.ini"


def xetex(cwd: Path, name: str) -> subprocess.CompletedProcess[str]:
    """Typeset a job with PTXprint's macros, which must succeed."""
    result = subprocess.run(
        ["xetex", "-interaction=nonstopmode", "-halt-on-error", name],
        cwd=cwd,
        env={**os.environ, "TEXINPUTS": f"{paths.UPSTREAM / 'src'}//:"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    return result


def ptxprint_project(tmp_path: Path) -> Path:
    """A small PTXprint project loading the production customizations,
    including their relative inputs; the directory its jobs run in."""
    conf = tmp_path / "shared/ptxprint/Bible"
    conf.mkdir(parents=True)
    work = tmp_path / "local/ptxprint/Bible"
    work.mkdir(parents=True)
    for name in ("protrusion.tex", "running-heads.tex"):
        shutil.copy(paths.CONFIG_DIR / name, conf)
    (conf / "baseline.sty").write_text(bsb_baseline()[1], encoding="utf-8")
    (conf / "mods.sty").write_text(style_mods(), encoding="utf-8")
    return work


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
    assert cfg["project"]["license"] == "Creative Commons BY-NC-ND 4.0 license"
    assert (
        front.index("\\periph Half-title")
        < front.index("\\periph Title Page")
        < front.index("\\periph Imprint page")
        < front.index("\\periph Table of Contents")
    )
    assert all(s in front for s in ("\\zcopyright", "\\zlicense", "\\zvar|compiled\\*"))
    assert "\\resetpagenums 1" in front
    assert "\\dopagenums" not in front
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
        # Note origins need that reset to stay at the body size inside notes,
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
    # the chapter styles select their fonts directly. Oldstyle 3, 4, and 5
    # descend well below the baseline; lining figures do not.
    (tmp_path / "mods.sty").write_text(style_mods(), encoding="utf-8")
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
        + rf"\stylesheet{{{tmp_path / 'mods.sty'}}}"
        + r"""
\catcode`\@=11
\XeTeXuseglyphmetrics=3
\def\measure#1{%
  \s@tfont{#1}{#1}%
  \immediate\write16{SELECTED #1 \fontname\font}%
  \setbox0=\hbox{345}%
  \immediate\write16{DIGITS #1 \the\ht0\space\the\dp0}%
}
\measure{p}
\measure{c}
\measure{cl}
\s@tfont{c}{c}
\setbox0=\hbox{1}\setbox1=\hbox{12}\setbox2=\hbox{123}
\ifdim\wd1>\wd0\else\errmessage{Two digit width}\fi
\ifdim\wd2>\wd1\else\errmessage{Three digit width}\fi
\setbox1=\hbox{0}
\ifdim\wd1=\wd0\errmessage{Tabular figures}\fi
\shipout\hbox{1 12 123}
\s@ve@nd
""",
        encoding="utf-8",
    )
    result = xetex(tmp_path, probe.name)
    depths = {
        marker: float(depth) / float(height)
        for marker, height, depth in re.findall(
            r"DIGITS (p|c|cl) ([\d.]+)pt\s*([\d.]+)pt", result.stdout
        )
    }
    selected = dict(re.findall(r"SELECTED (p|c|cl) (.*)", result.stdout))
    assert str(typeface.chapter_face()) in selected["c"]
    assert "OLEBFont" in selected["p"] and "onum=1" in selected["p"]
    assert "OLEBFont" in selected["cl"] and "onum=1" not in selected["cl"]
    fonts = subprocess.check_output(
        ["pdffonts", str(tmp_path / "chapter-figures.pdf")], text=True
    )
    assert typeface.postscript_name(typeface.chapter_face()) in fonts
    assert set(depths) == {"p", "c", "cl"}, result.stdout
    assert depths["p"] > 0.1
    assert depths["c"] < depths["p"] / 2
    assert depths["cl"] < depths["p"] / 2


def test_note_callers_follow_context_and_restart_without_margin_notes(
    tmp_path: Path,
) -> None:
    work = ptxprint_project(tmp_path)
    (work / "front.usfm").write_text(
        r"""\id FRT
\periph Preface|id="preface"
\p Alpha\f + \ft First front note. A longer explanation repeats its words to make this footnote wrap onto another line, where it must return to the left edge of the text.\f* and beta\f + \ft Second front note.\f*.
\p More word\f + \ft Front note 3.\f* word\f + \ft Front note 4.\f* word\f + \ft Front note 5.\f* word\f + \ft Front note 6.\f* word\f + \ft Front note 7.\f* word\f + \ft Front note 8.\f* word\f + \ft Front note 9.\f* word\f + \ft Front note 10.\f*.
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
  \immediate\write16{NOTE #1 [\them@rk] WIDTH \the\NoteCallerWidth\space GAP \the\NoteCallerSpace\space LEFT \the\leftskip}%
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
        result = xetex(work, probe.name)
        records.append((work / "callers.notepages").read_text(encoding="utf-8"))

    notes = re.findall(
        r"NOTE ([fx]) \[([^]]*)\] WIDTH ([\d.]+)pt GAP ([\d.]+)pt", result.stdout
    )
    assert [(kind, caller) for kind, caller, _, _ in notes] == [
        ("f", "1"),
        ("f", "2"),
        *(("f", str(n)) for n in range(3, 11)),
        ("x", "1"),
        ("f", "a"),
        ("f", "b"),
        ("f", ""),
        ("f", "a"),
        ("f", "1"),
        ("f", "2"),
        *(("f", str(n)) for n in range(3, 11)),
        ("x", "1"),
        ("f", "a"),
    ], result.stdout
    for kind, caller, width, gap in notes:
        if caller:
            # A bottom note's label carries its own word space; the front
            # matter's margin reference keeps a superior caller and its gap.
            assert (float(width), float(gap)) == (0, 1 if kind == "x" else 0)
        else:
            # Bottom-note spacing is local; margin notes keep their defaults.
            assert float(width) > 0
            assert float(gap) > 1
    assert records[1] == records[2]
    page_records = re.findall(r"\\noteonpage\{f\}\{(\d+)\}\{(-?\d+)\}", records[2])
    # Each automatic caller has exactly one record; the callerless note must
    # not overwrite its predecessor's page. This also checks the image patch.
    assert [int(number) for number, _ in page_records] == list(range(1, 25))
    assert int(page_records[12][1]) > int(page_records[11][1]) + 1
    left_skips = re.findall(r"NOTE f \[1\].* LEFT (-?[\d.]+)pt", result.stdout)
    assert left_skips and all(float(left) == 0 for left in left_skips)

    # In-note labels take the note's baseline and a period, while the
    # caller in the text remains superior. Check both numbers and letters.
    lines = layout(work, "callers").findall(".//x:line", NS)

    def opening(*texts: str) -> int:
        return next(
            index
            for index, line in enumerate(lines)
            if [w.text for w in line][: len(texts)] == list(texts)
        )

    for label, first, second in (
        ("1.", "First", "front"),
        ("a.", "First", "scripture"),
    ):
        words = list(lines[opening(label, first, second)])
        assert (
            abs(float(words[0].attrib["yMax"]) - float(words[1].attrib["yMax"])) < 0.1
        )
        assert float(words[1].attrib["xMin"]) - float(words[0].attrib["xMax"]) > 1
    first_line = opening("1.", "First", "front")
    assert (
        abs(
            float(lines[first_line][0].attrib["xMin"])
            - float(lines[first_line + 1][0].attrib["xMin"])
        )
        < 0.1
    )


NS = {"x": "http://www.w3.org/1999/xhtml"}


def layout(work: Path, name: str) -> ET.Element:
    """Poppler's layout of <name>.pdf: its pages, lines, and words, each word
    with its position."""
    pdf = subprocess.check_output(
        ["pdftotext", "-bbox-layout", str(work / f"{name}.pdf"), "-"], text=True
    )
    return ET.fromstring(pdf)


def typeset_lines(
    work: Path, name: str, *, after_verse_space_factor: float = 1.8, setup: str = ""
) -> list[list[ET.Element]]:
    """Typeset <name>.usfm in one column with the production customizations,
    and return the words of each line as Poppler finds them."""
    (work / f"{name}.tex").write_text(
        r"""\input paratext2.tex
\input ptx-ptxprint.tex
\def\regular{"OLEBFont:+onum=1:+pnum=1"}
\def\bold{"OLEBFont/B:+onum=1:+pnum=1"}
\def\italic{"OLEBFont/I:+onum=1:+pnum=1"}
\def\bolditalic{"OLEBFont/B/I:+onum=1:+pnum=1"}
\FontSizeUnit=.75pt
\def\LineSpaceBase{12}
\def\LineSpacingFactor{1.222222}
\stylesheet{usfm_sb.sty}
\stylesheet{ptx2pdf.sty}
\stylesheet{../../../shared/ptxprint/Bible/baseline.sty}
\stylesheet{../../../shared/ptxprint/Bible/mods.sty}
\BodyColumns=1\IntroColumns=1\TitleColumns=1
\JustifyParstrue\IndentAfterHeadingfalse
\OmitVerseNumberOnetrue
"""
        + rf"""\def\AfterVerseSpaceFactor{{{after_verse_space_factor}}}
\hangpoetry
\input {paths.CONFIG_DIR / 'ptxprint-mods.tex'}"""
        + r"""
\nolotwritetrue
\scripturebooktrue
\lastptxfiletrue
"""
        + setup
        + rf"\ptxfile{{{name}.usfm}}"
        + r"""
\end
""",
        encoding="utf-8",
    )
    result = xetex(work, f"{name}.tex")
    assert "Overfull" not in result.stdout
    return [list(line) for line in layout(work, name).findall(".//x:line", NS)]


def test_opening_pages_and_margin_contents(tmp_path: Path) -> None:
    work = ptxprint_project(tmp_path)
    (work / "opening.usfm").write_text(
        FRONT_TEMPLATE.read_text()
        + '\\periph Introduction|id="intbible"\n\\mt1 Introduction\n'
        "\\p Opening.\n\\pb\n\\p Continuation.\n"
        '\\periph Preface|id="preface"\n\\mt1 Preface\n\\p Prefacewords.\n'
        '\\periph The Old Testament|id="x-old-testament"\n'
        "\\mt1 The Old Testament\n\\zendperiph\n"
        "\\id GEN\n\\mt1 Genesis\n\\c 1\n\\p\\v 1 Scripture.\n"
        # Each book is its own file, ejecting its last page.
        "\\pb\n"
        '\\id XXG\n\\periph The New Testament|id="x-new-testament"\n'
        "\\mt1 The New Testament\n\\zendperiph\n"
        "\\id MAT\n\\mt1 Matthew\n\\c 1\n\\p\\v 1 Gospel.\n",
        encoding="utf-8",
    )
    cfg = read_cfg(LAYOUT.read_text(encoding="utf-8"))
    setup = "\n".join(
        [
            *(rf"\defzvar{{{name}}}{{{value}}}" for name, value in cfg["vars"].items()),
            rf"\def\zcopyright{{{cfg['project']['copyright']}}}",
            rf"\def\zlicense{{{cfg['project']['license']}}}",
            r"\notocwritetrue",
            rf"\BindingGuttertrue\BindingGutter={cfg['paper']['gutter']}mm",
            pagination() + r"\defTOC{main}{\doTOCline{intbible}{Introduction}{}{}{7}"
            r"\doTOCline{x-old-testament}{The Old Testament}{}{}{11}"
            r"\doTOCline{GEN}{Genesis}{}{Gen.}{13}"
            r"\doTOCline{x-new-testament}{New Testament}{}{}{15}"
            r"\doTOCline{TST}{Firstgospel}{}{}{16}"
            # Exercise verso folios independently of testament spacing.
            r"\endpage"
            r"\m\hbox to\hsize{Leftedge\hfil Rightedge}\endgraf"
            r"\doTOCline{MAT}{Matthew}{}{}{17}"
            r"\doTOCline{MRK}{Mark}{}{}{18}}",
            "",
        ]
    )
    typeset_lines(work, "opening", setup=setup)
    # The first run records each row's page; the second sets each folio's
    # side from that record, as PTXprint's later runs do.
    assert "{BibleTOC:MAT}" in (work / "opening.picpages").read_text("utf-8")
    typeset_lines(work, "opening", setup=setup)
    pages = layout(work, "opening").findall(".//x:page", NS)
    assert len(pages) == 17
    words = [page.findall(".//x:word", NS) for page in pages]
    texts = [[w.text for w in page] for page in words]
    by_text = [{w.text: w for w in page} for page in words]
    assert not any(words[index] for index in (1, 9, 11, 13, 15))
    assert "Septuagint" not in texts[0]
    assert "Septuagint" in texts[2]
    imprint = by_text[3]
    assert (
        min(float(w.attrib["yMin"]) for w in words[3])
        < float(pages[3].attrib["height"]) * 0.2
    )
    starts = [
        float(imprint[text].attrib["xMin"])
        for text in (
            "Published",
            "Concord,",
            "www.oleb.bible",
            "Compiled",
            "Copyright",
            "Under",
            "[God",
            "Printed",
        )
    ]
    assert max(starts) - min(starts) < 0.05
    contents = by_text[4]
    assert "Gen." not in contents
    assert "1" not in contents and "5" not in contents
    gap = float(contents["Introduction"].attrib["xMin"]) - float(
        contents["vii"].attrib["xMax"]
    )
    assert abs(gap - 6 * 72 / 25.4) < 0.05
    # A part follows a blank line, on the page of its first entry.
    tops = {
        text: float(contents[text].attrib["yMin"])
        for text in ("Genesis", "New", "Firstgospel")
    }
    line = tops["Firstgospel"] - tops["New"]
    assert line > 0
    assert abs(tops["New"] - tops["Genesis"] - 2 * line) < 0.5
    verso = by_text[5]
    assert "New" not in verso
    right = float(verso["Rightedge"].attrib["xMax"])
    for number in ("7", "8"):
        offset = float(verso[number].attrib["xMax"]) - right
        assert 6 * 72 / 25.4 < offset < 14 * 72 / 25.4
    assert (
        abs(float(verso["7"].attrib["xMax"]) - float(verso["8"].attrib["xMax"])) < 0.05
    )
    assert "5" not in verso
    assert "viii" in texts[7]
    # An opening folio is centered under the text column, as its title is.
    for index, number, title in (
        (6, "vii", "Introduction"),
        (8, "ix", "Preface"),
        (12, "3", "Genesis"),
        (16, "7", "Matthew"),
    ):
        footer, heading = by_text[index][number], by_text[index][title]
        assert (
            abs(
                float(footer.attrib["xMin"])
                + float(footer.attrib["xMax"])
                - float(heading.attrib["xMin"])
                - float(heading.attrib["xMax"])
            )
            < 2
        )
    # Each testament's divider opens a recto without a folio.
    assert texts[10] == ["The", "Old", "Testament"]
    assert texts[14] == ["The", "New", "Testament"]


@pytest.mark.parametrize("label", ["Longlabel", "Longerlabel"])
def test_narrow_table_labels_keep_their_natural_width(
    tmp_path: Path, label: str
) -> None:
    work = ptxprint_project(tmp_path)
    (work / "labels.usfm").write_text(
        "\\id TST\n\\p Before.\n\\b\n"
        "\\tr\\tc1 Short\\tc2 Meaning\n"
        f"\\tr\\tc1 {label}\\tc2 Description\n\\b\n\\p After.\n",
        encoding="utf-8",
    )
    words = [word for line in typeset_lines(work, "labels") for word in line]
    longest = next(w for w in words if w.text == label)
    meaning = next(w for w in words if w.text == "Meaning")
    gap = float(meaning.attrib["xMin"]) - float(longest.attrib["xMax"])
    # Native .1 IndentUnit padding, without stretching the intercolumn gap.
    assert abs(gap * 72.27 / 72 - 0.1 * 144 * 0.75) < 0.02


def test_stasis_prints_a_centered_dinkus(tmp_path: Path) -> None:
    work = ptxprint_project(tmp_path)
    (work / "stasis.usfm").write_text(
        "\\id PSA\n\\c 3\n\\p\\v 1 Preliminary prose.\n"
        "\\q2 Beforestasis ends here.\n\\sd2\n"
        "\\c 4\n\\d A Psalm.\n\\p\\v 1 Afterstasis begins here.\n",
        encoding="utf-8",
    )
    words = [word for line in typeset_lines(work, "stasis") for word in line]
    before = next(w for w in words if w.text == "Beforestasis")
    after = next(w for w in words if w.text == "Afterstasis")
    gap = float(after.attrib["yMin"]) - float(before.attrib["yMin"])
    assert 11 < gap < 66
    # As a native heading, it is padded to whole lines of the grid.
    prose = next(w for w in words if w.text == "Preliminary")
    line = float(before.attrib["yMin"]) - float(prose.attrib["yMin"])
    assert abs(gap / line - round(gap / line)) < 0.01
    stars = [w for w in words if w.text and set(w.text) == {"*"}]
    assert "".join(w.text or "" for w in stars) == "***"
    # It stands above the next psalm's title, centered on the column as the
    # title is.
    title = [
        next(w for w in words if w.text == "A"),
        next(w for w in words if w.text == "Psalm."),
    ]
    assert all(
        float(before.attrib["yMin"])
        < float(w.attrib["yMin"])
        < float(title[0].attrib["yMin"])
        for w in stars
    )

    def center(span: list[ET.Element]) -> float:
        return (float(span[0].attrib["xMin"]) + float(span[-1].attrib["xMax"])) / 2

    assert abs(center(stars) - center(title)) < 0.5


def test_urls_keep_both_slashes_in_print(tmp_path: Path) -> None:
    work = ptxprint_project(tmp_path)
    (work / "urls.usfm").write_text(
        '\\id FRT\n\\periph Introduction|id="intbible"\n'
        "\\p See https://example.org/license/.\n",
        encoding="utf-8",
    )
    lines = typeset_lines(work, "urls")
    words = [word.text for line in lines for word in line]
    assert "https://example.org/license/." in words


def test_peripheral_running_heads_follow_pages(tmp_path: Path) -> None:
    work = ptxprint_project(tmp_path)
    units = [
        ("x-dedication", "The Epistle Dedicatory", "\\mt2 To the Most High"),
        ("x-translators-preface", "The Translators to the Reader", "\\mt1 Preface"),
    ]
    # The head is the unit's \h, not the division's longer title.
    (work / "front.usfm").write_text(
        "\\id FRT\n"
        + "".join(
            f'\\periph {title} in Full|id="{identifier}"\n\\h {title}\n{opening}\n'
            "\\p Openingbody.\n"
            "\\p\\pagebreak\n\\p Secondbody.\n"
            "\\p\\pagebreak\n\\p Thirdbody.\n"
            for identifier, title, opening in units
        ),
        encoding="utf-8",
    )
    (work / "scripture.usfm").write_text(
        "\\id GEN\n\\h Genesis\n\\mt1 Genesis\n\\ip Scriptureintro.\n"
        "\\p\\pagebreak\n\\ip Continuedintro.\n"
        "\\p\\pagebreak\n\\c 1\n\\p\\v 1 Scripturebody.\n",
        encoding="utf-8",
    )
    (work / "heads.tex").write_text(
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
\BodyColumns=1\IntroColumns=1\TitleColumns=1
\DoubleSidedtrue
\def\RHevenleft{\firstref}\def\RHoddright{\lastref}
"""
        + rf"\input {paths.CONFIG_DIR / 'ptxprint-mods.tex'}"
        + r"""
\nolotwritetrue
\scripturebookfalse
\ptxfile{front.usfm}
\scripturebooktrue
\lastptxfiletrue
\ptxfile{scripture.usfm}
\end
""",
        encoding="utf-8",
    )
    xetex(work, "heads.tex")
    pages = layout(work, "heads").findall(".//x:page", NS)
    # Each unit opens on a page of its own, then fills two more, one of each
    # side; Genesis adds its title page, a second introduction page and a
    # chapter page.
    expected = [
        (title, opening, offset) for _, title, opening in units for offset in range(3)
    ]
    assert len(pages) == len(expected) + 3
    for number, (page, (title, opening, offset)) in enumerate(zip(pages, expected), 1):
        first = page.find(".//x:line", NS)
        assert first is not None
        text = " ".join(word.text or "" for word in first)
        if offset == 0:
            # The displayed title alone; no running head.
            assert text == opening.split(" ", 1)[1]
        else:
            assert text == title
            # Odd pages put the head at the right, even pages at the left.
            outer = float(first[0].attrib["xMin"]) > float(page.attrib["width"]) / 2
            assert outer == (number % 2 == 1)
        assert page.findall(".//x:word", NS)[-1].text == str(number)
    intro = " ".join(w.text or "" for w in pages[-2].findall(".//x:word", NS))
    assert intro == f"Continuedintro. {len(pages) - 1}"
    last = " ".join(w.text or "" for w in pages[-1].findall(".//x:word", NS))
    assert "Genesis 1" in last
    assert "Reader" not in last


@pytest.mark.parametrize("after_verse_space_factor", [1.8, 3.0])
def test_poetry_indents_and_line_opening_verse_numbers(
    tmp_path: Path, after_verse_space_factor: float
) -> None:
    """Check rendered geometry, including wraps, inline milestones, and acrostics."""
    work = ptxprint_project(tmp_path)
    (work / "poetry.usfm").write_text(
        r"""\id LAM
\c 1
\p \v 1 Preliminary prose clears the chapter cutout before the poem begins.
\p Further prose clears the chapter cutout completely.
\b
\q1 \v 8 Singlefigure aligns beside the level-one text.
\q1 \v 14 Levelone """
        + "echo " * 40
        + r"""Tailone.
\q2 \v 9 Leveltwo """
        + "echo " * 40
        + r"""Tailtwo.
\q2 \v 119 Leveltwothree aligns beside the level-two text.
\q1 \v 118 Threefigures align beside the level-one text.
\q1 \v 35a Lettered labels retain their native appearance.
\q1 \v 23 \vp 24:23\vp* Published labels hang before the text.
\q1 \v 30 \vp 30:15\vp* Anotherpublished label hangs too.
\q1 \v 36-37 Bridged labels keep their native formatting.
\q1 Beforeone \v 38 Afterone remains inline.
\q2 Beforetwo \v 39 Aftertwo remains inline.
\q1 \v 41 Opening \v 42 Secondinline remains in this line.
\qa \v 40 AIN
\q1 Acrostic starts beneath its heading.
\qa \v 44 PE
\q1 \v 45 Fortyfive follows the acrostic number inline.
\b
\p Afterpoetry resumes the ordinary prose paragraph indent.
\p Prosebefore \v 43 Proseafter keeps an inline number outside poetry.
\m Unindented resumes prose at the margin.
\b
\li1 \it Listkey\it* Listdescription """
        + "echo " * 40
        + r"""Listtail.
\b
\c 3
\qa \v 1 ALEPH
\q1 Chapteracrostic suppresses verse one beside the chapter figure.
""",
        encoding="utf-8",
    )
    lines = typeset_lines(
        work, "poetry", after_verse_space_factor=after_verse_space_factor
    )
    words = [word for line in lines for word in line]

    def word(text: str) -> ET.Element:
        found = [w for w in words if w.text == text]
        assert len(found) == 1, (text, [w.text for w in words])
        return found[0]

    def edge(element: ET.Element, side: str = "xMin") -> float:
        # Poppler uses PDF points (72/in), while the settings use TeX points.
        return float(element.attrib[side]) * 72.27 / 72

    def left(text: str) -> float:
        return edge(word(text))

    def right(text: str) -> float:
        return edge(word(text), "xMax")

    # The prose indent is 3 en of the 12-unit body at .75 pt per unit.
    x = 1.5 * 12 * 0.75
    margin = left("Afterpoetry") - x
    assert abs(left("Unindented") - margin) < 0.15
    assert abs(left("Listkey") - margin) < 0.15
    list_index = next(i for i, line in enumerate(lines) if word("Listkey") in line)
    list_continuation = lines[list_index + 1][0]
    assert list_continuation.text == "echo"
    assert abs(edge(list_continuation) - margin - x) < 0.15
    prose_gap = left("Proseafter") - right("43")
    assert abs(prose_gap - after_verse_space_factor * 0.75) < 0.02
    # Each level keeps its text position; variable-width labels share a
    # right edge at that level, with exactly the native prose gap after them.
    for label, opening, factor in (
        ("8", "Singlefigure", 2),
        ("14", "Levelone", 2),
        ("9", "Leveltwo", 3),
        ("119", "Leveltwothree", 3),
        ("118", "Threefigures", 2),
        ("35a", "Lettered", 2),
        ("24:23", "Published", 2),
        ("30:15", "Anotherpublished", 2),
        ("40", "Acrostic", 2),
        ("41", "Opening", 2),
        ("44", "45", 2),
    ):
        assert abs(left(opening) - margin - factor * x) < 0.15, opening
        assert abs(left(opening) - right(label) - prose_gap) < 0.02, label
    for start in ("Levelone", "Leveltwo"):
        index = next(i for i, line in enumerate(lines) if word(start) in line)
        continuation = lines[index + 1][0]
        assert continuation.text == "echo"
        assert abs(edge(continuation) - margin - 5 * x) < 0.15
    for before, label, after in (
        ("Beforeone", "38", "Afterone"),
        ("Beforetwo", "39", "Aftertwo"),
        ("Opening", "42", "Secondinline"),
        # A verse that opens an acrostic's line follows the acrostic's number.
        ("44", "45", "Fortyfive"),
        ("Prosebefore", "43", "Proseafter"),
    ):
        assert left(before) < left(label) < left(after)
        assert any(
            all(word(t) in line for t in (before, label, after)) for line in lines
        )
    # Poppler may split a bridge differently with another font or gap.
    # Measure its trailing edge without depending on those word boundaries.
    bridge_line = next(line for line in lines if word("Bridged") in line)
    bridge = bridge_line[: bridge_line.index(word("Bridged"))]
    assert "".join(w.text or "" for w in bridge) == "36–37"
    assert abs(left("Bridged") - margin - 2 * x) < 0.15
    assert abs(left("Bridged") - edge(bridge[-1], "xMax") - prose_gap) < 0.02
    # The only 1 above the last scripture line is the first chapter figure;
    # both opening verse ones are suppressed (the folio is farther down).
    last_line = float(word("Chapteracrostic").attrib["yMax"])
    assert (
        sum(w.text == "1" and float(w.attrib["yMin"]) < last_line for w in words) == 1
    )


def test_a_colophon_is_centered_across_the_text_width(tmp_path: Path) -> None:
    """PTXprint measures a sidebar before its category is named, so padding
    on the category alone would still narrow it. Its italic paragraph is
    centered, including its short last line, with no first-line indent. The
    notice ends without a full stop, whose protrusion would hang the last
    line off center."""
    work = ptxprint_project(tmp_path)
    (work / "colophon.usfm").write_text(
        r"""\id ROM
\c 16
\p \v 27 Prose """
        + "echo " * 60
        + r"""Amen.
\b
\esb \cat colophon\cat*
\p Colophon """
        + "echo " * 60
        + r"""Notice
\esbe
""",
        encoding="utf-8",
    )
    lines = typeset_lines(work, "colophon")
    start = next(i for i, line in enumerate(lines) if line[0].text == "Colophon")
    end = next(i for i, line in enumerate(lines) if line[-1].text == "Notice")
    prose, colophon = lines[:start], lines[start : end + 1]
    margin = min(float(line[0].attrib["xMin"]) for line in prose)
    measure = max(float(line[-1].attrib["xMax"]) for line in prose)
    assert len(colophon) > 2
    for line in colophon:
        assert (
            abs(
                float(line[0].attrib["xMin"])
                + float(line[-1].attrib["xMax"])
                - margin
                - measure
            )
            < 0.5
        ), line[0].text


def test_list_key_gap_and_hanging_indent(tmp_path: Path) -> None:
    work = ptxprint_project(tmp_path)
    # As the export sends a key: without the word space the gap replaces.
    (work / "listkeys.usfm").write_text(
        "\\id FRT\n\\m Unindented.\n\\p Proseindent.\n\\b\n"
        "\\li1 \\lik Label:\\lik*Description " + "echo " * 60 + "end.\n",
        encoding="utf-8",
    )
    lines = typeset_lines(work, "listkeys")

    def word(text: str) -> ET.Element:
        return next(w for line in lines for w in line if w.text == text)

    def left(w: ET.Element) -> float:
        return float(w.attrib["xMin"])

    assert abs(left(word("Label:")) - left(word("Unindented."))) < 0.15
    index = next(i for i, line in enumerate(lines) if word("Label:") in line)
    assert abs(left(lines[index + 1][0]) - left(word("Proseindent."))) < 0.15
    # Half an em of the 9-point list, unstretched on a justified line.
    gap = left(word("Description")) - float(word("Label:").attrib["xMax"])
    assert 4 < gap < 5
