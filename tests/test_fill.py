"""Cache isolation, strict solver acceptance and preserving checked downloads."""

from __future__ import annotations

import json
import os
import queue
import shutil
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from ptxprint import page_filler
from ptxprint.adjlist import AdjList

from bible import cli, fill, fill_cache, fill_layout, paths
from bible.checks import CheckFailed
from bible.project import SETTINGS_DIR


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    monkeypatch.setattr(paths, "BUILD_DIR", tmp_path / "build")
    monkeypatch.setattr(paths, "DIST_DIR", tmp_path / "dist")
    monkeypatch.setattr(paths, "FONTS", tmp_path / "fonts")
    monkeypatch.setattr(paths, "EZRA", tmp_path / "ezra.ttf")
    monkeypatch.setattr(paths, "UPSTREAM", tmp_path / "ptxprint")
    (paths.UPSTREAM / ".git").mkdir(parents=True)
    (paths.UPSTREAM / ".git/HEAD").write_text("pinned commit")
    paths.EZRA.write_bytes(b"hebrew")
    for directory in ("olebfont", "greek"):
        target = paths.FONTS / directory
        target.mkdir(parents=True)
        (target / "face.ttf").write_bytes(b"font")
    monkeypatch.setattr(fill_cache, "capture", lambda *args: "pinned tools")
    monkeypatch.setattr(fill_cache, "image_inputs", lambda: ("Dockerfile",))
    (tmp_path / "Dockerfile").write_text("pins")
    project = tmp_path / "project"
    conf = project / SETTINGS_DIR
    conf.mkdir(parents=True)
    for name in ("Settings.xml", "BookNames.xml", "GEN.usfm", "REV.usfm"):
        (project / name).write_text(name)
    (conf / "ptxprint.cfg").write_text("layout")
    return project


def test_cache_invalidates_only_rendering_inputs(project: Path) -> None:
    original = fill_cache.keys(project, ["GEN", "REV"])
    (paths.ROOT / "src").mkdir()
    (paths.ROOT / "src/unrelated.py").write_text("# edited code")
    assert fill_cache.keys(project, ["GEN", "REV"]) == original
    (project / "REV.usfm").write_text("changed note placement")
    changed = fill_cache.keys(project, ["GEN", "REV"])
    assert changed["GEN"] == original["GEN"]
    assert changed["REV"] != original["REV"]
    for target in (
        project / SETTINGS_DIR / "ptxprint.cfg",
        paths.EZRA,
        paths.ROOT / "Dockerfile",
    ):
        before = fill_cache.keys(project, ["GEN", "REV"])
        target.write_text("new shared rendering input")
        after = fill_cache.keys(project, ["GEN", "REV"])
        assert all(after[b] != before[b] for b in before)


