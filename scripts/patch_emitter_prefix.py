"""Let the pinned PTXprint's USFM emitter take usfmtc's marker prefix."""

from pathlib import Path

import ptxprint


def patch(path: Path) -> None:
    # usfmtc now passes the tag of every character style a prefix, the + of
    # a nested one in USFM 3.0 and nothing in 3.1, which PTXprint writes.
    # Take the prefix as usfmtc's own emitter does.
    text = path.read_text(encoding="utf-8")
    for old, new in (
        (
            'class PTXEmitter(Emitter):\n    def tag(self, e, sep=" "):\n',
            'class PTXEmitter(Emitter):\n    def tag(self, e, sep=" ", prefix=""):\n',
        ),
        (
            '            self("\\\\{0}{1}".format(s, sep))\n\n\nclass Sheets',
            '            self("\\\\{0}{1}".format(prefix + s, sep))\n\n\nclass Sheets',
        ),
    ):
        if text.count(old) != 1:
            raise RuntimeError(f"PTXprint changed in {path}; review the emitter patch")
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch(Path(ptxprint.__file__).parent / "usxutils.py")
