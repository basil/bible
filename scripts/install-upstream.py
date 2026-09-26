"""Network is permitted only while constructing the tool image."""

from fnmatch import fnmatch
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile

OPT = Path("/opt")
FONTS = Path("/usr/local/share/fonts")
lock = json.loads((OPT / "dependencies.json").read_text())


def run(*args):
    subprocess.run(args, check=True)


for name, dep in lock.items():
    if "commit" in dep:
        path = OPT / name
        run("git", "init", path)
        run("git", "-C", path, "remote", "add", "origin", dep["url"])
        run("git", "-C", path, "fetch", "--depth", "1", "origin", dep["commit"])
        run("git", "-C", path, "checkout", "--detach", "FETCH_HEAD")
        actual = subprocess.check_output(
            ["git", "-C", path, "rev-parse", "HEAD"], text=True
        ).strip()
        if actual != dep["commit"]:
            raise SystemExit(f'{name}: expected {dep["commit"]}, got {actual}')
    if "archive" in dep:
        data = (OPT / dep["archive"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != dep["sha256"]:
            raise SystemExit(f"{name}: checksum mismatch")
        (FONTS / name).mkdir(parents=True)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member in archive.namelist():
                if fnmatch(member, dep["fonts"]):
                    font = FONTS / name / PurePosixPath(member).name
                    font.write_bytes(archive.read(member))
# PTXprint's fontconfig template rejects OpenType files, but it includes the
# system configuration, where an acceptfont rule takes precedence.
Path("/etc/fonts/conf.d/99-accept-local-fonts.conf").write_text(
    f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <selectfont>
    <acceptfont>
      <glob>{FONTS}/*</glob>
    </acceptfont>
  </selectfont>
</fontconfig>
"""
)
# The venv already holds requirements.txt. PTXprint's metadata names usfmtc's
# moving main branch, not the pinned commit, so neither brings dependencies.
for name in ("usfmtc", "ptxprint"):
    run(
        OPT / "venv/bin/pip",
        "install",
        "--no-deps",
        "--no-build-isolation",
        OPT / name,
    )
