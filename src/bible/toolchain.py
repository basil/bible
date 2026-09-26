"""The container image the build runs in: its pinned tools and fonts, and the
refusal to typeset in an image built from other pins than the checkout's."""

from pathlib import Path
import subprocess

from bible import paths
from bible.checks import require
from bible.files import file_sha256

# The upstream projects the Dockerfile pins, checked out under /opt.
UPSTREAM_PROJECTS = ("ptxprint", "usfmtc", "utopia")


def run(*args, **kw):
    return subprocess.run([str(a) for a in args], check=True, **kw)


def capture(*args):
    return subprocess.check_output([str(a) for a in args], text=True)


def font_archives():
    """The font archives the image was built from, relative to /opt as they are
    to the checkout. The image build checks their hashes; outside it there are none."""
    return tuple(
        str(p.relative_to(paths.OPT))
        for p in sorted((paths.OPT / "sources").glob("*.zip"))
    )


def check_image(root=paths.ROOT):
    require(
        paths.UPSTREAM.exists(), "Run this command through Make (make bootstrap first)"
    )
    # The image keeps the pins it was built from; a stale image would typeset
    # with other tools or fonts than the ones pinned here.
    for name in ("Dockerfile", "requirements.txt", *font_archives()):
        require(
            (paths.OPT / name).read_bytes() == (root / name).read_bytes(),
            f"The image was built from another {name}; run make bootstrap",
        )


def upstream_commits():
    # The checkouts belong to root, which git refuses unless told otherwise.
    return {
        name: capture(
            "git",
            "-c",
            "safe.directory=*",
            "-C",
            paths.OPT / name,
            "rev-parse",
            "HEAD",
        ).strip()
        for name in UPSTREAM_PROJECTS
    }


def installed_fonts():
    """The hash of every font file the image installs, by file name."""
    fonts = {}
    for folder in (
        paths.UPSTREAM / "fonts",
        *sorted(p for p in Path("/usr/local/share/fonts").iterdir() if p.is_dir()),
        Path("/usr/share/fonts/truetype/ezra"),
    ):
        files = sorted(p for p in folder.iterdir() if p.suffix in {".otf", ".ttf"})
        require(files, f"No font files to record in provenance: {folder}")
        for p in files:
            require(p.name not in fonts, f"Duplicate font file name: {p.name}")
            fonts[p.name] = file_sha256(p)
    return fonts


def os_release():
    return Path("/etc/os-release").read_text(encoding="utf-8").splitlines()


def os_packages():
    return (paths.OPT / "os-packages.tsv").read_text(encoding="utf-8").splitlines()
