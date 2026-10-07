"""The pinned source texts under sources/, and reading them.

Replacing a source is deliberate: commit the new archive with its new hash
and retrieval date here.

Everything is read here and nowhere else. The two eBible archives give their
books as USFM text; the New Testament's Greek texts and witnesses are read
into in-memory views of their archives and files (Content), selected by the
registry below and converted from PDF by Poppler where the publisher gave
nothing else.
"""

from __future__ import annotations

import fnmatch
import io
import re
import subprocess
import tempfile
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import TypedDict

from bible import paths
from bible.checks import CheckFailed, require
from bible.files import sha256


class Pinned(TypedDict, total=False):
    archive: str
    file: str
    url: str
    retrieved: str
    sha256: str


# The pinned source texts, by path relative to the checkout. An archive's hash
# pins every book in it. sources/README.md says what each is and whose it is.
SOURCES: Mapping[str, Pinned] = {
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
        "sha256": "3372e39512dc23c13bf6118eb80901532d05607444b5694b2e175aa3a7c1cc38",
    },
    # The New Testament's Greek: the text the King James Version follows, and
    # the Byzantine text it is conformed to.
    "scrivener": {
        "archive": "sources/greektext-scrivener-6049a43b135ed870f843b83eb6a04764fc796678.zip",
        "url": "https://codeload.github.com/byztxt/greektext-scrivener/zip/6049a43b135ed870f843b83eb6a04764fc796678",
        "retrieved": "2026-10-07",
        "sha256": "41d290083e20be0863cf274517d0f4a02fab2ed503b08dd9e16a024d7ed341f5",
    },
    "accented_tr": {
        "archive": "sources/textus-receptus-2bac2dae4a0961c84d6d544a40cbef8b8d8c4e32.zip",
        "url": "https://codeload.github.com/honza/textus-receptus/zip/2bac2dae4a0961c84d6d544a40cbef8b8d8c4e32",
        "retrieved": "2026-10-07",
        "sha256": "0ff99c96f1146183ed610ed6794431101a5b8d28ec806bdf4cbdf537da1e2c18",
    },
    "parsed_tr": {
        "archive": "sources/greektext-textus-receptus-7fd4d02c3e5adebd379ebfbc824040820dde10fc.zip",
        "url": "https://codeload.github.com/byztxt/greektext-textus-receptus/zip/7fd4d02c3e5adebd379ebfbc824040820dde10fc",
        "retrieved": "2026-10-07",
        "sha256": "d34f55b55f93934b2c738f85ee1242edc90119002ff40f92df7bc27160b0a516",
    },
    "rp2018": {
        "archive": "sources/byzantine-majority-text-27a45ff1b7be6c17ccbfeac414f3f55732ae8e28.zip",
        "url": "https://codeload.github.com/byztxt/byzantine-majority-text/zip/27a45ff1b7be6c17ccbfeac414f3f55732ae8e28",
        "retrieved": "2026-10-07",
        "sha256": "5093aa23b9302394cadc0a49fc04c70d4d99749c4ca2e580cfd7bbea1b0f9955",
    },
    "rp2026": {
        "file": "sources/TGNTByzText_081526_0727PM.pdf",
        "url": "https://drive.google.com/file/d/1zOfeQw-7UBcEF1zk0v5ymj2jJCHlSFCv/view",
        "retrieved": "2026-10-07",
        "sha256": "ec3cbc42c62a936573880244389054f63d68438be1d171011d4dd6b6a50a11af",
    },
    "collation": {
        "file": "sources/collation-scrivener-rp-2018.pdf",
        "url": "https://byzantinetext.com/wp-content/uploads/2022/04/collation-scrivener-rp-2018.pdf",
        "retrieved": "2026-10-07",
        "sha256": "3e5f95fe3f71ee8bf30ba0fecafee6575658d57eb65596223b879024c73212d0",
    },
    "tcgnt": {
        "archive": "sources/tcgnt-usx-files.zip",
        "url": "https://archive.org/download/TCGNT/tcgnt-usx-files.zip",
        "retrieved": "2026-10-03",
        "sha256": "83d05e1b188b78eb8d68af82b04dfd219ca399f6e288f319f0144a5f81ffc733",
    },
    "tcent": {
        "archive": "sources/tcent-usx-files.zip",
        "url": "https://archive.org/download/tcent/tcent-usx-files.zip",
        "retrieved": "2026-10-03",
        "sha256": "3cf48d8b594368b87671cfdf75d51e4360d1177644a0d52b0dfbcdb945854426",
    },
    # The English witnesses: Pierpont's instructions in the King James Bible's
    # words, the revisions of 1881 and 2021, and the translations whose notes
    # report the Received Text.
    "pierpont": {
        "file": "sources/pierpont.md",
        "url": "https://byzantinemusic.org/holy-scriptures/improvements-kjv.html",
        "retrieved": "2026-10-07",
        "sha256": "eb1b4c80558549772d8652eeb8413f7c5eacf8344a3164641e31ec40424e9cfe",
    },
    "pierpont_scan": {
        "file": "sources/pierpont-1990.pdf",
        "url": "https://byzantinemusic.org/holy-scriptures/improvements-kjv.html",
        "retrieved": "2026-10-07",
        "sha256": "4c584a42a9ba5edf8df839d1b00aef2225c6ce5da4d3a1df3929d0a69c8b108a",
    },
    "rv": {
        "archive": "sources/eng-rv_usfm.zip",
        "url": "https://ebible.org/Scriptures/eng-rv_usfm.zip",
        "retrieved": "2026-10-06",
        "sha256": "ed587388c6a1935a8a61b8a44906587d0dfaa1712fa8b0b802d7ace5ced91175",
    },
    "asv": {
        "archive": "sources/eng-asv_usfm.zip",
        "url": "https://ebible.org/Scriptures/eng-asv_usfm.zip",
        "retrieved": "2026-10-06",
        "sha256": "a9420074e1d96f87e6fac53d35b49de863cf5a69fa54911793255d92ba2047e9",
    },
    "web": {
        "archive": "sources/eng-web_usfm.zip",
        "url": "https://ebible.org/Scriptures/eng-web_usfm.zip",
        "retrieved": "2026-10-06",
        "sha256": "b09f8b9f197d05d54c32eabaa90fed9b11279b03ecc26cb347da6e1dc943eb7d",
    },
    "boyd_asv": {
        "archive": "sources/boyd-asv-byz-2021-scrape.zip",
        "url": "https://gojes.us/documents/bible/all_html/asv_byzantine_text/",
        "retrieved": "2026-10-03",
        "sha256": "03beac613a1f1e77cf5e2439c80e8a6f4c03db5f9eadff38a579a6293bb2b490",
    },
    "crosswire": {
        "archive": "sources/kjv-osis-201602070816-2_9a.zip",
        "url": "https://www.crosswire.org/~dmsmith/kjv2011/kjv2.9a/kjv-osis-201602070816-2_9a.zip",
        "retrieved": "2026-10-07",
        "sha256": "d87e7f69d7f6c1c0331bf30872969f03914a871765548c6fcdb0b54db5a136cb",
    },
    "faa": {
        "file": "sources/NTinHTML_AVorder_Unicode.html",
        "url": "https://www.faraboveall.com/050_BibleTranslation/NTinHTML_AVorder_Unicode.html",
        "retrieved": "2026-10-03",
        "sha256": "b00cadd25c57890ff68a201786debd37a81e7330bfa4f08b7e83310544422de4",
    },
    "msb": {
        "file": "sources/msb.txt",
        "url": "https://majoritybible.com/msb.txt",
        "retrieved": "2026-10-03",
        "sha256": "99ca452c23fb901a0f5a814b16d9a52fd61015e2e80987d9bf26dfb2ea850d24",
    },
    "msb_tables": {
        "file": "sources/msb_nt_tables.tsv",
        "url": "https://majoritybible.com/msb_nt_tables.tsv",
        "retrieved": "2026-10-03",
        "sha256": "9eed4097d3fa003db9c29c3e29a44cee8ae2f9922bedfeca78b171860e1106b0",
    },
}

