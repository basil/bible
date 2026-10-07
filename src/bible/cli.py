"""The build's commands: validate the sources and the edition's decisions,
write the review, or typeset the sample or the full Bible, check it, and
publish it."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Sequence

from bible import paths, pipeline, policy, sources
from bible.project import write_project
from bible.publish import publish
from bible.review import review
from bible.toolchain import check_image
from bible.typeset import typeset
from bible.verify import check_processed, inspect_pdf

COMMANDS = ("validate", "review", *paths.OUTPUTS)


def prepared() -> tuple[sources.Sources, policy.Policy, pipeline.Edition]:
    read = sources.load()
    decisions = policy.load()
    return read, decisions, pipeline.prepare(read, decisions)


def validate() -> None:
    """Prepare the whole edition, which checks every source and decision."""
    _, _, edition = prepared()
    print("Validated the sources and the edition:", dict(edition.summary), flush=True)


def render(mode: str) -> None:
    """Typeset one edition in build/<mode>, check it, and publish it to dist/."""
    read, decisions, edition = prepared()
    documents = pipeline.export(edition, mode)
    check_image()
    base = paths.BUILD_DIR / mode
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    project, ids = write_project(mode, base, documents, decisions, read)
    pdf = typeset(base, project)
    check_processed(project, base, ids)
    report = inspect_pdf(pdf, base, project, ids, mode == "sample", decisions.witnesses)
    publish(mode, pdf, ids, report, decisions.title)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m bible", description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            validate()
        elif args.command == "review":
            review(*prepared())
        else:
            render(args.command)
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1
    return 0
