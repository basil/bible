"""Refusal of a PDF whose layout has not settled within the pass cap."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bible import project, typeset
from bible.checks import CheckFailed


@pytest.mark.parametrize("unsettled", [False, True])
@pytest.mark.parametrize(
    "output,pdfs,finished",
    [
        ("Screen", ["Bible.pdf"], "Bible.pdf"),
        ("Gray", ["Bible.pdf", "Bible_gray.pdf"], "Bible_gray.pdf"),
        ("CMYK", ["Bible.pdf", "Bible_cmyk_2up.pdf"], "Bible_cmyk_2up.pdf"),
        # A conversion that failed, and one that was not asked for.
        ("Gray", ["Bible.pdf"], None),
        ("Screen", ["Bible.pdf", "Bible_gray.pdf"], None),
        ("Gray", ["Bible.pdf", "Other.pdf"], None),
        ("Gray", ["Bible.pdf", "Bible_gray.pdf", "Bible_cmyk.pdf"], None),
    ],
)
def test_typeset_refuses_unsettled_layout_even_with_cli_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unsettled: bool,
    output: str,
    pdfs: list[str],
    finished: str | None,
) -> None:
    project_dir = tmp_path / project.PROJECT_DIR
    settings = project_dir / project.SETTINGS_DIR
    settings.mkdir(parents=True)
    (settings / "ptxprint.cfg").write_text(
        f"[snippets]\npdfoutput = {output}\n", encoding="utf-8"
    )
    for name in pdfs:
        (project_dir / name).write_bytes(b"test PDF")

    def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        console = kwargs["stdout"]
        assert hasattr(console, "write")
        console.write("Maximum runs exceeded\nDone\n" if unsettled else "Done\n")
        return subprocess.CompletedProcess([str(arg) for arg in args], 0)

    monkeypatch.setattr(subprocess, "run", run)
    if unsettled:
        with pytest.raises(CheckFailed, match="Typesetting did not converge"):
            typeset.typeset(tmp_path, project_dir)
    elif finished is None:
        with pytest.raises(CheckFailed, match="Expected XeTeX's PDF"):
            typeset.typeset(tmp_path, project_dir)
    else:
        assert typeset.typeset(tmp_path, project_dir) == project_dir / finished
