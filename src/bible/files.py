"""Reading and writing the build's JSON files, and hashing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from bible.checks import CheckFailed


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:  # malformed JSON or not UTF-8
        raise CheckFailed(f"{path}: {error}") from None


def json_text(data: object) -> str:
    """The data as the build writes JSON."""

    def plain(value: object) -> object:
        # The policy's frozen objects and lists.
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, (tuple, set, frozenset)):
            return list(value)
        raise TypeError(f"Unsupported JSON value: {type(value).__name__}")

    return json.dumps(data, indent=2, ensure_ascii=False, default=plain) + "\n"


def write_json(path: Path, data: object) -> None:
    """Write the file whole: a reader sees the old file or the new, never part."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json_text(data), encoding="utf-8")
    temporary.replace(path)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
