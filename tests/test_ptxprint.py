"""Regression checks against the pinned PTXprint, without invoking TeX."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from patch_rerun_limit import patch
from ptxprint import runjob
from ptxprint.marginnotes import tidymarginnotes


def test_rerun_limit_patch_refuses_changed_upstream(tmp_path: Path) -> None:
    path = tmp_path / "runjob.py"
    path.write_text("# upstream changed\n")
    with pytest.raises(RuntimeError, match="review the rerun-limit patch"):
        patch(path)


@pytest.mark.parametrize("reason", ["margin notes", "chapter positions", "TeX log"])
@pytest.mark.parametrize("settles", [False, True])
def test_rerun_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    reason: str,
    settles: bool,
) -> None:
    passes = 0
    pdfs = []

    def call(*args: object, **kwargs: object) -> int:
        nonlocal passes
        passes += 1
        # Settling on pass five must succeed, even at the limit.
        position = min(passes, 4) if settles else passes
        (tmp_path / "Bible.parlocs").write_text(
            str(position) if reason == "chapter positions" else "stable"
        )
        (tmp_path / "Bible.marginnotes").write_text("stable")
        return 0

    printer = SimpleNamespace(
        incrementProgress=lambda **kwargs: None,
        get=lambda key, default=None: default,
        editFile_delayed=lambda *args: None,
    )
    info = SimpleNamespace(
        printer=printer,
        dict={},
        asBool=lambda key: False,
        getTextBlockSize=lambda: (600, 500, 100),
    )
    job = SimpleNamespace(
        maxRuns=5,
        tmpdir=str(tmp_path),
        printer=printer,
        info=info,
        forcedlooseness=None,
        silent=True,
        env={},
        nopdf=False,
        res=0,
        readfile=lambda path: Path(path).read_text() if Path(path).exists() else "",
        parselog=lambda *args, **kwargs: (
            [],
            reason == "TeX log" and (not settles or passes < 5),
        ),
        xdvtopdf=lambda *args: pdfs.append(args),
    )
    monkeypatch.setattr(runjob, "call", call)
    monkeypatch.setattr(runjob, "child_cpu_time", lambda runner: 0)
    monkeypatch.setattr(
        runjob,
        "tidymarginnotes",
        lambda *args, **kwargs: reason == "margin notes"
        and (not settles or passes < 5),
    )
    with caplog.at_level(logging.ERROR):
        runjob.RunJob.run_xetex(job, "Bible.tex", "Bible.pdf")
    assert passes == 5
    if settles:
        assert job.res == 0
        assert len(pdfs) == 1
        assert not caplog.records
    else:
        assert job.res != 0, (reason, job.rerunReasons)
        assert not pdfs
        assert "did not converge" in caplog.text
        assert reason in caplog.text


@pytest.mark.parametrize("max_runs", [0, 1])
def test_managed_single_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, max_runs: int
) -> None:
    """Page filling and quick runs may intentionally leave changed caches."""
    printer = SimpleNamespace(
        incrementProgress=lambda **kwargs: None,
        get=lambda key, default=None: default,
        editFile_delayed=lambda *args: None,
    )

    def call(*args: object, **kwargs: object) -> int:
        (tmp_path / "Bible.parlocs").write_text("changed")
        return 0

    job = SimpleNamespace(
        maxRuns=max_runs,
        tmpdir=str(tmp_path),
        printer=printer,
        info=SimpleNamespace(printer=printer),
        forcedlooseness=None,
        silent=True,
        env={},
        nopdf=True,
        res=0,
        readfile=lambda path: Path(path).read_text() if Path(path).exists() else "",
        parselog=lambda *args, **kwargs: ([], True),
    )
    monkeypatch.setattr(runjob, "call", call)
    monkeypatch.setattr(runjob, "child_cpu_time", lambda runner: 0)
    runjob.RunJob.run_xetex(job, "Bible.tex", "Bible.pdf")
    assert job.res == 0


def test_margin_notes_reach_fixed_point(tmp_path: Path) -> None:
    """Overlapping notes and fractional-sp offsets must stop requesting reruns."""
    path = tmp_path / "test.marginnotes"
    path.write_text(
        "".join(
            r"\@marginnote" + "{" + ref + "}{f}{outer}{top}{5pt}{50pt}{20pt}{0pt}{0pt}"
            "{0.000003pt}{1}{3276800}{" + str(y) + "}\n"
            for ref, y in (("GEN1.1", 300 * 65536), ("GEN1.2", 295 * 65536))
        )
    )
    assert tidymarginnotes(str(path), top=500, bot=100)
    settled = path.read_bytes()
    for _ in range(3):
        assert not tidymarginnotes(str(path), top=500, bot=100)
        assert path.read_bytes() == settled
