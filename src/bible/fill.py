"""Run the pinned page filler, reusing only matching per-book checkpoints."""

from __future__ import annotations

import fcntl
import os
import queue
import shutil
import signal
import sys
import time
from collections.abc import Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, wait
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from ptxprint.main import main as ptxprint_main
from ptxprint.multiprint import MultiPrint
from ptxprint.utils import BuildParams
from ptxprint.view import ViewModel

from bible import fill_cache, fill_layout, paths, typeset
from bible.checks import require
from bible.files import write_json
from bible.project import ADJUSTMENTS_DIR, SETTINGS_DIR

WORKERS = 4
Result = tuple[str, str | None, bool, str, list[int]]


class Report(TypedDict):
    books: int
    reused: int
    completed: int
    pending: int
    status: Literal["filling", "typesetting", "complete", "failed"]
    results: list[Result]
    protected_breaks: dict[str, list[int]]
    elapsed_seconds: NotRequired[int]
    remaining_seconds: NotRequired[int | None]
    progress: NotRequired[dict[str, dict[str, Any]]]
    build_seconds: NotRequired[int]
    pages: NotRequired[int]
    error: NotRequired[str]


def save(report: Report) -> None:
    write_json(paths.BUILD_DIR / "page-fill/report.json", report)


@contextmanager
def locked() -> Iterator[None]:
    """One filler owns the temporary projects and cache at a time."""
    paths.BUILD_DIR.mkdir(exist_ok=True)
    with (paths.BUILD_DIR / "page-fill.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another page filler is running") from None
        yield


def worker_result(value: Any) -> Result:
    """The patched worker lists its unresolved pages after upstream's fields;
    upstream's early exits (a timeout, a cancellation) list none."""
    book, worker, success, message, *rest = value
    return (book, worker, success, message, rest[0] if rest else [])


def successful(result: Result) -> bool:
    """The patched API exposes unresolved pages separately from its boolean."""
    return result[2] and not result[4]


def drained(channel: Any) -> Iterator[Any]:
    while True:
        try:
            yield channel.get_nowait()
        except queue.Empty:
            return


def stopped(signum: int, frame: Any) -> None:
    # Not an Exception, which a handler for a book's failure would swallow.
    raise KeyboardInterrupt(f"Page filling interrupted by signal {signum}")


