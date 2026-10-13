"""The web boundary preserves the prepared USJ and its scripture inventory."""

from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from bible import files, paths, pipeline, scripture, usj, web
from bible.checks import CheckFailed
from bible.sources import Sources


def test_web_fonts(tmp_path: Path) -> None:
    """WOFF changes the wrapper, preserving every font table."""
    first, second = tmp_path / "first", tmp_path / "second"
    web.write_fonts(first)
    web.write_fonts(second)
    installed = paths.FONTS / "olebfont"
    assert {p.name for p in first.iterdir()} == {
        f"OLEBFont-{style}.woff" for style in web.FONT_STYLES
    }
    for output in first.iterdir():
        assert output.read_bytes() == (second / output.name).read_bytes()
    for style in web.FONT_STYLES:
        with (
            TTFont(installed / f"OLEBFont-{style}.otf") as original,
            TTFont(first / f"OLEBFont-{style}.woff") as exported,
        ):
            assert exported.flavor == "woff"
            assert set(original.keys()) == set(exported.keys())
            # Compare serialized tables before decompilation: this includes
            # outlines, hints, metrics, coverage, features, names and copyright.
            for tag in original.keys():
                if tag == "GlyphOrder":
                    continue
                before, after = original.getTableData(tag), exported.getTableData(tag)
                if tag == "head":
                    # The checksum adjustment belongs to the file wrapper.
                    before = before[:8] + before[12:]
                    after = after[:8] + after[12:]
                assert before == after, (style, tag)
            assert original.getGlyphOrder() == exported.getGlyphOrder()
            assert original.getBestCmap() == exported.getBestCmap()


def test_missing_web_fonts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "FONTS", tmp_path)
    with pytest.raises(
        CheckFailed, match="Missing installed font input.*make bootstrap"
    ):
        web.write_fonts(tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_web(sources: Sources, edition: pipeline.Edition, tmp_path: Path) -> None:
    stale = tmp_path / "stale.json"
    stale.write_text("{}")
    web.write(sources, edition, tmp_path)
    assert not stale.exists()
    manifest = files.read_json(tmp_path / "manifest.json")
    assert [b["id"] for b in manifest["books"]] == [
        u["id"] for u in edition.policy.scripture
    ]
    assert manifest["books"][0]["short"] == "Genesis"
    documents = dict(pipeline.view(edition, "pdf"))
    assert {p.name for p in (tmp_path / "books").iterdir()} == edition.scripture
    for book in manifest["books"]:
        code = book["id"]
        assert {c["number"]: c["verses"] for c in book["chapters"]} == dict(
            edition.inventory[code]
        )
        # The chapters, less the book node each repeats, are the whole book
        # but for the names the manifest carries.
        doc = documents[code]
        doc = usj.with_blocks(
            doc,
            [
                block
                for block in doc["content"]
                if block.get("marker") not in usj.BOOK_PARAGRAPHS
            ],
        )
        blocks = [doc["content"][0]]
        for chapter in book["chapters"]:
            part = files.read_json(
                tmp_path / "books" / code / f"{chapter['number']}.json"
            )
            assert part["content"][0] == doc["content"][0]
            blocks += part["content"][1:]
        assert usj.with_blocks(doc, blocks) == doc
    daniel = next(b for b in manifest["books"] if b["id"] == "DAG")
    labels = [c["label"] for c in daniel["chapters"] if c["titled"]]
    assert labels == ["Susanna", "Bel and the Dragon"]
    # The stasis rule set before Psalm 4 opens it, not the close of Psalm 3.
    psalms = tmp_path / "books" / "PSA"
    rule, chapter = files.read_json(psalms / "4.json")["content"][1:3]
    assert (rule.get("marker"), chapter["type"]) == ("sd2", "chapter")
    assert all(
        b.get("marker") != "sd2" for b in files.read_json(psalms / "3.json")["content"]
    )


def test_comparisons(sources: Sources, edition: pipeline.Edition) -> None:
    """Each passage is quoted from the edition and from the King James verses
    the place stage pairs with it, under the names the edition cites by."""
    documents = dict(pipeline.view(edition, "pdf"))
    compared = {c["reference"]: c for c in web.comparisons(edition, documents, sources)}
    assert len(compared) == len(edition.policy.comparisons["passages"])
    psalm = compared["Psalm 23:7"]
    assert psalm["kjvReference"] == "Psalm 24:7"
    assert "".join(s["text"] for s in psalm["kjv"]) == scripture.plain(
        scripture.verses(usj.parse(sources.kjv["PSA"]))["24:7"].text
    )
    assert [s["text"] for s in psalm["oleb"] if s["changed"]] == [
        "your gates, ye princes,"
    ]
    assert compared["Esaias 40:13–14"]["kjvReference"] == "Isaiah 40:13–14"
    assert {ref for ref, row in compared.items() if "osb" in row} == {
        "Esaias 40:13–14",
        "Luke 23:42",
        "John 8:11",
        "1 John 5:7–8",
        "Revelation 21:6",
        "Revelation 22:19",
    }
    assert "".join(s["text"] for s in compared["Luke 23:42"]["osb"]) == (
        "Then he said to Jesus, ‘Lord, remember me when You come into Your kingdom.’"
    )
    assert [s["text"] for s in compared["Revelation 22:19"]["osb"] if s["changed"]] == [
        "the Book of Life,"
    ]


@pytest.mark.parametrize(
    ("phrases", "message"),
    [
        (["still waters", "waters"], "overlap"),
        (["e"], "exactly once"),
        (["absent"], "exactly once"),
    ],
)
def test_spans_refuse_unplaceable_highlights(phrases: list[str], message: str) -> None:
    with pytest.raises(CheckFailed, match=message):
        web.spans("He leadeth me beside the still waters.", phrases)


def test_spans_take_closing_punctuation() -> None:
    assert web.spans("Lift up, O ye gates; and be.", ["O ye gates"]) == [
        {"text": "Lift up, ", "changed": False},
        {"text": "O ye gates;", "changed": True},
        {"text": " and be.", "changed": False},
    ]
