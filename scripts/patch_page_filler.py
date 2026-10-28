"""Expose unresolved pages from PTXprint's page filler."""

from pathlib import Path

import ptxprint


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"PTXprint changed in {path}; review the page-filler patch")
    path.write_text(text.replace(old, new), encoding="utf-8")


def patch(root: Path) -> None:
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


if __name__ == "__main__":
    patch(Path(ptxprint.__file__).parent)
