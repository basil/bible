"""The container image must match the checkout's pins."""

import shutil

import pytest

from bible import paths, toolchain
from bible.checks import CheckFailed


def test_stale_image(tmp_path):
    # The image's own copies, so that only the damaged archive differs from it.
    for name in ("Dockerfile", "requirements.txt", *toolchain.font_archives()):
        (tmp_path / name).parent.mkdir(exist_ok=True)
        shutil.copy(paths.OPT / name, tmp_path / name)
    (tmp_path / "sources/erewhon.zip").write_bytes(b"")
    with pytest.raises(CheckFailed, match="another sources/erewhon.zip"):
        toolchain.check_image(tmp_path)
