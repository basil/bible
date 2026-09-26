"""Running PTXprint on a written project, in a private home directory."""

import os
import subprocess

from bible import paths
from bible.checks import require


def typeset(base, project):
    """Typeset the project written under base; returns the PDF it produced."""
    home = base / "home"
    home.mkdir()
    env = os.environ.copy()
    env.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / "config"),
        XDG_CACHE_HOME=str(home / "cache"),
    )
    command = [
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
        str(base / "ptxprint.log"),
        "-R",
        "5",
        "-to",
        "1200",
        "BIBLE",
        "print",
    ]
    print("Typesetting", base.name, "in", base, flush=True)
    with (base / "console.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(
            command, stdout=log, stderr=subprocess.STDOUT, env=env, cwd=paths.ROOT
        )
    if result.returncode:
        print((base / "console.log").read_text(encoding="utf-8")[-6000:])
        raise RuntimeError(
            f"PTXprint failed ({result.returncode}); see {base}/console.log"
        )
    pdfs = list(project.rglob("*.pdf"))
    require(len(pdfs) == 1, f"Expected one PDF, found {pdfs}; see {base}/console.log")
    return pdfs[0]
