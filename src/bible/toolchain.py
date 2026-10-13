"""The container image the build runs in: its pinned tools and fonts, and the
refusal to typeset in an image built from other pins than the checkout's."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import IO

from bible import paths
from bible.checks import require


def run(
    *args: str | int | Path,
    stdout: IO[str] | int | None = None,
    stderr: IO[str] | int | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [str(a) for a in args], check=True, stdout=stdout, stderr=stderr
    )


def capture(*args: str | int | Path) -> str:
    return subprocess.check_output([str(a) for a in args], text=True)


def font_archives() -> tuple[str, ...]:
    """The font archives the image was built from, relative to /opt as they are
    to the checkout. The image build checks their hashes; outside it there are none."""
    return tuple(
        str(p.relative_to(paths.OPT)) for p in sorted(paths.FONT_ARCHIVES.glob("*.zip"))
    )


def font_build_inputs() -> tuple[str, ...]:
    """Assembly and notices are image inputs, checked alongside font pins."""
    return tuple(
        str(p.relative_to(paths.OPT))
        for p in sorted(paths.FONT_SCRIPTS.glob("*"))
        if p.suffix in {".py", ".txt"}
    )


def image_inputs() -> tuple[str, ...]:
    """Every checkout file whose copy in the image must match it."""
    return ("Dockerfile", "requirements.txt", *font_build_inputs(), *font_archives())


def check_image(root: Path = paths.ROOT) -> None:
    require(
        paths.UPSTREAM.exists(), "Run this command through Make (make bootstrap first)"
    )
    # The image keeps the pins it was built from; a stale image would typeset
    # with other tools or fonts than the ones pinned here.
    for name in image_inputs():
        require(
            (paths.OPT / name).read_bytes() == (root / name).read_bytes(),
            f"The image was built from another {name}; run make bootstrap",
        )
