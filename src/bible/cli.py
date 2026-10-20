"""The build's commands: validate the sources and the edition's decisions,
write the review, or typeset the sample or the full Bible, check it, and
publish it."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from contextlib import nullcontext

from bible import export, fill, paths, pipeline, policy, sources, usj, web
from bible.project import write_project
from bible.publish import publish
from bible.review import review
from bible.toolchain import check_image
from bible.typeset import typeset
from bible.verify import check_processed, inspect_pdf

COMMANDS = ("validate", "review", "web", *paths.OUTPUTS)


def prepared() -> pipeline.Edition:
    return pipeline.prepare(sources.load(), policy.load())


def validate() -> None:
    """Prepare the whole edition and write it as USFM, which checks every
    source and decision."""
    edition = prepared()
    export.export(edition, "pdf")
    print("Validated the sources and the edition:", dict(edition.summary), flush=True)


def render(command: str, *, jobs: int = fill.WORKERS, fresh: bool = False) -> None:
    """Typeset one edition in build/<command>, check it, and publish it to dist/."""
    filling = command == "pdf"
    with fill.locked() if filling else nullcontext():
        check_image()
        edition = prepared()
        mode = "sample" if command == "sample" else "pdf"
        documents = export.grouped(edition, export.prepared(edition, mode))
        render_project(command, mode, edition, documents, jobs=jobs, fresh=fresh)


def render_project(
    command: str,
    mode: str,
    edition: pipeline.Edition,
    documents: Sequence[tuple[str, usj.Document]],
    *,
    jobs: int,
    fresh: bool,
) -> None:
    started = time.monotonic()
    base = paths.BUILD_DIR / command
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    project, ids = write_project(mode, base, documents, edition)
    report: fill.Report | None = None
    try:
        if command == "pdf":
            books = [b for b in ids if b in edition.scripture]
            report = fill.run(project, books, jobs, fresh)
        pdf = typeset(base, project)
        check_processed(project, base, ids)
        pages = inspect_pdf(
            pdf, base, project, ids, mode == "sample", edition.policy.witnesses
        )
        publish(command, pdf)
        if report is not None:
            report.update(
                {
                    "status": "complete",
                    "build_seconds": round(time.monotonic() - started),
                    "pages": pages,
                }
            )
    except BaseException as error:
        if report is not None:
            report.update({"status": "failed", "error": str(error)})
        raise
    finally:
        if report is not None:
            fill.save(report)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m bible", description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument(
        "--jobs", type=int, help=f"Page-filler workers (default: {fill.WORKERS})"
    )
    parser.add_argument(
        "--fresh", action="store_true", help="Discard page-filler cache"
    )
    args = parser.parse_args(argv)
    if args.jobs is not None and args.jobs < 1:
        parser.error("--jobs must be positive")
    if args.command != "pdf" and (args.fresh or args.jobs is not None):
        parser.error("Page-filler options require the pdf command")
    try:
        if args.command == "validate":
            validate()
        elif args.command == "review":
            review(prepared())
        elif args.command == "web":
            check_image()
            web.write(prepared(), paths.WEB_DIR)
        else:
            render(args.command, jobs=args.jobs or fill.WORKERS, fresh=args.fresh)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1
    return 0
