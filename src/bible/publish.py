"""Publishing a checked PDF, or the books as USFM, to dist/."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
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


@contextmanager
def staged(target: Path) -> Iterator[Path]:
    """A file of its own beside the target, readable by all, that atomically
    replaces the target once written, so that runs that overlap never expose
    each other's partial copies, and that is removed if writing it fails."""
    target.parent.mkdir(exist_ok=True)
    handle, name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
    os.close(handle)
    path = Path(name)
    try:
        yield path
        path.chmod(0o644)
        path.replace(target)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    print("Wrote", target, flush=True)


def publish(mode: str, pdf: Path) -> None:
    """Stage a checked PDF and atomically replace the published copy."""
    with staged(paths.DIST_DIR / paths.OUTPUTS[mode]) as path:
        shutil.copyfile(pdf, path)


def publish_usfm(books: Sequence[tuple[str, str]]) -> None:
    """Write the books to a zip, one file to a book numbered in the edition's
    order (01-GEN.usfm), after the form, not the numbers, of eBible.org's
    file names, and atomically replace the published copy. Every entry has
    the same date and is readable by all, so the same books make the same
    zip."""
    with staged(paths.DIST_DIR / paths.USFM_ZIP) as path:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for number, (code, text) in enumerate(books, start=1):
                entry = zipfile.ZipInfo(
                    f"{number:02d}-{code}.usfm", (1980, 1, 1, 0, 0, 0)
                )
                entry.compress_type = zipfile.ZIP_DEFLATED
                # Without a mode, zipfile writes rw------- (0600).
                entry.external_attr = 0o644 << 16
                archive.writestr(entry, text)
