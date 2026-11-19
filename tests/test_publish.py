"""The books as plain USFM: every scripture book in the edition's order,
without what only PTXprint needs, and zipped the same way every time."""

import re
import zipfile
from pathlib import Path

import pytest

from bible import export, paths, pipeline
from bible.publish import publish_usfm


def test_plain_usfm_is_every_book_without_the_typesetters_markup(
    edition: pipeline.Edition, tmp_path: Path
) -> None:
    import usfmtc

    books = export.plain(edition)
    assert [code for code, _ in books] == [
        entry["id"] for entry in edition.policy.scripture
    ]
    for code, text in books:
        assert text.startswith(f"\\id {code}"), code
        # No note set below the text, no Greek or Hebrew tagged for a font,
        # and every note's origin with its chapter.
        assert not re.search(r"\\zbelow|\\w[gh] |\\fr \d+ ", text), code
    # Proverbs prints other labels than its verses' own, which other
    # readers take from \vp, as usfmtc does.
    path = tmp_path / "PRO.usfm"
    path.write_text(dict(books)["PRO"], encoding="utf-8")
    assert usfmtc.readFile(str(path)).outUsj(None)["content"]


def test_the_zip_names_books_in_order_and_is_reproducible(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(paths, "DIST_DIR", tmp_path)
    books = [("GEN", "\\id GEN\n"), ("EXO", "\\id EXO\n")]
    publish_usfm(books)
    first = (tmp_path / paths.USFM_ZIP).read_bytes()
    publish_usfm(books)
    assert (tmp_path / paths.USFM_ZIP).read_bytes() == first
    with zipfile.ZipFile(tmp_path / paths.USFM_ZIP) as archive:
        assert archive.namelist() == ["01-GEN.usfm", "02-EXO.usfm"]
        assert archive.read("02-EXO.usfm") == b"\\id EXO\n"
