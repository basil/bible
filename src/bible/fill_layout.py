"""Fill a book and check the layout it ends on: a short page before a heading is forced."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from ptxprint import multiprint

# A worker's report: the book, its worker, whether the book is complete, the
# message, and the final layout's unresolved and protected pages.
Filled = tuple[str, str, bool, str, list[int], list[int]]


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
    paragraphs: Any, underfills: Iterable[Sequence[int] | None]
) -> tuple[list[int], list[int]]:
    """Return unresolved and protected pages, using physical one-based pages.

    The filler measures every layout it runs (PTXFiller.underfills): the lines
    each column of a physical page has free, or nothing for a page unmeasured.
    """
    unresolved: list[int] = []
    protected: list[int] = []
    for page, columns in enumerate(underfills, start=1):
        if page >= paragraphs.numPages():  # The last page may be short.
            break
        for column, lines in enumerate(columns or ()):
            if lines <= 0:
                continue
            target = (
                protected if column == 0 and forced(paragraphs, page) else unresolved
            )
            target.append(page)
    return sorted(set(unresolved)), sorted(set(protected))


def fill(job: Any) -> Filled:
    """In a pool worker: fill a book, and judge it by the layout the filler ends on.

    PTXprint returns a status and a message, and its record of failed pages
    outlives the reflow that fixes them. But its filler lays the whole book out
    with the adjustments it chose before it returns, and keeps that layout's
    measurements for whoever calls it, so the pool's worker calls it here
    rather than through PTXprint's own job.

    The filler can stop before a book's end. To save time it lays a book out
    only as far as a chapter a little past the page it is filling. It decides
    whether such a layout covers the whole book after TeX has run, from the
    chapters' pages, which that run has just rewritten. Where the last
    chapters moved up a page, a layout cut before the last chapter passes for
    the whole book, and the pages after it are never filled. Restarted, the
    filler goes on from the first short page with the adjustments it chose.
    """
    book = job.books[0]
    # The pool's worker keeps one filler, with its own directory and queues.
    filler = multiprint._worker_ctx.get_printer(job)

    def failed(message: str) -> Filled:
        return (book, filler.nid, False, message, [], [])

    status, message = filler.solve(book) or (None, f"{book} is not in the project")
    if status is None:  # The book could not be typeset.
        return failed(message)
    # The search or the last layout was cut short.
    if filler.timedout or filler.cancelled:
        return failed(message)
    # TeX failed on the first layout, so the filler searched nothing.
    initial = filler.hooks.basestate.layout
    if not initial.pages or initial.result != 0:
        return failed(message)
    unresolved, protected = remaining(filler.parlocs, filler.underfills)
    restarts = 0
    # A restart that leaves as many pages short as it found will not do better.
    while unresolved:
        left = len(unresolved)
        status, message = filler.solve(book, restart=True)
        if status is None or filler.timedout or filler.cancelled:
            return failed(message)
        restarts += 1
        unresolved, protected = remaining(filler.parlocs, filler.underfills)
        if len(unresolved) >= left:
            break
    if not status and not unresolved:
        message = f"Final layout verified; protected breaks {protected}"
    if restarts:
        message += f"; restarted {restarts} time{'s' * (restarts > 1)}"
    return (book, filler.nid, not unresolved, message, unresolved, protected)
