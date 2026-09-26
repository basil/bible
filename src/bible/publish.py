"""Publishing a checked PDF to dist/ with a provenance record of what produced it."""

import shutil
import sys

from bible import edition, paths, sources, toolchain
from bible.files import file_sha256, write_json

# The checkout's folders and files that the provenance record hashes.
TRACKED_FOLDERS = ("config", "content", "edition", "src")
TRACKED_FILES = (
    "Dockerfile",
    "compose.yaml",
    "Makefile",
    "pyproject.toml",
    "requirements.txt",
)


def tracked_inputs():
    """The hash of every input in the checkout, by its path in the checkout."""
    tracked = {
        p.relative_to(paths.ROOT).as_posix(): file_sha256(p)
        for folder in TRACKED_FOLDERS
        for p in sorted((paths.ROOT / folder).rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }
    for name in (
        *TRACKED_FILES,
        # Not pinned by a hash like the archives, so record the copy that was read.
        sources.SOURCES["marginal_notes"]["file"],
        *toolchain.font_archives(),
    ):
        tracked[name] = file_sha256(paths.ROOT / name)
    return tracked


def publish(mode, pdf, ids, report):
    """Copy a checked PDF to dist/ with a record of what produced it."""
    target = paths.DIST_DIR / paths.OUTPUTS[mode]
    paths.DIST_DIR.mkdir(exist_ok=True)
    provenance = {
        "title": edition.MANIFEST["title"],
        "pdf_sha256": file_sha256(pdf),
        "upstream_commits": toolchain.upstream_commits(),
        "source_archives": {
            k: {x: v[x] for x in ("url", "sha256", "retrieved") if x in v}
            for k, v in sources.SOURCES.items()
        },
        "inputs": tracked_inputs(),
        "order": ids,
        "checks": report,
        "fonts": toolchain.installed_fonts(),
        "os_release": toolchain.os_release(),
        "python_version": sys.version,
        "os_packages": toolchain.os_packages(),
    }
    # Stage both outputs, then swap them in together so a failure never pairs a new
    # PDF with an old provenance record.
    provenance_target = target.with_suffix(".provenance.json")
    staged_pdf = target.with_suffix(".pdf.tmp")
    staged_provenance = target.with_suffix(".provenance.json.tmp")
    shutil.copyfile(pdf, staged_pdf)
    write_json(staged_provenance, provenance)
    provenance_target.unlink(missing_ok=True)
    staged_pdf.replace(target)
    staged_provenance.replace(provenance_target)
    print("Wrote", target, flush=True)