# USFM codes of the New Testament's books, in order.
NEW_TESTAMENT = (
    "MAT MRK LUK JHN ACT ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM "
    "HEB JAS 1PE 2PE 1JN 2JN 3JN JUD REV"
).split()
# The byztxt repositories' names for them, in the same order.
BYZTXT_BOOKS = (
    "MT MR LU JOH AC RO 1CO 2CO GA EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB "
    "JAS 1PE 2PE 1JO 2JO 3JO JUDE RE"
).split()


class Content:
    """A view of one file, or one directory, of an in-memory snapshot of
    files by their names: what a reader needs of a path, and no more.

    A directory view and its files share one immutable snapshot. The label
    names the archive or folder the snapshot came from, for a message.
    """

    def __init__(
        self, files: Mapping[str, bytes], name: str = "", label: str = "sources"
    ) -> None:
        self._files = (
            # A snapshot of its own, unless it is one already: views of one
            # snapshot share it.
            files
            if isinstance(files, MappingProxyType)
            else MappingProxyType(dict(files))
        )
        self._name, self._label = name, label

    def __len__(self) -> int:
        return len(self._files)

    def __truediv__(self, name: str) -> Content:
        return Content(self._files, str(PurePosixPath(self._name) / name), self._label)

    def __str__(self) -> str:
        return f"{self._label}/{self._name}"

    @property
    def name(self) -> str:
        return PurePosixPath(self._name).name

    @property
    def stem(self) -> str:
        return PurePosixPath(self._name).stem

    def glob(self, pattern: str) -> list[Content]:
        """The files of this directory whose names match, in name order."""
        prefix = self._name.rstrip("/") + "/" if self._name else ""
        return [
            Content(self._files, name, self._label)
            for name in sorted(self._files)
            if name.startswith(prefix)
            and "/" not in name[len(prefix) :]
            and fnmatch.fnmatchcase(name[len(prefix) :], pattern)
        ]

    def read_bytes(self) -> bytes:
        try:
            return self._files[self._name]
        except KeyError:
            raise FileNotFoundError(str(self)) from None

    def read_text(self, encoding: str = "utf-8") -> str:
        """The file's text, its line ends read as newlines, as a text file
        opened for reading gives it."""
        return self.open_text(encoding).read()

    def open_text(
        self, encoding: str = "utf-8", newline: str | None = None
    ) -> io.StringIO:
        return io.StringIO(self.read_bytes().decode(encoding), newline=newline)


