"""Publishing a checked PDF, or the books as USFM, to dist/."""

from __future__ import annotations

import shutil
import zipfile
from collections.abc import Sequence
from pathlib import Path

from bible import paths


def publish(mode: str, pdf: Path) -> None:
    """Stage a checked PDF and atomically replace the published copy."""
    target = paths.DIST_DIR / paths.OUTPUTS[mode]
    paths.DIST_DIR.mkdir(exist_ok=True)
    staged_pdf = target.with_suffix(".pdf.tmp")
    shutil.copyfile(pdf, staged_pdf)
    staged_pdf.replace(target)
    print("Wrote", target, flush=True)


def publish_usfm(books: Sequence[tuple[str, str]]) -> None:
    """Write the books to a zip, one file to a book numbered in the edition's
    order as eBible.org names them (01-GEN.usfm), and atomically replace the
    published copy. Every entry has the same date, so the same books make
    the same zip."""
    target = paths.DIST_DIR / paths.USFM_ZIP
    paths.DIST_DIR.mkdir(exist_ok=True)
    staged = target.with_suffix(".zip.tmp")
    with zipfile.ZipFile(staged, "w", zipfile.ZIP_DEFLATED) as archive:
        for number, (code, text) in enumerate(books, start=1):
            entry = zipfile.ZipInfo(f"{number:02d}-{code}.usfm", (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, text)
    staged.replace(target)
    print("Wrote", target, flush=True)
