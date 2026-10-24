"""Expose unresolved pages and publish whole adjustment checkpoints in PTXprint."""

from pathlib import Path

import ptxprint


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"PTXprint changed in {path}; review the page-filler patch")
    path.write_text(text.replace(old, new), encoding="utf-8")


def patch(root: Path) -> None:
    # Each worker's TeX subprocesses share its process group, so cancellation
    # can stop them too rather than leave orphaned typesetters running.
    replace_once(
        root / "multiprint.py",
        "def _init_worker(progress_q, cpu_q, cancel_event):\n",
        "def _init_worker(progress_q, cpu_q, cancel_event):\n    os.setsid()\n",
    )
    replace_once(
        root / "multiprint.py", "import os, argparse\n", "import os, argparse, signal\n"
    )
    replace_once(
        root / "multiprint.py",
        "                    process.terminate()  # Sends SIGTERM to kill worker immediately\n",
        # A worker still starting has no group of its own yet, nor typesetters.
        "                    try:\n"
        "                        os.killpg(process.pid, signal.SIGTERM)  # and its typesetters\n"
        "                    except ProcessLookupError:\n"
        "                        process.terminate()\n",
    )
    # Upstream runs a single worker synchronously in the parent. Always use
    # a child, so --jobs 1 still reports progress and supports checkpoints
    # and process-group cancellation while a book is being solved.
    replace_once(
        root / "multiprint.py",
        "        if self.numproc == 1:\n"
        "            _init_worker(self.progress_q, self.cpu_q, self.cancel_event)\n"
        "            return\n",
        "",
    )
    replace_once(
        root / "multiprint.py",
        "        if self.numproc == 1:\n"
        "            res = _worker_dispatch(job)\n"
        "            fut = Future()\n"
        "            fut.set_result(res)\n"
        "            self.pending_futures[fut] = job\n"
        "        else:\n"
        "            if not self.executor:\n"
        "                self.start()\n"
        "            fut = self.executor.submit(_worker_dispatch, job)\n"
        "            self.pending_futures[fut] = job\n",
        "        if not self.executor:\n"
        "            self.start()\n"
        "        fut = self.executor.submit(_worker_dispatch, job)\n"
        "        self.pending_futures[fut] = job\n",
    )
    replace_once(
        root / "page_filler.py",
        'return (True, f"Complete {bk} Already good")',
        'return (True, f"Complete {bk} Already good", [])',
    )
    replace_once(
        root / "page_filler.py",
        'retval = (True, f"Complete {bk}, failures={res.failures},',
        'retval = (not res.failures, f"Complete {bk}, failures={res.failures},',
    )
    # A search that ends on a page it cannot fix returns a HumanFixRequest,
    # whose state carries no failures; the solver keeps the pages it gave up.
    replace_once(
        root / "page_filler.py",
        "        return retval\n",
        "        return (*retval, list(state.failures or getattr(solver, 'failed_pages', None) or []))\n",
    )
    # The parent snapshots these files while workers continue probing. A
    # snapshot must see either complete version, never half a written file.
    replace_once(
        root / "adjlist.py",
        '        with open(fname, "w", encoding="utf-8") as outf:\n',
        '        with open(str(fname) + ".tmp", "w", encoding="utf-8") as outf:\n',
    )
    replace_once(
        root / "adjlist.py",
        '                    outf.write(line + "\\n")\n        self.ftime',
        '                    outf.write(line + "\\n")\n'
        '        os.replace(str(fname) + ".tmp", fname)\n        self.ftime',
    )


if __name__ == "__main__":
    patch(Path(ptxprint.__file__).parent)
