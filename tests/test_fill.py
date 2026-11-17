"""Cache isolation, strict solver acceptance, and preserving checked downloads."""

from __future__ import annotations

import json
import queue
import shutil
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from ptxprint import multiprint, page_filler

from bible import cli, fill, fill_cache, fill_layout, paths, typeface
from bible.checks import CheckFailed
from bible.files import sha256
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
    monkeypatch.setattr(typeface, "CHAPTER", tmp_path / "chapter.otf")
    monkeypatch.setattr(typeface, "greek_family", lambda: "GFS Heraklit")
    typeface.CHAPTER.write_bytes(b"chapter")
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
        typeface.CHAPTER,
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
    entry = cache / "REV" / f'{identities["REV"]}.json'
    assert not entry.exists()
    # Old incomplete entries must not restore adjustments or saved probes.
    legacy = json.loads((cache / "GEN" / f'{identities["GEN"]}.json').read_text())
    legacy.update(
        book="REV",
        key=identities["REV"],
        complete=False,
        adjustments=adj.read_text(),
        checksum=sha256(adj.read_bytes()),
    )
    entry.parent.mkdir(parents=True)
    entry.write_text(json.dumps(legacy))
    adj.unlink()
    restored = fill_cache.restore(cache, project, identities)
    assert set(restored) == {"GEN"}
    assert not adj.exists()
    assert fill_cache.adjustment(project, "GEN").read_text() == ""
    adj.write_text("REV 1.1 -1 % expand=99 p0=100+0@3\n")
    fill_cache.snapshot(cache, project, identities, {"GEN", "REV"}, {})
    adj.unlink()
    assert set(fill_cache.restore(cache, project, identities)) == {"GEN", "REV"}
    assert "expand=99" in adj.read_text()
    content = json.loads(entry.read_text())
    content["adjustments"] = "corrupt"
    entry.write_text(json.dumps(content))
    assert fill_cache.load(cache, "REV", identities["REV"]) is None
    entry.write_text("{truncated")
    assert fill_cache.load(cache, "REV", identities["REV"]) is None
    assert fill_cache.load(cache, "GEN", "wrong key") is None


@pytest.mark.parametrize(
    "case,expected",
    [
        ("clean", (True, [], [])),
        ("gap", (False, [1], [])),
        ("protected", (True, [], [1])),
        ("gave up", (True, [], [1])),
        ("gave up on a gap", (False, [1], [])),
        ("stopped early", (True, [], [])),
        ("restart timed out", (False, [], [])),
        ("timed out", (False, [], [])),
        ("bad initial layout", (False, [], [])),
        ("no pages", (False, [], [])),
        ("missing", (False, [], [])),
    ],
)
def test_worker_judges_the_layout_the_pinned_filler_ends_on(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    expected: tuple[bool, list[int], list[int]],
) -> None:
    """PTXprint's solve() must still lay the whole book out last and keep its
    measurements; its record of failures is not read. Restarted, it must go on
    from the adjustments it saved."""
    assert multiprint._worker_ctx is None  # Set in a worker, where fill() runs.
    filler = page_filler.PTXFiller.__new__(page_filler.PTXFiller)
    filler.nid = "Worker1"
    filler.timedout = False
    filler.cancel_event = None
    filler.view = SimpleNamespace(
        getAllBooks=lambda: {} if case == "missing" else {"REV": None},
        get=lambda key, default=None: (
            SimpleNamespace(feats={}) if key == "bl_fontR" else default
        ),
        set=lambda *args: None,
        get_adjlist=lambda book, save: SimpleNamespace(
            get_params=lambda: {}, get_cache=lambda: ({}, {})
        ),
    )
    filler.clear_book_files = lambda *args: None
    filler.printbk = lambda *args, **kwargs: None
    filler.progress = lambda *args: None
    filler.createAdjs = lambda *args, **kwargs: None
    filler.adjs = object()
    filler.stats = []
    filler.cpu_q = None
    heading = (SimpleNamespace(partype="section", mrk="s1"), None)
    verse = (SimpleNamespace(partype="versetext", mrk="p"), None)
    # The filler stopped before the book's end, and fills it when restarted.
    early = case == "stopped early"
    restarted = case in (
        "gap",
        "gave up on a gap",
        "stopped early",
        "restart timed out",
    )
    short = restarted or case in ("protected", "gave up")
    forced = case in ("protected", "gave up")
    filler.parlocs = SimpleNamespace(
        numPages=lambda: 0 if case == "no pages" else 3,
        chapters={},
        getParas=lambda page: iter([heading if forced else verse]),
    )
    gave_up = case.startswith("gave up")
    # The solver's failures are of its search: here they name a page the last
    # layout fills, and no page that layout leaves short.
    state = SimpleNamespace(
        failures=None if gave_up else [2] if short and not early else [],
        page=2,
        paragraph_params={},
        float_anchors={},
        numPages=lambda: 3,
    )
    solved = page_filler.HumanFixRequest(state, 3, "Failed") if gave_up else state
    layout = SimpleNamespace(
        paragraph_pages={},
        first_failing_page=1,
        pages=[object()],
        result=1 if case == "bad initial layout" else 0,
    )
    runs = 0
    solves = 0

    def run_layout(*args: object, **kwargs: object) -> Any:
        nonlocal runs
        runs += 1
        filler.job = SimpleNamespace(
            pdffile="/tmp/REV.pdf",
            outfname="REV.tex",
            res=0,
            xdvtopdf=lambda *args: None,
        )
        # The first layout is short on its second page; the last, with the
        # chosen adjustments, on its first or nowhere. A restart lays the
        # book out twice more, as it was left and as the restart leaves it.
        gap = short and not (early and runs == 4)
        filler.underfills = [[0], [5], [40]] if runs == 1 else [[3 * gap], [0], [40]]
        return layout

    def search(*args: object, **kwargs: object) -> Any:
        nonlocal solves
        solves += 1
        filler.timedout = case == "timed out" or (
            case == "restart timed out" and solves == 2
        )
        return solved

    filler.hooks_class = lambda *args: SimpleNamespace(run_layout=run_layout)
    filler.solver_class = lambda *args, **kwargs: SimpleNamespace(
        solve=search, neutral=lambda p: (1.0, 0), itercount=1, shape_cache={}
    )
    monkeypatch.setattr(page_filler, "unlockme", lambda: None)
    monkeypatch.setattr(
        multiprint, "_worker_ctx", multiprint.WorkerContext("Worker1", None, None, None)
    )
    monkeypatch.setattr(
        multiprint.WorkerContext, "get_printer", lambda self, job: filler
    )
    book, worker, complete, message, unresolved, protected = fill_layout.fill(
        SimpleNamespace(books=["REV"])
    )
    assert (book, worker) == ("REV", "Worker1")
    assert (complete, unresolved, protected) == expected
    assert runs == (
        0 if case == "missing" else 1 if case == "no pages" else 4 if restarted else 2
    )
    if case in ("protected", "gave up"):
        assert message == "Final layout verified; protected breaks [1]"
    if early:
        assert message.endswith("; restarted 1 time")


