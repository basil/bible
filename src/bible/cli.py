"""The build's commands: validate the sources, or typeset the sample or the
full Bible, check it, and publish it."""

import argparse
import shutil
import subprocess
import sys

from bible import paths
from bible.project import write_project
from bible.publish import publish
from bible.review import notes_review
from bible.toolchain import check_image
from bible.typeset import typeset
from bible.validate import validate
from bible.verify import check_processed, inspect_pdf


def render(mode):
    """Typeset one edition in build/<mode>, check it, and publish it to dist/."""
    archives = validate()
    check_image()
    base = paths.BUILD_DIR / mode
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    project, ids = write_project(mode, base, archives)
    pdf = typeset(base, project)
    check_processed(project, base, ids)
    report = inspect_pdf(pdf, base, project, ids, mode == "sample")
    publish(mode, pdf, ids, report)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m bible", description=__doc__)
    parser.add_argument(
        "command",
        choices=["validate", "notes-review", *paths.OUTPUTS],
        help="validate the sources, write the notes review, or build dist/sample.pdf or dist/bible.pdf",
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            validate()
        elif args.command == "notes-review":
            notes_review()
        else:
            render(args.command)
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print("ERROR:", exc, file=sys.stderr)
        return 1
    return 0