def run(project: Path, books: list[str], jobs: int, fresh: bool) -> Report:
    """Fill the project's books in a copy of it, and put their adjustments in it."""
    base = paths.BUILD_DIR / "page-fill"
    cache = paths.BUILD_DIR / "page-fill-cache"
    if fresh and cache.exists():
        shutil.rmtree(cache)
    if base.exists():
        shutil.rmtree(base)
    base.mkdir()
    identities = fill_cache.keys(project, books)
    restored = fill_cache.restore(cache, project, identities)
    completed = set(restored)
    pending = [book for book in books if book not in completed]
    results: list[Result] = []
    report = Report(
        books=len(books),
        reused=len(completed),
        completed=len(completed),
        pending=len(pending),
        status="filling",
        results=results,
        protected_breaks={
            book: entry["protected_breaks"]
            for book, entry in restored.items()
            if entry["protected_breaks"]
        },
    )
    save(report)
    print(
        f"Page filler: {len(completed)} cached, {len(pending)} pending; {jobs} workers",
        flush=True,
    )
    if not pending:
        report["status"] = "typesetting"
        save(report)
        return report

    # The filler works on a copy, so that the project typeset at the end is
    # as it was written. Workers run one directory deeper than normal rendering.
    work = base / "projects/BIBLE"
    shutil.copytree(project, work)
    (work / "local").mkdir()
    (work / "local/shared").symlink_to("../shared", target_is_directory=True)
    with (work / SETTINGS_DIR / "ptxprint-mods.tex").open("a") as mods:
        mods.write("\n\\nolotwritetrue\n")

    def checkpoint(changed: Iterable[str]) -> None:
        """Cache those of the changed books that are complete; save the report."""
        report.update(
            {"completed": len(completed), "pending": len(books) - len(completed)}
        )
        fill_cache.snapshot(
            cache,
            work,
            {b: identities[b] for b in changed},
            completed,
            report["protected_breaks"],
        )
        save(report)

    private = typeset.environment(base)
    environment = {key: os.environ.get(key) for key in private}
    os.environ.update(private)
    argv = sys.argv
    pool = None
    handler = signal.signal(signal.SIGTERM, stopped)
    started = time.monotonic()
    progress: dict[str, dict[str, Any]] = {}
    try:
        # The pinned CLI's fill command waits for every book, without
        # checkpoints or progress. Its ViewModel plus MultiPrint API provide
        # the supported primitives.
        sys.argv = typeset.command(
            work, base / "filler.log", "fill", "-b", " ".join(pending)
        )
        view = ptxprint_main(retview=True, viewClass=ViewModel)
        sys.argv = argv
        view.savePics()
        view.saveStyles()
        view.saveAdjlists()
        params = BuildParams(
            prjtree=view.prjTree,
            config=view.userconfig,
            macrosdir=view.scriptsdir,
            scriptsdir=view.scriptsdir,
            args=view.args,
            restart=False,
            pid=view.project.prjid,
            guid=view.project.guid,
            cfgid=view.cfgid,
            timeout=None,
            loglevel=20,
        )
        pool = MultiPrint(numproc=jobs, progress=True)
        pool.submit_fill_jobs(pending, params, stop=False)
        report["progress"] = progress
        last_save = time.monotonic()
        sizes = {book: (work / f"{book}.usfm").stat().st_size for book in pending}
        while pool.pending_futures:
            wait(list(pool.pending_futures), timeout=60, return_when=FIRST_COMPLETED)
            for event in drained(pool.progress_q):
                progress[event.book] = dict(vars(event))
            for _ in drained(pool.cpu_q):  # Load reports, for the GUI.
                pass
            for future, job in list(pool.pending_futures.items()):
                if not future.done():
                    continue
                del pool.pending_futures[future]
                book = job.books[0]
                try:
                    result = worker_result(future.result())
                except Exception as error:
                    result = (book, None, False, str(error), [])
                results.append(result)
                if successful(result):
                    completed.add(book)
                print(f"Page filler {book}: {result[3]}", flush=True)
                checkpoint([book])
            elapsed = time.monotonic() - started
            if time.monotonic() - last_save >= 60 or not pool.pending_futures:
                done = sum(sizes[b] for b in pending if b in completed)
                remaining = sum(sizes.values()) - done
                eta = (
                    elapsed * remaining / done
                    if done and len(results) >= 4 and elapsed >= 60
                    else None
                )
                report["elapsed_seconds"] = round(elapsed)
                report["remaining_seconds"] = round(eta) if eta is not None else None
                save(report)
                estimate = (
                    f"; about {eta/60:.0f} minutes of filling remain"
                    if eta is not None
                    else ""
                )
                print(
                    f"Page filler: {len(completed)}/{len(books)} complete, {elapsed/60:.1f} minutes elapsed{estimate}",
                    flush=True,
                )
                last_save = time.monotonic()
        # A failed trial need not describe the final saved choices. Check
        # those choices afresh after all workers stop writing shared styles.
        reprobed = [i for i, result in enumerate(results) if result[4]]
        for i in reprobed:
            book, worker, success, message, _ = results[i]
            unresolved, protected = fill_layout.probe(view, book)
            report["protected_breaks"][book] = protected
            if unresolved:
                results[i] = (book, worker, success, message, unresolved)
            else:
                message = f"Final layout verified; protected breaks {protected}"
                results[i] = (book, worker, True, message, [])
                completed.add(book)
        report["elapsed_seconds"] = round(time.monotonic() - started)
        checkpoint(results[i][0] for i in reprobed)
        require(
            len(results) == len(pending) and all(successful(r) for r in results),
            "Page filling failed or left unresolved pages; see build/page-fill/report.json",
        )
        if (work / ADJUSTMENTS_DIR).exists():
            shutil.copytree(
                work / ADJUSTMENTS_DIR, project / ADJUSTMENTS_DIR, dirs_exist_ok=True
            )
        report["status"] = "typesetting"
        return report
    except BaseException as error:
        if pool is not None:
            pool.terminate()
        report.update({"status": "failed", "error": str(error)})
        raise
    finally:
        if pool is not None:
            pool.teardown()
        checkpoint(pending)
        signal.signal(signal.SIGTERM, handler)
        sys.argv = argv
        for key, value in environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
