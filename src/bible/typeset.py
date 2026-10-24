"""Running PTXprint on a written project, in a private home directory."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from bible import paths
from bible.checks import require
from bible.project import project_settings


def environment(base: Path) -> dict[str, str]:
    """A private home under base, so PTXprint reads and writes no user settings."""
    home = base / "home"
    home.mkdir()
    return dict(
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / "config"),
        XDG_CACHE_HOME=str(home / "cache"),
    )


def command(project: Path, logfile: Path, action: str, *options: str) -> list[str]:
    """The pinned CLI's invocation of an action on the project."""
    return [
        "ptxprint",
        "-m",
        str(paths.UPSTREAM / "src"),
        "-p",
        str(project.parent),
        "-c",
        "Bible",
        "-N",
        "-q",
        "-l",
        "INFO",
        "--logfile",
        str(logfile),
        "-to",
        "1200",
        *options,
        "BIBLE",
        action,
    ]


def typeset(base: Path, project: Path) -> Path:
    """Typeset the project written under base; returns the PDF it produced."""
    env = os.environ.copy()
    env.update(environment(base))
    # The contents and delayed chapter positions settle on the fifth
    # pass in the full edition (Genesis 24 is the last to settle).
    print("Typesetting", base.name, "in", base, flush=True)
    with (base / "console.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(
            command(project, base / "ptxprint.log", "print", "-R", "5"),
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=paths.ROOT,
        )
    if result.returncode:
        print((base / "console.log").read_text(encoding="utf-8")[-6000:])
        # The rerun-limit patch logs why a layout did not settle in -R passes.
        raise RuntimeError(
            f"PTXprint failed ({result.returncode}); "
            f"see {base}/console.log and {base}/ptxprint.log"
        )
    # The rerun-limit patch exempts a single-pass run, of which PTXprint
    # keeps the unsettled PDF and only says so on its console.
    require(
        "Maximum runs exceeded"
        not in (base / "console.log").read_text(encoding="utf-8"),
        f"Typesetting did not converge; see {base}/console.log",
    )
    pdfs = sorted(project.rglob("*.pdf"), key=lambda pdf: len(pdf.name))
    # A colour conversion leaves XeTeX's PDF beside the finished one, which
    # PTXprint names after it with a suffix: Bible.pdf and Bible_gray.pdf.
    # A conversion that fails writes nothing, and must not pass for one.
    converted = (
        project_settings(project).get("snippets", "pdfoutput", fallback="Screen")
        != "Screen"
    )
    require(
        len(pdfs) == 1 + converted
        and (not converted or pdfs[1].name.startswith(pdfs[0].stem + "_")),
        f"Expected XeTeX's PDF{' and its conversion' if converted else ''}, "
        f"found {pdfs}; see {base}/console.log",
    )
    return pdfs[-1]
