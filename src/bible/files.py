"""Reading and writing the build's JSON files, and hashing."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def plain(value):
        # The policy's frozen objects and lists.
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, (tuple, set, frozenset)):
            return list(value)
        raise TypeError(f"Unsupported JSON value: {type(value).__name__}")

    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, default=plain)
        stream.write("\n")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    return sha256(Path(path).read_bytes())
