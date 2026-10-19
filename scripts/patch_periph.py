"""Let the pinned usfmtc close a peripheral division at its document root."""

from pathlib import Path

import usfmtc.usfmparser  # type: ignore[import-untyped]


def patch(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    old = 'if curr.tag == tag or tag == "" and'
    new = 'if getattr(curr, "tag", None) == tag or tag == "" and'
    if text.count(old) != 1:
        raise RuntimeError(f"usfmtc changed in {path}; review the peripheral patch")
    path.write_text(text.replace(old, new), encoding="utf-8")


if __name__ == "__main__":
    patch(Path(usfmtc.usfmparser.__file__))
