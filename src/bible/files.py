"""Reading and writing the build's JSON files, and hashing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def plain(value: object) -> object:
        # The policy's frozen objects and lists.
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, (tuple, set, frozenset)):
            return list(value)
        raise TypeError(f"Unsupported JSON value: {type(value).__name__}")

    with path.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, default=plain)
        stream.write("\n")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: str | Path) -> str:
    return sha256(Path(path).read_bytes())
