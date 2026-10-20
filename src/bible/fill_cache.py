"""Disposable, per-book PTXprint adjustments, keyed by rendering inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bible import paths
from bible.files import json_text, sha256, write_json
from bible.project import ADJUSTMENTS_DIR, SETTINGS_DIR, project_usfm
from bible.toolchain import capture, image_inputs

# Bump when the saved adjustments or probes need a different interpretation.
VERSION = 1


def keys(project: Path, books: list[str]) -> dict[str, str]:
    """Hash generated rendering inputs, not the source code that prepared them."""
    shared = {
        "version": str(VERSION),
        # Docker checks out the verified pin detached; reading HEAD avoids
        # Git's ownership restriction on this root-owned image directory.
        "ptxprint": (paths.UPSTREAM / ".git/HEAD").read_text().strip(),
        "xetex": capture("xetex", "--version"),
    }
    files = [project / "Settings.xml", project / "BookNames.xml"]
    files.extend(p for p in (project / SETTINGS_DIR).rglob("*") if p.is_file())
    for p in sorted(files):
        shared[str(p.relative_to(project))] = sha256(p.read_bytes())
    for name in image_inputs():
        shared[name] = sha256((paths.ROOT / name).read_bytes())
    for directory in ("olebfont", "greek"):
        for p in sorted((paths.FONTS / directory).iterdir()):
            if p.is_file():
                shared[str(p)] = sha256(p.read_bytes())
    shared[str(paths.EZRA)] = sha256(paths.EZRA.read_bytes())
    digest = sha256(json_text(shared).encode())
    return {
        book: sha256(
            (digest + sha256(project_usfm(project, book).read_bytes())).encode()
        )
        for book in books
    }


def adjustment(project: Path, book: str) -> Path:
    return project / ADJUSTMENTS_DIR / f"{book}-Bible.usfm.adj"


def load(cache: Path, book: str, key: str) -> dict[str, Any] | None:
    try:
        entry = json.loads((cache / book / f"{key}.json").read_text("utf-8"))
        if (
            not isinstance(entry, dict)
            or entry.get("key") != key
            or entry.get("book") != book
            or not isinstance(entry.get("complete"), bool)
            or not isinstance(entry.get("adjustments"), str)
            or not isinstance(entry.get("protected_breaks"), list)
            or entry.get("checksum") != sha256(entry["adjustments"].encode())
        ):
            return None
        return entry
    except (OSError, ValueError):
        return None


def restore(
    cache: Path, project: Path, identities: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """Write the matching books' saved adjustments into the project; their entries."""
    restored = {}
    for book, key in identities.items():
        entry = load(cache, book, key)
        if entry is not None:
            target = adjustment(project, book)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(entry["adjustments"], encoding="utf-8")
            restored[book] = entry
    return restored


def snapshot(
    cache: Path,
    project: Path,
    identities: dict[str, str],
    completed: set[str],
    protected: dict[str, list[int]],
) -> None:
    for book, key in identities.items():
        try:
            text = adjustment(project, book).read_text("utf-8")
        except FileNotFoundError:
            if book not in completed:
                continue
            text = ""  # A successful book may need no adjustments at all.
        write_json(
            cache / book / f"{key}.json",
            dict(
                book=book,
                key=key,
                complete=book in completed,
                adjustments=text,
                checksum=sha256(text.encode()),
                protected_breaks=protected.get(book, []),
            ),
        )
