"""Reject an unsettled layout at PTXprint's pass cap (upstream #1262)."""

from pathlib import Path

import ptxprint


def patch(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for old, new in (
        (
            "            rererun = rerun\n",
            "            rererun = rerun\n"
            "            if rerun:\n"
            '                self.rerunReasons.append(_("TeX log"))\n',
        ),
        (
            "                    rererun = True\n                    if self.maxRuns == 1:\n",
            "                    rererun = True\n"
            '                    self.rerunReasons.append(_("margin notes"))\n'
            "                    if self.maxRuns == 1:\n",
        ),
        (
            "        if not self.res and not self.nopdf:\n",
            "        # A run of one pass (a quick run, or the page filler's) may stop\n"
            "        # unsettled; one that margin notes extended to two may not.\n"
            "        rerunnable = {v[0] for v in cacheexts.values() if v[1]}\n"
            "        if self.maxRuns > 1 and numruns >= self.maxRuns and not self.res \\\n"
            "                and (rererun or rerunnable.intersection(self.rerunReasons)):\n"
            '            logger.error("Typesetting did not converge after %s passes: %s",\n'
            '                         numruns, ", ".join(self.rerunReasons))\n'
            "            self.res = 1\n\n"
            "        if not self.res and not self.nopdf:\n",
        ),
    ):
        if text.count(old) != 1:
            raise RuntimeError(
                f"PTXprint changed in {path}; review the rerun-limit patch"
            )
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch(Path(ptxprint.__file__).parent / "runjob.py")
