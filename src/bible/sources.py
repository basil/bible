"""The pinned source texts under sources/, and reading them.

Replacing a source is deliberate: commit the new archive with its new hash
and retrieval date here.
"""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from types import MappingProxyType

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
    "versification": {
        "file": "sources/TVTMS - Translators Versification Traditions with Methodology for Standardisation for Eng+Heb+Lat+Grk+Others - STEPBible.org CC BY.txt",
        "url": "https://github.com/STEPBible/STEPBible-Data/blob/1f342173b881ba5d1a5a4cae6e7c6c3fcc7cac51/Versification/",
        "retrieved": "2026-09-28",
        "sha256": "63058e0f20201af4bdaa7d830da5be8f493455d947c5f147d84840b33db9ddf8",
    },
    "marginal_notes": {
        "file": "sources/exhaustive-listing-marginal-notes-1611-edition-king-james-bible.md",
        "url": "https://en.literaturabautista.com/exhaustive-listing-marginal-notes-1611-edition-king-james-bible",
        "retrieved": "2026-09-25",
    },
}


@dataclass(frozen=True)
class Sources:
    """Every text the edition is made from, as it was read.

    The archives' books are USFM by their \\id codes; the edition's own pages
    are by their paths; the marginal notes are Calvin George's listing.
    """

    brenton: MappingProxyType[str, str]
    kjv: MappingProxyType[str, str]
    authored: MappingProxyType[str, str]
    marginal: str

    def __getitem__(self, family: str) -> Mapping[str, str]:
        return {"brenton": self.brenton, "kjv": self.kjv}[family]


def read_archive(file: BytesIO) -> MappingProxyType[str, str]:
    """Each USFM book in a zip archive, by its \\id code."""
    result = {}
    with zipfile.ZipFile(file) as archive:
        for name in archive.namelist():
            if name.lower().endswith(".usfm"):
                text = archive.read(name).decode("utf-8-sig").replace("\r\n", "\n")
                match = re.search(r"\\id\s+(\S+)", text)
                assert match is not None
                code = match[1]
                require(code not in result, f"Duplicate source book: {code}")
                result[code] = text
    return MappingProxyType(result)


def pinned_bytes(path: str, expected_sha256: str) -> bytes:
    """A pinned file's contents, refused unless they match the recorded hash."""
    data = (paths.ROOT / path).read_bytes()
    require(sha256(data) == expected_sha256, f"Checksum mismatch: {path}")
    return data


def load() -> Sources:
    """Read the archives, the edition's pages and the marginal notes."""
    archives = {
        name: read_archive(
            io.BytesIO(pinned_bytes(source["archive"], source["sha256"]))
        )
        for name, source in SOURCES.items()
        if "archive" in source
    }
    authored = {
        str(path.relative_to(paths.ROOT)): path.read_text(encoding="utf-8")
        for path in sorted(paths.CONTENT_DIR.glob("*.sfm"))
    }
    marginal = (paths.ROOT / SOURCES["marginal_notes"]["file"]).read_text(
        encoding="utf-8"
    )
    return Sources(
        archives["brenton"], archives["kjv"], MappingProxyType(authored), marginal
    )
