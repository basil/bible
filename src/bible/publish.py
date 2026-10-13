"""Publishing a checked PDF to dist/."""

from __future__ import annotations

import shutil
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
