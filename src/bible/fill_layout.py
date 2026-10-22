"""Check the filler's actual output: a short page before a heading is forced."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ptxprint.parlocs import Paragraphs
from ptxprint.runjob import RunJob, unlockme
from ptxprint.texlog import readUnderfills

from bible.checks import require


def heading(paragraph: Any) -> bool:
    """Does TeX keep this paragraph with the one after it?

    PTXprint sets a title, a section heading, or any other non-verse paragraph
    outside an introduction (an introduction marker begins with i, as its TeX
    tests) in a heading box, and forbids a page break after the box
    (ptx-para-style.tex). The type it typeset each paragraph as is recorded in
    the paragraph locations.
    """
    kind = paragraph.partype
    return kind in {"title", "section"} or (
        kind == "other" and not paragraph.mrk.startswith("i")
    )


def forced(paragraphs: Any, page: int) -> bool:
    """Is the break at the end of a page forced by a heading opening the next?

    TeX breaks a page at the last place it may, so a page ends before a heading
    only when the heading, with the lines it keeps, cannot follow the page's
    last line; the filler cannot reflow a heading. A page that ends inside a
    paragraph, or before a verse paragraph, could have been filled.
    """
    following = next(iter(paragraphs.getParas(page + 1)), None)
    return following is not None and heading(following[0])


def remaining(
    paragraphs: Any, records: Iterable[tuple[int, str, float, float, float]]
) -> tuple[list[int], list[int]]:
    """Return unresolved and protected pages, using physical one-based pages."""
    unresolved: list[int] = []
    protected: list[int] = []
    for printed, column, available, used, leading in records:
        if printed <= 0:
            continue
        page = paragraphs.pnums.get(printed, printed)
        if page >= paragraphs.numPages():  # The last page may be short.
            continue
        if int((available - used) / leading + 0.4) <= 0:
            continue
        target = protected if column == "A" and forced(paragraphs, page) else unresolved
        target.append(page)
    return sorted(set(unresolved)), sorted(set(protected))


def inspect(stem: Path) -> tuple[list[int], list[int]]:
    paragraphs = Paragraphs()
    paragraphs.readParlocs(str(stem.with_suffix(".parlocs")), False)
    require(paragraphs.numPages() > 0, f"No page data in {stem}")
    status = stem.with_suffix(".status")
    require(status.exists(), f"Missing page-filler status: {status}")
    return remaining(paragraphs, readUnderfills(str(status)))


def probe(view: Any, book: str) -> tuple[list[int], list[int]]:
    """Recheck an interrupted book's saved adjustments with one diagnostic pass."""
    values: dict[str, Any] = {key: False for key in """
        c_inclFrontMatter c_autoToC c_frontmatter c_inclMaps c_useSectIntros
        c_makeCoverPage c_colophon c_inclBackMatter c_extradvproc
        c_inclSettingsInPDF c_applyWatermark c_cropmarks c_extractInserts
        c_printArchive c_quickRun
    """.split()}
    values.update(
        fcb_pagesPerSpread=1,
        fcb_outputFormat="Screen",
        c_allowUnbalanced=True,
        r_book="single",
        ecb_book=book,
        t_chapfrom="1",
        t_chapto="200",
    )
    old = {key: view.get(key) for key in values}
    cwd = os.getcwd()  # RunJob changes into its working directory.
    try:
        for key, value in values.items():
            view.set(key, value)
        view.adjlists.pop(book, None)  # Reload choices written by the worker.
        view.get_adjlist(book).createTriggerlist()
        unlockme()
        job = RunJob(view, view.scriptsdir, view.scriptsdir, view.args)
        job.norun = job.nopdf = job.notracing = job.silent = job.nothreads = True
        job.doit(noview=True)
        job.maxRuns = 0
        job.run_xetex(job.outfname, job.pdffile)
        require(job.res == 0, f"Cached {book} diagnostic failed")
        return inspect(Path(job.tmpdir, job.outfname).with_suffix(""))
    finally:
        os.chdir(cwd)
        for key, value in old.items():
            view.set(key, value)
