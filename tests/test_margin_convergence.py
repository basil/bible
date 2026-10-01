"""Margin-note convergence at TeX precision and refusal at the pass cap."""

from types import SimpleNamespace

import pytest
from ptxprint.marginnotes import MarginNote, MarginNotes
from ptxprint import runjob

from bible import typeset
from bible.checks import CheckFailed
from patch_margin_convergence import patch


@pytest.mark.parametrize("offset", [0, 12.34567, -12.34567])
@pytest.mark.parametrize("shift_sp", [0, 0.00001, -0.00001, 1, -1, 2, -2, 65536])
def test_rerun_requires_more_than_one_scaled_point(tmp_path, offset, shift_sp):
    notes = MarginNotes()
    notes.pages = [
        [
            MarginNote(
                ref=f"GEN1.1-{i}",
                marker="f",
                hpos="inner",
                vpos="bottom",
                gap=8.5,
                width=68.3,
                height=10,
                depth=0,
                xoffset=0,
                yoffset=offset,
                pnum=0,
                xpos=100,
                ypos=400 - 20 * i,
                yshift=shift_sp / 65536,
            )
            for i in range(4)
        ]
    ]
    output = tmp_path / "notes.marginnotes"
    assert notes.outfile(output) == (abs(shift_sp) > 1)
    # All notes and their positions remain available to TeX and verification.
    restored = MarginNotes(output)
    assert len(restored.pages[0]) == 4
    assert restored.pages[0][0].yoffset == pytest.approx(
        offset - shift_sp / 65536, abs=0.0000051
    )


def test_crowded_notes_settle_after_their_offsets_are_applied(tmp_path):
    notes = MarginNotes(top=500, bot=0)
    notes.pages = [
        [
            MarginNote(
                ref=f"GEN1.1-{i}",
                marker="f",
                hpos="inner",
                vpos="bottom",
                gap=8.5,
                width=68.3,
                height=10,
                depth=0,
                xoffset=0,
                yoffset=0,
                pnum=0,
                xpos=100,
                ypos=100 - 5 * i,
            )
            for i in range(2)
        ]
    ]
    notes.processpages()
    output = tmp_path / "notes.marginnotes"
    assert notes.outfile(output)
    for note in notes.pages[0]:
        note.ypos += note.yshift
        note.yoffset -= note.yshift
        note.yshift = 0
    notes.processpages()
    assert not notes.outfile(output)
    first, second = notes.pages[0]
    assert first.ymin >= second.ymax


@pytest.mark.parametrize("unsettled", [False, True])
def test_typeset_refuses_unsettled_notes_even_with_cli_success(
    tmp_path, monkeypatch, unsettled
):
    project = tmp_path / "projects/BIBLE"
    project.mkdir(parents=True)
    pdf = project / "Bible.pdf"
    pdf.write_bytes(b"test PDF")

    def run(*args, **kwargs):
        (tmp_path / "ptxprint.log").write_text(
            (
                "ERROR Margin notes did not converge after 5 passes\n"
                if unsettled
                else "INFO Finished\n"
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(typeset.subprocess, "run", run)
    if unsettled:
        with pytest.raises(CheckFailed, match="Typesetting did not converge"):
            typeset.typeset(tmp_path, project)
    else:
        assert typeset.typeset(tmp_path, project) == pdf


def test_patch_refuses_changed_upstream(tmp_path):
    (tmp_path / "marginnotes.py").write_text("# upstream changed\n")
    with pytest.raises(RuntimeError, match="review the convergence patch"):
        patch(tmp_path)


@pytest.mark.parametrize(
    "max_runs, settles, expected_runs, layout_changes",
    [
        (5, True, 2, False),
        (5, False, 5, False),
        (1, False, 2, False),
        (5, True, 5, True),
    ],
)
def test_note_reruns_and_cap(
    tmp_path, monkeypatch, caplog, max_runs, settles, expected_runs, layout_changes
):
    job = runjob.RunJob.__new__(runjob.RunJob)
    printer = SimpleNamespace(
        incrementProgress=lambda **kw: None,
        get=lambda *args: 0,
        editFile_delayed=lambda *args: None,
    )
    job.printer = printer
    job.info = SimpleNamespace(printer=printer, getTextBlockSize=lambda: (500, 500, 0))
    job.tmpdir = str(tmp_path)
    job.maxRuns = max_runs
    job.forcedlooseness = None
    job.silent = True
    job.env = None
    job.res = 0
    job.nopdf = False
    passes = []
    converted = []
    job.xdvtopdf = lambda *args: converted.append(args)

    def xetex(*args, **kwargs):
        passes.append(args)
        # A different byte representation every pass must not override the
        # note solver's decision that the layout has settled.
        (tmp_path / "Bible.marginnotes").write_text(str(len(passes)))
        (tmp_path / "Bible.parlocs").write_text(
            rf"\@noteid{{7}}{{f}}{{n}}{{43}}{{1678212}}{{{16998254 + len(passes) % 2}}}"
            + (f"\npage={len(passes)}" if layout_changes else "")
        )
        return 0

    monkeypatch.setattr(runjob, "call", xetex)
    monkeypatch.setattr(runjob, "child_cpu_time", lambda *args: 0)
    monkeypatch.setattr(
        runjob,
        "tidymarginnotes",
        lambda *args, **kwargs: not settles or len(passes) == 1,
    )
    job.run_xetex("Bible.tex", "Bible.pdf")
    assert len(passes) == expected_runs
    success = settles and not layout_changes
    assert bool(converted) == success
    assert job.res == (0 if success else 1)
    assert ("Margin notes did not converge after" in caplog.text) == (not settles)
    assert ("Typesetting did not converge after" in caplog.text) == layout_changes


@pytest.mark.parametrize(
    "after, same",
    [
        (r"\@noteid{7}{f}{n}{43}{1678212}{16998255}", True),
        (r"\@noteid{7}{f}{n}{43}{1678211}{16998253}", True),
        (r"\@noteid{7}{f}{n}{43}{1678212}{16998256}", False),
        (r"\@noteid{8}{f}{n}{43}{1678212}{16998254}", False),
        (r"\@noteid{7}{x}{n}{43}{1678212}{16998254}", False),
        (r"\@noteid{7}{f}{n}{44}{1678212}{16998254}", False),
        ("", False),
        (r"\@noteid{7}{f}{n}{43}{1678212}{16998254}" + "\nextra", False),
    ],
)
def test_parloc_note_coordinate_tolerance(after, same):
    before = r"\@noteid{7}{f}{n}{43}{1678212}{16998254}"
    assert runjob._bible_same_cache(before, after, "parlocs") == same
    assert not runjob._bible_same_cache(before, after, "toc")


def test_parloc_other_coordinates_remain_exact():
    before = r"\@parend {0}{20517504}{27714133}{0.0pt}"
    after = r"\@parend {0}{20517504}{27714134}{0.0pt}"
    assert not runjob._bible_same_cache(before, after, "parlocs")