@dataclass(frozen=True)
class Sources:
    """Every text the edition is made from, as it was read.

    The archives' books are USFM by their \\id codes; the edition's own pages
    are by their paths; the marginal notes are Calvin George's listing;
    versification is TVTMS. The New Testament's Greek texts and witnesses are
    views of their files by the registry's names (byzantine): the archives'
    members, the loose files, and the texts Poppler read from the PDFs.
    """

    brenton: MappingProxyType[str, str]
    kjv: MappingProxyType[str, str]
    authored: MappingProxyType[str, str]
    marginal: str
    versification: str
    byzantine: MappingProxyType[str, Content]

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


def archive_content(data: bytes, label: str, wanted: Iterable[str] = ("*",)) -> Content:
    """An archive's members whose names match a wanted pattern, as one
    snapshot, each member read once; a member whose name would escape the
    archive, or repeats, is refused."""
    wanted = tuple(wanted)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), f"Duplicate archive member: {label}")
        for name in names:
            raw = name[:-1] if name.endswith("/") else name
            path = PurePosixPath(raw)
            require(
                not path.is_absolute()
                and ".." not in path.parts
                and bool(path.parts)
                and str(path) == raw
                and "\\" not in name,
                f"{label}: escaping or invalid archive member {name}",
            )
        return Content(
            {
                n: archive.read(n)
                for n in names
                if not n.endswith("/")
                and any(fnmatch.fnmatchcase(n, w) for w in wanted)
            },
            label=label,
        )


def members(content: Content, directory: str, patterns: Iterable[str]) -> Content:
    """A directory of an archive's snapshot, each required member matched once."""
    found = content / directory.rstrip("/") if directory else content
    for pattern in patterns:
        matches = found.glob(pattern)
        require(
            len(matches) == 1,
            f"{found}: missing or ambiguous required member {pattern}: "
            f"{[str(m) for m in matches]}",
        )
    return found


def converted(name: str, data: bytes, tool: str, options: Iterable[str]) -> bytes:
    """A PDF as Poppler reads it: the publisher gave the text as a PDF, and
    the build never commits a conversion. Written to a directory of its own
    that is removed afterwards; nothing of it reaches the checkout."""
    with tempfile.TemporaryDirectory(prefix="oleb-pdf-") as folder:
        pdf = Path(folder) / name
        pdf.write_bytes(data)
        command = [tool, *options, str(pdf), *(["-"] if tool == "pdftotext" else [])]
        try:
            return subprocess.run(command, capture_output=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError) as error:
            detail = getattr(error, "stderr", b"") or b""
            raise CheckFailed(
                f"{name}: {tool} conversion failed: {error}; "
                f"{detail.decode(errors='replace').strip()}"
            ) from error


