"""The books as plain USFM: every scripture book in the edition's order,
without what only PTXprint needs, and zipped the same way every time."""

import re
import zipfile
from pathlib import Path

import pytest

from bible import export, paths, pipeline, usj
from bible.publish import publish_usfm


def test_plain_usfm_is_every_book_without_the_typesetters_markup(
    edition: pipeline.Edition, tmp_path: Path
) -> None:
    import usfmtc

    books = export.plain(edition)
    assert [code for code, _ in books] == [
        entry["id"] for entry in edition.policy.scripture
    ]
    views = dict(pipeline.view(edition, "pdf"))
    for code, text in books:
        assert text.startswith(f"\\id {code}"), code
        # No note set below the text, no Greek or Hebrew tagged for a font,
        # and every note's origin with its chapter, under the label its
        # verse prints.
        assert not re.search(r"\\zbelow|\\w[gh] |\\fr \d+ ", text), code
        origins = {o.strip() for o in re.findall(r"\\[fx][ro] ([^\\]+)", text)}
        assert not origins & set(export.printed_labels(views[code])), code
    # Every note is marked in the text, since no margin stands beside it.
    assert not re.search(r"\\[fx] - ", "".join(text for _, text in books))
    # A note the book sets below the text stays at its words, with its text
    # and its whole origin, as every other.
    key = next(iter(edition.policy.margin["below"]))
    code, note = next(
        (code, note)
        for code, doc in views.items()
        for note in usj.notes_of(doc["content"])
        if note.get("x-key") == key
    )
    origin = next(p for p in note["content"] if usj.is_origin(p))
    words = usj.text_of([p for p in note["content"] if p is not origin]).strip()
    text = dict(books)[code]
    assert f"\\fr {usj.text_of([origin]).strip()} " in text, key
    assert words[:40] in text, key
    # The Psalter's chapters are labelled as the book prints them.
    assert "\n\\cl Psalm\n\\c 1\n" in dict(books)["PSA"]
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
        assert {i.external_attr >> 16 for i in archive.infolist()} == {0o644}
    # The published zip is readable by all, and nothing is left beside it.
    assert (tmp_path / paths.USFM_ZIP).stat().st_mode & 0o777 == 0o644
    assert [p.name for p in tmp_path.iterdir()] == [paths.USFM_ZIP]


def test_a_failed_zip_leaves_the_published_copy_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(paths, "DIST_DIR", tmp_path)
    publish_usfm([("GEN", "\\id GEN\n")])
    first = (tmp_path / paths.USFM_ZIP).read_bytes()
    with pytest.raises(TypeError):
        publish_usfm([("EXO", None)])  # type: ignore[list-item]
    assert (tmp_path / paths.USFM_ZIP).read_bytes() == first
    assert [p.name for p in tmp_path.iterdir()] == [paths.USFM_ZIP]