def test_concurrent_build_cannot_take_lock(project: Path) -> None:
    with fill.locked():
        with pytest.raises(RuntimeError, match="Another page filler"):
            with fill.locked():
                pytest.fail("second runner entered")


def test_one_worker_is_refused() -> None:
    """PTXprint would fill a single worker's books in the build's own process."""
    with pytest.raises(SystemExit):
        cli.main(["pdf", "--jobs", "1"])


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
    pools: list[Any] = []

    class Pool:
        def __init__(self, **kwargs: Any) -> None:
            self.pending_futures: dict[Any, Any] = {}
            self.progress_q: queue.Queue[Any] = queue.Queue()
            self.cpu_q: queue.Queue[Any] = queue.Queue()
            self.terminated = False
            pools.append(self)

        def start(self) -> None:
            self.executor = self

        def submit(self, worker: Any, job: Any) -> Future[Any]:
            assert worker is fill_layout.fill
            (book,) = job.books
            target = fill_cache.adjustment(work, book)
            assert not target.exists()  # Pending books always start fresh.
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"{book} 1.1 -1\n")
            future: Future[Any] = Future()
            if outcome == "interrupt" and book == "REV":
                future.set_exception(KeyboardInterrupt())
            elif outcome == "unresolved" and book == "REV":
                future.set_result((book, "worker", False, "finished", [1], []))
            else:
                protected = [1] if outcome == "protected" else []
                future.set_result((book, "worker", True, "finished", [], protected))
            return future

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
        assert checkpoint is None
        assert not (
            paths.BUILD_DIR / "page-fill-cache/REV" / f'{identities["REV"]}.json'
        ).exists()
        assert (
            fill_cache.load(
                paths.BUILD_DIR / "page-fill-cache", "GEN", identities["GEN"]
            )
            is not None
        )
        assert not (project / SETTINGS_DIR / "AdjLists").exists()
        outcome = "success"
        restarted = fill.run(project, ["GEN", "REV"], 4, False)
        assert restarted["reused"] == 1
        assert restarted["completed"] == 2
        assert [book for book, *_ in restarted["results"]] == ["REV"]
    # The filler worked on its copy; the project typeset at the end is untouched.
    assert (
        project / SETTINGS_DIR / "ptxprint-mods.tex"
    ).read_text() == "production TeX"
    assert not (project / "local").exists()
