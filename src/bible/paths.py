"""Where the build reads its inputs and writes its outputs."""

from pathlib import Path

# The checkout: the package runs from it, never from an installed copy.
ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
CONTENT_DIR = ROOT / "content"
EDITION_DIR = ROOT / "edition"
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
# The PDF each command publishes under dist/; it builds in build/<command>.
OUTPUTS = {"sample": "sample.pdf", "pdf": "bible.pdf"}

# The container image's pinned tools, and the PTXprint checkout among them.
OPT = Path("/opt")
UPSTREAM = OPT / "ptxprint"
