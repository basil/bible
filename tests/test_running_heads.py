"""Render headers and bookmarks with the pinned PTXprint formatters."""

import json
from pathlib import Path

from bible import paths
from bible.toolchain import capture, run


def test_running_heads_render_page_marks(tmp_path: Path) -> None:
    # Read the pinned bookmark definitions without loading the paragraph
    # engine around them. The formatters themselves are upstream code.
    upstream = (paths.UPSTREAM / "src/ptx-para-style.tex").read_text()
    bookmarks = tmp_path / "bookmarks.tex"
    bookmarks.write_text(
        "\n".join(
            upstream.split(f"%+cpar_{section}\n", 1)[1].split(f"%-cpar_{section}", 1)[0]
            for section in ("pdfbookmark", "pdfchaptermark")
        )
    )
    source = (
        r"""
\catcode`\@=11
\let\x@\expandafter
\def\trace#1#2{}
\def\traceifset#1{}
\def\traceifcheck#1{}
\def\def@cseq#1#2{\expandafter\def\csname #1\endcsname{#2}}
\newif\ifdiglot
\input BOOKMARKS
\def\liter@lspecials{}
\def\g@tdstat{}
\newif\ifOneChapBook
\def\t@tle{title}
\def\intr@{intro}
\input REFERENCES
% As PTXprint's settings fill them from layout.ini, before ptxprint-mods.tex.
\def\RHevenleft{\firstref}
\def\RHoddright{\lastref}
\input HELPER
\BibleRunningHead{Daniel}{0}{Susanna}
\BibleRunningHead{Daniel}{13}{Bel and the Dragon}
\font\body="OLEBFont" at 11pt
\body
\headline={}\footline={}
\hsize=400pt
% The parser is ahead of the page being shipped.
\def\ch@pter{12}
\def\Check#1#2{%
  \def\p@gefirstmark{#1}\def\p@gebotmark{#2}%
  \noindent\hbox{[\RHevenleft]}\quad\hbox{[\RHoddright]}\par}
\Check{Daniel:0:2}{Daniel:0:20}
\Check{Daniel:13:2}{Daniel:13:20}
\Check{Daniel:0:60}{Daniel:1:2}
\Check{Daniel:12:13}{Daniel:13:2}
\Check{Genesis:1:1}{Daniel:12:13}
\Check{}{}
\Check{title}{intro}
% PTXprint reads chapter and verse digits with category code 11.
\begingroup
\catcode`0=11 \catcode`3=11 \catcode`1=11
\Check{Daniel:0:1}{Daniel:13:1}
\endgroup
\Check{Daniel:1:1-3}{Daniel:12:1-3}
% Exercise the original verse-bridge formatting on the fallback path too.
\VerseRefstrue
\def\ChapterVerseSeparator{:}
\catcode`-=11
\Check{Daniel:1:1-3}{Daniel:12:1-3}
\catcode`-=12
\def\id@@@{DAG}
\def\book{Daniel}
\pdfb@@kmark
\def\ch@pter{0}\pdfch@ptermark
\def\ch@pter{1}\pdfch@ptermark
\def\ch@pter{12}\pdfch@ptermark
\def\ch@pter{13}\pdfch@ptermark
\bye
""".replace("HELPER", str(paths.CONFIG_DIR / "running-heads.tex"))
        .replace("BOOKMARKS", str(bookmarks))
        .replace("REFERENCES", str(paths.UPSTREAM / "src/ptx-references.tex"))
    )
    tex = tmp_path / "heads.tex"
    tex.write_text(source)
    run(
        "xetex",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={tmp_path}",
        tex,
    )
    text = capture("pdftotext", "-layout", tmp_path / "heads.pdf", "-")
    assert [" ".join(line.split()) for line in text.splitlines() if line.strip()] == [
        "[Susanna] [Susanna]",
        "[Bel and the Dragon] [Bel and the Dragon]",
        "[Susanna] [Daniel 1]",
        "[Daniel 12] [Bel and the Dragon]",
        "[Genesis 1] [Daniel 12]",
        "[] []",
        "[] []",
        "[Susanna] [Bel and the Dragon]",
        "[Daniel 1] [Daniel 12]",
        "[Daniel 1:1] [Daniel 12:3]",
    ]
    pdf = json.loads(capture("qpdf", "--json", tmp_path / "heads.pdf"))
    outline = pdf["outlines"]
    assert [entry["title"] for entry in outline] == ["Daniel"]
    assert [entry["title"] for entry in outline[0]["kids"]] == [
        "Susanna",
        "Daniel 1",
        "Daniel 12",
        "Bel and the Dragon",
    ]
