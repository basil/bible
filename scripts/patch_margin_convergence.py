"""Guarded fixes for the pinned PTXprint margin-note convergence checks."""

from __future__ import annotations

from pathlib import Path

import ptxprint


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"PTXprint changed in {path}; review the convergence patch")
    path.write_text(text.replace(old, new), encoding="utf-8")


def patch(root: Path) -> None:
    # A note keeps its offset when its verse moves to another page, and the
    # solver moves only notes that collide: a note lifted clear of one page's
    # foot can stand above the next page's head, alone beside its first line
    # (Genesis 4:15). Once the notes are moved apart, hold every note below
    # the block's head. The other notes are placed as before.
    replace_once(
        root / "marginnotes.py",
        "                i += 1\n        return\n",
        "                i += 1\n"
        "            for n in t:\n"
        "                n.yshift = min(n.yshift, self.top - n.ymax)\n"
        "        return\n",
    )
    # Compare the offsets at TeX's integer scaled-point precision. A change
    # of one sp at most is rounding in the round trip, not a move: keep the
    # offset TeX had, so that the note stays exactly where it stood and the
    # next pass finds the same positions.
    replace_once(
        root / "marginnotes.py",
        "                    if s['yshift'] != 0:\n"
        "                        changed = True\n",
        "                    if abs(round(s['yoffset'] * 65536) - "
        "round(n.yoffset * 65536)) > 1:\n"
        "                        changed = True\n"
        "                    else:\n"
        "                        s['yoffset'] = n.yoffset\n",
    )
    # PTXprint's tolerant comparison never matches a record (its pattern
    # doubles the @ and drops each name's last letter), so it compares lines
    # exactly, but zip lets it miss a line added or removed, or any change
    # from an empty file. Compare parlocs whole. The note solver alone
    # decides whether margin positions need another pass, so marginnotes is
    # left out of the check.
    replace_once(
        root / "runjob.py",
        """                    "parlocs":      (_("chapter positions"), True, cmptexfiles),
                    "marginnotes":  (_("margin note positions"), True, cmptexfiles)}""",
        """                    "parlocs":      (_("chapter positions"), True, cmpdat)}""",
    )
    replace_once(
        root / "runjob.py",
        """                    if self.maxRuns == 1:
                        self.maxRuns = 2
""",
        """                    if self.maxRuns == 1:
                        self.maxRuns = 2
                    if numruns >= self.maxRuns:
                        logger.error(f"Margin notes did not converge after {numruns} passes")
                        self.res = 1
                        break
""",
    )
    replace_once(
        root / "runjob.py",
        "        if not self.res and not self.nopdf:\n",
        """        if not self.res and numruns >= self.maxRuns and (rererun or self.rerunReasons):
            logger.error(f"Typesetting did not converge after {numruns} passes: {self.rerunReasons}")
            self.res = 1
        if not self.res and not self.nopdf:
""",
    )


if __name__ == "__main__":
    patch(Path(ptxprint.__file__).parent)
