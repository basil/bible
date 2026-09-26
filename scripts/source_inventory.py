"""Reading source archives, and inventories of USFM: verse labels are strings
(including bridges/letters), and markers are counted."""

import collections
import hashlib
import re
import zipfile

# A USFM marker: its name, with the + of a nested character style and the * that
# closes a span.
MARKER = r"\\(\+?[\w-]+\*?)"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_archive(file):
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


def inventory(text):
    chapters = {}
    chapter = None
    for m in re.finditer(r"\\(c|v)\s+(\S+)", text):
        kind, label = m.groups()
        if kind == "c":
            if label in chapters:
                raise ValueError(f"Duplicate chapter {label}")
            chapter = label
            chapters[chapter] = []
        else:
            if chapter is None:
                raise ValueError("Verse before chapter")
            if label in chapters[chapter]:
                raise ValueError(f"Duplicate verse {chapter}:{label}")
            chapters[chapter].append(label)
    return {"chapters": chapters, "markers": dict(sorted(marker_counts(text).items()))}


def marker_counts(text):
    return collections.Counter(re.findall(MARKER, text))