def test_cache_version_and_tool_changes(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = fill_cache.keys(project, ["GEN"])
    monkeypatch.setattr(fill_cache, "VERSION", 2)
    versioned = fill_cache.keys(project, ["GEN"])
    assert versioned != before
    monkeypatch.setattr(fill_cache, "capture", lambda *args: "new tools")
    assert fill_cache.keys(project, ["GEN"]) != versioned


def test_complete_partial_empty_and_corrupt_checkpoints(project: Path) -> None:
    cache = paths.BUILD_DIR / "cache"
    identities = fill_cache.keys(project, ["GEN", "REV"])
    adj = fill_cache.adjustment(project, "REV")
    adj.parent.mkdir(parents=True)
    adj.write_text("REV 1.1 -1 % expand=99 p0=100+0@3\n")
    fill_cache.snapshot(cache, project, identities, {"GEN"}, {})
    adj.unlink()
    restored = fill_cache.restore(cache, project, identities)
    assert {book: entry["complete"] for book, entry in restored.items()} == {
        "GEN": True,
        "REV": False,
    }
    assert "expand=99" in adj.read_text()
    assert fill_cache.adjustment(project, "GEN").read_text() == ""
    entry = cache / "REV" / f'{identities["REV"]}.json'
    content = json.loads(entry.read_text())
    content["adjustments"] = "corrupt"
    entry.write_text(json.dumps(content))
    assert fill_cache.load(cache, "REV", identities["REV"]) is None
    entry.write_text("{truncated")
    assert fill_cache.load(cache, "REV", identities["REV"]) is None
    assert fill_cache.load(cache, "GEN", "wrong key") is None


def test_adjustment_checkpoint_is_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "book.adj"
    target.write_text("previous checkpoint\n")
    adj = AdjList(100, 95, 105, fname=str(target), gtk=None)
    adj.liststore.append(["GEN", "1.1", 1, "-1", "", 99, "", ""])
    adj.db.append({})

    def interrupted(index: int) -> str:
        raise InterruptedError("worker stopped during write")

    monkeypatch.setattr(adj, "genline", interrupted)
    with pytest.raises(InterruptedError):
        adj.createAdjlist()
    assert target.read_text() == "previous checkpoint\n"


@pytest.mark.parametrize("failures", [[], [2]])
@pytest.mark.parametrize("gave_up", [False, True])
def test_upstream_exposes_unresolved_pages(
    monkeypatch: pytest.MonkeyPatch, failures: list[int], gave_up: bool
) -> None:
    filler = page_filler.PTXFiller.__new__(page_filler.PTXFiller)
    filler.view = SimpleNamespace(
        getAllBooks=lambda: {"REV": None},
        get=lambda key, default=None: (
            SimpleNamespace(feats={}) if key == "bl_fontR" else default
        ),
        set=lambda *args: None,
    )
    filler.clear_book_files = lambda *args: None
    filler.printbk = lambda *args, **kwargs: None
    filler.progress = lambda *args: None
    filler.createAdjs = lambda *args, **kwargs: None
    filler.adjs = object()
    filler.stats = []
    filler.cpu_q = None
    filler.parlocs = SimpleNamespace(numPages=lambda: 3, chapters={})
    # A search that ends on a page it cannot fix returns a HumanFixRequest
    # whose state has no failures; the solver keeps the pages it gave up.
    state = SimpleNamespace(
        failures=None if gave_up else failures,
        page=2,
        paragraph_params={},
        numPages=lambda: 3,
    )
    solved = page_filler.HumanFixRequest(state, 3, "Failed") if gave_up else state
    layout = SimpleNamespace(paragraph_pages={}, first_failing_page=1)

    def run_layout(*args: object, **kwargs: object) -> Any:
        filler.job = SimpleNamespace(
            pdffile="/tmp/REV.pdf", outfname="REV.tex", xdvtopdf=lambda *args: None
        )
        return layout

    monkeypatch.setattr(
        page_filler, "Hooks", lambda *args: SimpleNamespace(run_layout=run_layout)
    )
    monkeypatch.setattr(
        page_filler,
        "TypesetterSolver",
        lambda *args, **kwargs: SimpleNamespace(
            solve=lambda *args, **kwargs: solved,
            itercount=1,
            shape_cache={},
            failed_pages=failures,
        ),
    )
    monkeypatch.setattr(page_filler, "unlockme", lambda: None)
    result = filler.solve("REV")
    assert result[0] == (not failures and not gave_up)
    assert result[2] == failures
    assert fill.successful(("REV", "worker", *result)) == (not failures and not gave_up)
    assert not fill.successful(("REV", "worker", True, "success", [2]))


def test_concurrent_build_cannot_take_lock(project: Path) -> None:
    with fill.locked():
        with pytest.raises(RuntimeError, match="Another page filler"):
            with fill.locked():
                pytest.fail("second runner entered")


def test_worker_results_without_unresolved_pages_are_early_exits() -> None:
    assert fill.worker_result(("GEN", "worker", False, "Cancelled")) == (
        "GEN",
        "worker",
        False,
        "Cancelled",
        [],
    )
    assert not fill.successful(
        fill.worker_result(("GEN", "worker", False, "Cancelled"))
    )


@pytest.mark.parametrize("failure", ["fill", "typeset", "verify", None])
def test_only_publish_after_all_checks(
    project: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    paths.DIST_DIR.mkdir()
    published = paths.DIST_DIR / "bible.pdf"
    published.write_bytes(b"previous checked PDF")
    report = fill.Report(
        books=1,
        reused=0,
        resumed=0,
        completed=1,
        pending=0,
        status="typesetting",
        results=[],
        protected_breaks={},
    )
    edition: Any = SimpleNamespace(
        scripture={"GEN": None}, policy=SimpleNamespace(witnesses={})
    )

    def write(mode: str, base: Path, *args: object) -> tuple[Path, list[str]]:
        target = base / "project"
        (target / SETTINGS_DIR).mkdir(parents=True)
        return target, ["GEN"]

    def check(stage: str) -> None:
        if failure == stage:
            raise CheckFailed(f"{stage} failed")

    def filling(*args: object) -> fill.Report:
        check("fill")
        return report

    def typeset(base: Path, target: Path) -> Path:
        check("typeset")
        pdf = base / "new.pdf"
        pdf.write_bytes(b"new checked PDF")
        return pdf

    def inspect(*args: object) -> int:
        check("verify")
        return 1424

    monkeypatch.setattr(cli, "write_project", write)
    monkeypatch.setattr(fill, "run", filling)
    monkeypatch.setattr(cli, "typeset", typeset)
    monkeypatch.setattr(cli, "check_processed", lambda *args: None)
    monkeypatch.setattr(cli, "inspect_pdf", inspect)
    paths.BUILD_DIR.mkdir()
    if failure:
        with pytest.raises(CheckFailed):
            cli.render_project("pdf", "pdf", edition, [], jobs=4, fresh=True)
        assert published.read_bytes() == b"previous checked PDF"
        assert report["status"] == ("typesetting" if failure == "fill" else "failed")
    else:
        cli.render_project("pdf", "pdf", edition, [], jobs=4, fresh=True)
        assert published.read_bytes() == b"new checked PDF"
        assert report["status"] == "complete"
        assert report["pages"] == 1424


@pytest.mark.parametrize("outcome", ["success", "unresolved", "interrupt", "protected"])
def test_runner_checkpoints_reuses_and_stops_workers(
    project: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    paths.BUILD_DIR.mkdir()
    work = paths.BUILD_DIR / "page-fill/projects/BIBLE"
    (project / SETTINGS_DIR / "ptxprint-mods.tex").write_text("production TeX")
    view = SimpleNamespace(
        args=SimpleNamespace(),
        prjTree=None,
        userconfig=None,
        scriptsdir=None,
        project=SimpleNamespace(prjid="BIBLE", guid="guid"),
        cfgid="Bible",
        savePics=lambda: None,
        saveStyles=lambda: None,
        saveAdjlists=lambda: None,
    )
    monkeypatch.setattr(fill, "ptxprint_main", lambda **kwargs: view)
    monkeypatch.setattr(
        fill_layout,
        "probe",
        lambda *args: ([], [1]) if outcome == "protected" else ([1], []),
    )
    pools: list[Any] = []

    class Pool:
        def __init__(self, **kwargs: Any) -> None:
            self.pending_futures: dict[Any, Any] = {}
            self.progress_q: queue.Queue[Any] = queue.Queue()
            self.cpu_q: queue.Queue[Any] = queue.Queue()
            self.executor = None
            self.terminated = False
            pools.append(self)

        def submit_fill_jobs(self, books: list[str], *args: Any, **kwargs: Any) -> None:
            for book in books:
                target = fill_cache.adjustment(work, book)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f"{book} 1.1 -1\n")
                future: Future[Any] = Future()
                if outcome == "interrupt":
                    future.set_exception(KeyboardInterrupt())
                else:
                    future.set_result(
                        (
                            book,
                            "worker",
                            True,
                            "finished",
                            [2] if outcome in ("unresolved", "protected") else [],
                        )
                    )
                self.pending_futures[future] = SimpleNamespace(books=[book])

        def terminate(self) -> None:
            self.terminated = True

        def teardown(self) -> None:
            pass

    monkeypatch.setattr(fill, "MultiPrint", Pool)
    identities = fill_cache.keys(project, ["GEN", "REV"])
    if outcome in ("success", "protected"):
        report = fill.run(project, ["GEN", "REV"], 4, True)
        assert report["completed"] == 2
        assert fill_cache.adjustment(project, "REV").read_text() == "REV 1.1 -1\n"
        # Simulate a new generated project without the previous adjustments.
        shutil.rmtree(project / SETTINGS_DIR / "AdjLists")
        report = fill.run(project, ["GEN", "REV"], 4, False)
        assert report["reused"] == 2
        if outcome == "protected":
            assert report["protected_breaks"] == {"GEN": [1], "REV": [1]}
        assert len(pools) == 1  # No solver jobs on the warm build.
        shutil.rmtree(project / SETTINGS_DIR / "AdjLists")
        (project / "REV.usfm").write_text("changed Revelation note placement")
        report = fill.run(project, ["GEN", "REV"], 4, False)
        assert report["reused"] == 1
        assert [book for book, *_ in report["results"]] == ["REV"]
    else:
        with pytest.raises((CheckFailed, KeyboardInterrupt)):
            fill.run(project, ["GEN", "REV"], 4, True)
        assert pools[0].terminated
        checkpoint = fill_cache.load(
            paths.BUILD_DIR / "page-fill-cache", "REV", identities["REV"]
        )
        assert checkpoint is not None and not checkpoint["complete"]
        assert checkpoint["adjustments"].startswith("REV")
        assert not (project / SETTINGS_DIR / "AdjLists").exists()
        outcome = "success"
        resumed = fill.run(project, ["GEN", "REV"], 4, False)
        assert resumed["resumed"] == 2
        assert resumed["completed"] == 2
    # The filler worked on its copy; the project typeset at the end is untouched.
    assert (
        project / SETTINGS_DIR / "ptxprint-mods.tex"
    ).read_text() == "production TeX"
    assert not (project / "local").exists()


@pytest.mark.parametrize("workers", [1, 2])
def test_workers_have_separate_process_groups(workers: int) -> None:
    from ptxprint.multiprint import MultiPrint

    pool = MultiPrint(numproc=workers, progress=True)
    try:
        pool.start()
        assert pool.executor is not None
        worker = pool.executor.submit(os.getpid).result(timeout=30)
        assert worker != os.getpid()
        assert os.getpgid(worker) == worker
    finally:
        pool.teardown()