def byzantine_inputs(pinned: Mapping[str, bytes]) -> MappingProxyType[str, Content]:
    """The New Testament's Greek texts and witnesses, by the names the readers
    know them by, each a view of its archive's members or of its file."""
    # A GitHub archive keeps its files in a directory named as the archive is.
    roots = {
        name: f"{Path(SOURCES[name]['archive']).stem}/"
        for name in ("scrivener", "accented_tr", "parsed_tr", "rp2018")
    }
    usfm = tuple(f"*{book}*.usfm" for book in NEW_TESTAMENT)
    usx = tuple(f"*{book}.usx" for book in NEW_TESTAMENT)
    # Each input: its archive, its directory there, and the members it needs.
    selected: dict[str, tuple[str, str, tuple[str, ...]]] = {
        "scrivener": (
            "scrivener",
            f"{roots['scrivener']}textonly/",
            tuple(f"{book}.SCV" for book in BYZTXT_BOOKS),
        ),
        "accented_tr": (
            "accented_tr",
            f"{roots['accented_tr']}data/",
            ("gnt.flat.json",),
        ),
        "parsed_tr": (
            "parsed_tr",
            f"{roots['parsed_tr']}parsed/",
            tuple(f"{book}.UTR" for book in BYZTXT_BOOKS),
        ),
        "rp2018": (
            "rp2018",
            f"{roots['rp2018']}source/Strongs/",
            tuple(f"{n:02d}_*.BP5" for n in range(1, 28)),
        ),
        "rp_margin": (
            "rp2018",
            f"{roots['rp2018']}source/CCAT/",
            tuple(f"{n:02d}_*.TXT" for n in range(1, 28)),
        ),
        "tcgnt": ("tcgnt", "", (*usx, "095XXC.usx")),
        "tcent": ("tcent", "", usx),
        "rv": ("rv", "", usfm),
        "asv": ("asv", "", usfm),
        "web": ("web", "", usfm),
        "boyd_asv": ("boyd_asv", "", ()),
        "crosswire": ("crosswire", "", ("kjv.tr.xml",)),
    }
    wanted: dict[str, list[str]] = {}
    for archive, directory, patterns in selected.values():
        wanted.setdefault(archive, []).extend(directory + p for p in patterns or ("*",))
    archives = {
        name: archive_content(
            pinned[name], Path(SOURCES[name]["archive"]).name, patterns
        )
        for name, patterns in wanted.items()
    }
    inputs = {
        name: members(archives[archive], directory, patterns)
        for name, (archive, directory, patterns) in selected.items()
    }
    for name, single in (("accented_tr", "gnt.flat.json"), ("crosswire", "kjv.tr.xml")):
        inputs[name] = inputs[name] / single
    loose = {
        name: Content({Path(SOURCES[name]["file"]).name: pinned[name]})
        / Path(SOURCES[name]["file"]).name
        for name in ("faa", "pierpont", "msb", "msb_tables")
    }
    # The Greek New Testament and Robinson's collation are published as PDFs:
    # Poppler reads them, once, and the texts it read are the inputs.
    for name, tool, options, suffix in (
        ("rp2026", "pdftohtml", ("-xml", "-i", "-stdout"), "xml"),
        ("collation", "pdftotext", ("-layout",), "txt"),
    ):
        pdf = Path(SOURCES[name]["file"]).name
        text = f"{Path(pdf).stem}.{suffix}"
        loose[name] = (
            Content(
                {text: converted(pdf, pinned[name], tool, options)},
                label=f"{pdf}!{tool}",
            )
            / text
        )
    return MappingProxyType({**inputs, **loose})


def load() -> Sources:
    """Read the pinned texts and the edition's own pages. Every pin is checked
    before anything is converted, so a changed file is refused at once."""
    pinned = {
        name: pinned_bytes(source.get("archive") or source["file"], source["sha256"])
        for name, source in SOURCES.items()
    }
    archives = {
        name: read_archive(io.BytesIO(pinned[name])) for name in ("brenton", "kjv")
    }
    authored = {
        str(path.relative_to(paths.ROOT)): path.read_text(encoding="utf-8")
        for path in sorted(paths.CONTENT_DIR.glob("*.sfm"))
    }
    return Sources(
        archives["brenton"],
        archives["kjv"],
        MappingProxyType(authored),
        pinned["marginal_notes"].decode("utf-8"),
        pinned["versification"].decode("utf-8-sig"),
        byzantine_inputs(pinned),
    )
