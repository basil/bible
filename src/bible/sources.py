"""The pinned source texts under sources/, and reading them.

Replacing a source is deliberate: commit the new archive with its new hash
and retrieval date here.
"""

import io
import re
import zipfile

from bible import paths
from bible.checks import require
from bible.files import sha256

# The pinned source texts, by path relative to the checkout. An archive's hash
# pins every book in it.
SOURCES = {
    "brenton": {
        "archive": "sources/eng-Brenton_usfm.zip",
        "url": "https://ebible.org/Scriptures/eng-Brenton_usfm.zip",
        "retrieved": "2026-09-23",
        "sha256": "93496ef23f7ff2427c32f5d353089dee73e82975ab92c80a00663fb333c57e32",
    },
    "kjv": {
        "archive": "sources/engkjvcpb_usfm.zip",
        "url": "https://ebible.org/Scriptures/engkjvcpb_usfm.zip",
        "retrieved": "2026-09-23",
        "sha256": "7940a2d164513b2bd2dbec2c8570b89ef8673621ed4f30f3099218a7ddd04936",
    },
    "marginal_notes": {
        "file": "sources/exhaustive-listing-marginal-notes-1611-edition-king-james-bible.md",
        "url": "https://en.literaturabautista.com/exhaustive-listing-marginal-notes-1611-edition-king-james-bible",
        "retrieved": "2026-09-25",
    },
}


def read_archive(file):
    """Each USFM book in a zip archive, by its \\id code."""
    result = {}
    with zipfile.ZipFile(file) as archive:
        for name in archive.namelist():
            if name.lower().endswith(".usfm"):
                text = archive.read(name).decode("utf-8-sig").replace("\r\n", "\n")
                code = re.search(r"\\id\s+(\S+)", text)[1]
                if code in result:
                    raise ValueError(f"Duplicate source book: {code}")
                result[code] = text
    return result


def pinned_bytes(path, expected_sha256):
    """A pinned file's contents, refused unless they match the recorded hash."""
    data = (paths.ROOT / path).read_bytes()
    require(sha256(data) == expected_sha256, f"Checksum mismatch: {path}")
    return data


def load_archives():
    """Every pinned archive's books, by source name, refused on a hash mismatch."""
    return {
        name: read_archive(
            io.BytesIO(pinned_bytes(source["archive"], source["sha256"]))
        )
        for name, source in SOURCES.items()
        if "archive" in source
    }
