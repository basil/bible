"""The container image must match the checkout's pins."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from bible import paths, toolchain
from bible.checks import CheckFailed


def test_stale_image(tmp_path: Path) -> None:
    # The image's own copies, so that only the damaged archive differs from it.
    for name in toolchain.image_inputs():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(paths.OPT / name, tmp_path / name)
    (tmp_path / "sources/erewhon.zip").write_bytes(b"")
    with pytest.raises(CheckFailed, match="another sources/erewhon.zip"):
        toolchain.check_image(tmp_path)
