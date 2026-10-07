"""Guarded fixes for the pinned PTXprint margin-note convergence checks."""

from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"PTXprint changed in {path}; review the convergence patch")
    path.write_text(text.replace(old, new), encoding="utf-8")


def _bible_same_cache(old: str, new: str, extension: str) -> bool:
    if old == new:
        return True
    if extension != "parlocs":
        return False
    old_lines, new_lines = old.splitlines(), new.splitlines()
    if len(old_lines) != len(new_lines):
        return False
    # Only the final two note coordinates are scaled points. IDs, note
    # classes, page numbers and every other layout record must match exactly.
    note = r"(\\@noteid(?:\{[^{}]*\}){4})\{(-?\d+)\}\{(-?\d+)\}"
    for before, after in zip(old_lines, new_lines):
        if before == after:
            continue
        left, right = re.fullmatch(note, before), re.fullmatch(note, after)
        if left is None or right is None or left[1] != right[1]:
            return False
        if any(abs(int(left[i]) - int(right[i])) > 1 for i in (2, 3)):
            return False
    return True


def patch(root: Path) -> None:
    # PTXprint shifts a note only when it collides with another, so a note
    # set beside a page's first line, as at a chapter's opening, can stand
    # above the text block if no other note pushes it down. Hold every note
    # within the block before the notes are moved apart. The Dockerfile has
    # already changed this sort to order notes by their tops alone.
    replace_once(
        root / "marginnotes.py",
        "            t.sort(key=lambda n: -n.ymax)\n",
        "            t.sort(key=lambda n: -n.ymax)\n"
        "            for n in t:\n"
        "                if n.ymax + n.yshift > self.top:\n"
        "                    n.yshift = self.top - n.ymax\n",
    )
    # A margin too full for its notes is shifted further on every pass, until
    # an offset is larger than TeX can take. Once the notes are moved apart,
    # hold every note below the block's head and above the foot of the page
    # (y = 0): the notes of an overfull margin then overlap low on the page,
    # and the next pass finds them where it left them. A margin that fits
    # never needs either bound, so its notes are placed as before.
    replace_once(
        root / "marginnotes.py",
        "                i += 1\n        return\n",
        "                i += 1\n"
        "            for n in t:\n"
        "                n.yshift = min(n.yshift, self.top - n.ymax)\n"
        "                n.yshift = max(n.yshift, -n.ymin)\n"
        "        return\n",
    )
    replace_once(
        root / "marginnotes.py",
        "                    if s['yshift'] != 0:\n",
        # Compare the offsets at TeX's integer scaled-point precision. A
        # one-sp round-trip discrepancy must not request another full pass.
        "                    if abs(round(s['yoffset'] * 65536) - "
        "round(n.yoffset * 65536)) > 1:\n",
    )
    # The generic cache check compares bytes and would request reruns for the
    # same harmless jitter even after outfile declares the offsets settled.
    # tidymarginnotes already decides whether another note-placement pass is
    # needed; keep the other layout caches under their existing checks.
    replace_once(
        root / "runjob.py",
        """                    "parlocs":      (_("chapter positions"), True),
                    "marginnotes":  (_("margin note positions"), True)}""",
        """                    "parlocs":      (_("chapter positions"), True)}""",
    )
    replace_once(
        root / "runjob.py",
        "class RunJob:\n",
        inspect.getsource(_bible_same_cache) + "\n\nclass RunJob:\n",
    )
    replace_once(
        root / "runjob.py",
        "                if testdata != cachedata[a]:\n",
        "                if not _bible_same_cache(testdata, cachedata[a], a):\n",
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
    patch(Path(sys.argv[1]))
