"""Lossless source inventory: verse labels are strings (including bridges/letters)."""

import collections
import hashlib
import re
import zipfile


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_archive(path):
    result = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.lower().endswith(".usfm"):
                raw = archive.read(name)
                text = raw.decode("utf-8-sig").replace("\r\n", "\n")
                code = re.search(r"\\id\s+(\S+)", text)[1]
                if code in result:
                    raise ValueError(f"Duplicate source book: {code}")
                result[code] = (name, raw, text)
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
    markers = collections.Counter(re.findall(r"\\(\+?[\w-]+\*?)", text))
    return {"chapters": chapters, "markers": dict(sorted(markers.items()))}
