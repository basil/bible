"""The web boundary preserves the prepared USJ and its scripture inventory."""

from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from bible import export, files, paths, pipeline, scripture, usj, web
from bible.checks import CheckFailed
from bible.sources import Sources


def test_web_fonts(tmp_path: Path) -> None:
    """WOFF changes the wrapper, preserving every font table: of the
    edition's own faces, and of the Greek and Hebrew fonts the typesetter
    sets quotations in."""
    first, second = tmp_path / "first", tmp_path / "second"
    web.write_fonts(first)
    web.write_fonts(second)
    assert {p.name for p in first.iterdir()} == set(web.FONTS)
    assert {name.split("-")[0] for name in web.FONTS} == {
        "OLEBFont",
        "GFSDidot",
        "EzraSIL",
    }
    for output in first.iterdir():
        assert output.read_bytes() == (second / output.name).read_bytes()
    for name, source in web.FONTS.items():
        with (
            TTFont(source) as original,
            TTFont(first / name) as exported,
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
                assert before == after, (name, tag)
            assert original.getGlyphOrder() == exported.getGlyphOrder()
            assert original.getBestCmap() == exported.getBestCmap()


@pytest.mark.parametrize("name", ["OLEBFont-Regular.woff", "EzraSIL-Regular.woff"])
def test_missing_web_fonts(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(web.FONTS, name, tmp_path / "missing.ttf")
    with pytest.raises(
        CheckFailed, match="Missing installed font input missing.ttf.*make bootstrap"
    ):
        web.write_fonts(tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_web(edition: pipeline.Edition, tmp_path: Path) -> None:
    stale = tmp_path / "stale.json"
    stale.write_text("{}")
    web.write(edition, tmp_path)
    assert not stale.exists()
    manifest = files.read_json(tmp_path / "manifest.json")
    assert [b["id"] for b in manifest["books"]] == [
        u["id"] for u in edition.policy.scripture
    ]
    assert manifest["books"][0]["short"] == "Genesis"
    # A chapter is cited by the name the edition cites one chapter by.
    assert manifest["books"][0]["cited"] == "Genesis"
    psalms = next(b for b in manifest["books"] if b["id"] == "PSA")
    assert (psalms["short"], psalms["cited"]) == ("Psalms", "Psalm")
    documents = dict(pipeline.view(edition, "pdf"))
    assert {p.name for p in (tmp_path / "books").iterdir()} == edition.scripture
    assert {p.name for p in (tmp_path / "matter").iterdir()} == {
        f"{u['id']}.json" for u in manifest["matter"]
    }
    for unit, doc in web.matter(edition, documents):
        assert unit in manifest["matter"]
        assert files.read_json(tmp_path / "matter" / f"{unit['id']}.json") == doc
    for book in manifest["books"]:
        code = book["id"]
        assert {c["number"]: c["verses"] for c in book["chapters"]} == dict(
            edition.inventory[code]
        )
        # The chapters, less the book node each repeats, are the whole book
        # but for the names the manifest carries, its notes under the labels
        # their verses print, and its Greek and Hebrew tagged for their fonts.
        doc = usj.with_content(
            export.with_printed_origins(documents[code]), export.font_runs
        )
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
    # Greek and Hebrew are tagged for their fonts, as the typesetter has them.
    genesis = files.read_json(tmp_path / "books" / "GEN" / "1.json")
    assert any(
        node.get("marker") == "wg" and usj.text_of(node["content"]).startswith("εἰς")
        for node in usj.walk(genesis["content"])
    )
    kingdoms = files.read_json(tmp_path / "books" / "2SA" / "5.json")
    assert any(
        node.get("marker") == "wh" and usj.text_of(node["content"]) == "רפאים"
        for node in usj.walk(kingdoms["content"])
    )
    daniel = next(b for b in manifest["books"] if b["id"] == "DAG")
    labels = [c["label"] for c in daniel["chapters"] if c["titled"]]
    assert labels == ["Susanna", "Bel and the Dragon"]
    # Sirach's Prologue is a chapter its title stands for.
    sirach = next(b for b in manifest["books"] if b["id"] == "SIR")
    prologue = sirach["chapters"][0]
    assert (prologue["number"], prologue["titled"]) == ("0", True)
    assert prologue["label"].startswith("The Prologue to the Wisdom of Jesus")
    # The stasis rule set before Psalm 4 opens it, not the close of Psalm 3.
    psalms = tmp_path / "books" / "PSA"
    rule, chapter = files.read_json(psalms / "4.json")["content"][1:3]
    assert (rule.get("marker"), chapter["type"]) == ("sd2", "chapter")
    assert all(
        b.get("marker") != "sd2" for b in files.read_json(psalms / "3.json")["content"]
    )


def test_comparisons(edition: pipeline.Edition) -> None:
    """Each passage is quoted from the edition and from the King James verses
    the place stage pairs with it, under the names the edition cites by."""
    documents = dict(pipeline.view(edition, "pdf"))
    compared = {c["reference"]: c for c in web.comparisons(edition, documents)}
    assert len(compared) == len(edition.policy.comparisons["passages"])
    psalm = compared["Psalm 23:7"]
    assert psalm["kjvReference"] == "Psalm 24:7"
    assert "".join(s["text"] for s in psalm["kjv"]) == scripture.plain(
        scripture.verses(edition.read.kjv["PSA"])["24:7"].text
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


def test_matter(edition: pipeline.Edition) -> None:
    """The front matter the book prints, in its order and under its section,
    each unit the whole document but for the names the manifest carries,
    with its printed title and its Greek and Hebrew tagged for their fonts;
    the editor's pages as the editor wrote them."""
    documents = dict(pipeline.view(edition, "pdf"))
    listed = web.matter(edition, documents)
    assert [(unit["id"], unit["section"]) for unit, _ in listed] == [
        ("XXD", "front"),
        ("CNC", "front"),
        ("XXA", "front"),
        ("XXB", "old_testament"),
        ("XXE", "old_testament"),
        ("TDX", "new_testament"),
        ("NDX", "new_testament"),
    ]
    units = {unit["id"]: unit for unit, _ in listed}
    assert units["XXD"]["short"] == "Abbreviations"
    assert units["TDX"]["title"] == "The Epistle Dedicatory"
    assert units["CNC"]["title"] == "Editor’s Introduction"
    for unit, doc in listed:
        code = unit["id"]
        whole = documents[code]
        if code not in edition.authored:
            whole = usj.with_content(whole, export.font_runs)
        assert doc["content"][0]["type"] == "book"
        assert doc["content"][0] == whole["content"][0]
        assert doc == usj.with_blocks(
            whole,
            [b for b in whole["content"] if b.get("marker") not in web.NAMES],
        )
        assert [b.get("marker") for b in doc["content"][1:]].count("mt1") == 1
    markers = {
        unit["id"]: [b.get("marker") for b in doc["content"][1:]]
        for unit, doc in listed
    }
    # The dedication's address stands around its title, as printed.
    assert markers["TDX"][:6] == ["mt2", "mt1", "mt2", "mt2", "mt2", "mt2"]
    assert markers["XXD"][0] == "mt1"
    blocks = {unit["id"]: doc["content"] for unit, doc in listed}
    assert any(b["type"] == "table" for b in blocks["XXD"])
    assert any(node.get("marker") == "th1" for node in usj.walk(blocks["XXA"]))
    tagged = {
        code: {
            node["marker"]
            for node in usj.walk(content)
            if node.get("marker") in ("wg", "wh")
        }
        for code, content in blocks.items()
    }
    assert tagged["XXB"] == {"wg", "wh"}
    assert "wg" in tagged["NDX"]
    assert tagged["CNC"] == set()


def test_variants(edition: pipeline.Edition) -> None:
    """The textual variants, by book, each entry the verse it is about,
    with the King James number where it differs and its lanes, with the
    prose that opens the page and without the names the site prints
    itself."""
    listed = web.variants(edition)
    assert listed["title"] == "Textual Variants"
    assert listed["terms"] == {"kjv": "KJV", "apparatus": "apparatus"}
    assert {block["marker"] for block in listed["intro"]} == {"ip"}
    assert usj.text_of(listed["intro"][-1]["content"]).startswith(
        "The Greek is Scrivener’s"
    )
    books = listed["books"]
    assert [book["id"] for book in books] == [
        unit["id"]
        for unit in edition.policy.scripture
        if unit["section"] == "new_testament"
    ]
    entries = [entry for book in books for entry in book["entries"]]
    assert len(entries) == len(edition.variants)
    for entry, (row, lanes) in zip(entries, edition.variants, strict=True):
        assert row.reference.split()[1] == f"{entry['chapter']}:{entry['verse']}"
        assert ("kjv" in entry) == (row.source != row.reference)
        assert entry.get("kjv", row.reference.split()[1]) == row.source.split()[1]
        assert entry["lanes"] == lanes
    matthew = books[0]["entries"][0]
    assert matthew["chapter"] == "1"
    # A moved verse is listed under the edition's number with the King
    # James Bible's beside it.
    romans = next(book for book in books if book["id"] == "ROM")
    doxology = next(
        e for e in romans["entries"] if (e["chapter"], e["verse"]) == ("14", "24")
    )
    assert doxology["kjv"] == "16:25"
    # An omitted verse of the Received Text is listed under its own number,
    # each lane the source's words alone.
    luke = next(book for book in books if book["id"] == "LUK")
    omitted = next(
        e for e in luke["entries"] if (e["chapter"], e["verse"]) == ("17", "36")
    )
    assert "36" not in edition.inventory["LUK"]["17"]
    assert [lane["language"] for lane in omitted["lanes"]] == ["grc", "en"]
    for lane in omitted["lanes"]:
        (reading,) = lane["segments"]
        assert isinstance(reading, dict) and set(reading) == {"from"}
