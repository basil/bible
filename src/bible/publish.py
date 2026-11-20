"""Publishing a checked PDF to dist/."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from bible import paths
from bible.checks import require
from bible.files import read_json
from bible.toolchain import capture, run


def label_pages(pdf: Path, base: Path) -> Path:
    """A copy of the PDF whose page labels are its folios, so that a reader's
    page numbers are the book's: lowercase Roman in the front matter and
    Arabic from the Old Testament divider, which verification found and
    recorded in build/<command>/book-boundaries.json."""
    boundaries = read_json(base / "book-boundaries.json")
    main = [b["page"] for b in boundaries if b["printed_page"] == "1"]
    require(len(main) == 1, "No single page where the Arabic folios begin")
    # Beside the build's logs, not among PTXprint's PDFs, which typeset counts.
    labelled = base / f"{pdf.stem}-labelled.pdf"
    # The PDF declares PDF/A, which wants an end of line before each
    # endstream; and the same PDF is to give the same copy, /ID and all.
    run(
        "qpdf",
        "--newline-before-endstream",
        "--deterministic-id",
        pdf,
        "--set-page-labels",
        "1:r",
        f"{main[0]}:D",
        "--",
        labelled,
    )
    with (base / "qpdf-labelled.log").open("w", encoding="utf-8") as log:
        run("qpdf", "--check", labelled, stdout=log, stderr=subprocess.STDOUT)
    labels = json.loads(capture("qpdf", "--json", "--json-key=pagelabels", labelled))
    require(
        [(r["index"], r["label"]["/S"]) for r in labels["pagelabels"]]
        == [(0, "/r"), (main[0] - 1, "/D")],
        "Page labels not set as the folios run",
    )
    return labelled


def publish(mode: str, pdf: Path) -> None:
    """Stage a checked PDF and atomically replace the published copy."""
    target = paths.DIST_DIR / paths.OUTPUTS[mode]
    paths.DIST_DIR.mkdir(exist_ok=True)
    staged_pdf = target.with_suffix(".pdf.tmp")
    shutil.copyfile(pdf, staged_pdf)
    staged_pdf.replace(target)
    print("Wrote", target, flush=True)
