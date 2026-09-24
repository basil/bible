"""Network is permitted only while constructing the tool image."""

import json
from pathlib import Path
import subprocess

lock = json.loads(Path("/opt/dependencies.json").read_text())


def run(*args):
    subprocess.run(args, check=True)


for name in ("ptxprint", "usfmtc"):
    dep = lock[name]
    path = "/opt/" + name
    if "tag" in dep:
        run("git", "clone", "--depth", "1", "--branch", dep["tag"], dep["url"], path)
    else:
        run("git", "init", path)
        run("git", "-C", path, "remote", "add", "origin", dep["url"])
        run("git", "-C", path, "fetch", "--depth", "1", "origin", dep["commit"])
        run("git", "-C", path, "checkout", "--detach", "FETCH_HEAD")
    actual = subprocess.check_output(
        ["git", "-C", path, "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != dep["commit"]:
        raise SystemExit(f'{name}: expected {dep["commit"]}, got {actual}')
run("python3", "-m", "venv", "--system-site-packages", "/opt/venv")
run(
    "/opt/venv/bin/pip",
    "install",
    "--no-cache-dir",
    "--only-binary=:all:",
    "-r",
    "/opt/requirements.txt",
)
for name in ("usfmtc", "ptxprint"):
    run(
        "/opt/venv/bin/pip",
        "install",
        "--no-deps",
        "--no-build-isolation",
        "/opt/" + name,
    )
