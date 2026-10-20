"""Check actual filler output, including space protected for a major heading."""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ptxprint.parlocs import Paragraphs
from ptxprint.runjob import RunJob, unlockme
from ptxprint.texlog import readUnderfills

from bible.checks import require

# These paragraphs form the heading group of a kathisma and its first psalm.
HEADINGS = {"ms1", "ms2", "cl", "d"}


def protected_heading(
    paragraphs: Any, page: int, available: float, leading: float
) -> bool:
    """Does the next page's major heading need more space than was left?"""
    following = list(paragraphs.getParas(page + 1))
    if not following or following[0][0].mrk != "ms1":
        return False
    top = following[0][1].ystart
    for paragraph, rect in following:
        if paragraph.mrk in HEADINGS:
            continue
        if paragraph.mrk not in {"p", "q1", "q2", "q3", "q4"}:
            return False
        if rect.lines < 1:
            return False
        # Use only the first scripture line. Requiring an entire verse or
        # paragraph would incorrectly excuse a gap in which its start fits.
        bottom = rect.yend + (rect.lines - 1) * leading
        return bool(top - bottom > available + 1 / 65536)
    return False


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
        gap = available - used
        if int(gap / leading + 0.4) <= 0:
            continue
        target = (
            protected
            if column == "A" and protected_heading(paragraphs, page, gap, leading)
            else unresolved
        )
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
