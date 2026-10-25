"""The web boundary preserves the prepared USJ and its scripture inventory."""

from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from bible import export, files, peripherals, pipeline, scripture, typeface, usj, web
from bible.checks import CheckFailed
from bible.sources import Sources


def test_web_fonts(tmp_path: Path) -> None:
    """WOFF changes the wrapper, preserving every font table: of OLEBFont's
    faces, and of the Greek and Hebrew fonts the typesetter sets quotations
    in. The stylesheet declares every face written, under the families the
    site sets each script in."""
    first, second = tmp_path / "first", tmp_path / "second"
    web.write_fonts(first)
    web.write_fonts(second)
    faces = typeface.installed()
    assert {p.name for p in first.iterdir()} == {
        *(web.font_file(face) for face in faces),
        "fonts.css",
    }
    assert [web.font_file(face) for face in faces][:4] == [
        f"OLEBFont-{style}.woff"
        for style in ("Bold", "BoldItalic", "Italic", "Regular")
    ]
    assert web.font_file(typeface.HEBREW) == "SILEOT.woff"
    css = (first / "fonts.css").read_text(encoding="utf-8")
    assert css.count("@font-face") == len(faces)
    for face in faces:
        assert f'url("./{web.font_file(face)}")' in css
        assert f'font-family: "{typeface.family(face)}";' in css
    assert '--edition-font-latin: "OLEBFont";' in css
    assert f'--edition-font-greek: "{typeface.greek_family()}";' in css
    assert '--edition-font-hebrew: "Ezra SIL";' in css
    assert "font-weight: 700;\n  font-style: italic;" in css.split("@font-face")[2]
    for output in first.iterdir():
        assert output.read_bytes() == (second / output.name).read_bytes()
    for face in faces:
        with (
            TTFont(face) as original,
            TTFont(first / web.font_file(face)) as exported,
        ):
            assert exported.flavor == "woff"
            assert set(original.keys()) == set(exported.keys())
            # Compare serialized tables before decompilation: this includes
            # outlines, hints, metrics, coverage, features, names, and copyright.
            for tag in original.keys():
                if tag == "GlyphOrder":
                    continue
                before, after = original.getTableData(tag), exported.getTableData(tag)
                if tag == "head":
                    # The checksum adjustment belongs to the file wrapper.
                    before = before[:8] + before[12:]
                    after = after[:8] + after[12:]
                assert before == after, (face.name, tag)
            assert original.getGlyphOrder() == exported.getGlyphOrder()
            assert original.getBestCmap() == exported.getBestCmap()


@pytest.mark.parametrize("script", ["LATIN", "GREEK"])
def test_missing_web_fonts(
    script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(typeface, script, tmp_path / "none")
    with pytest.raises(
        CheckFailed, match="No fonts installed in .*none; run make bootstrap"
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
        if "introduction" in book:
            introduction = files.read_json(tmp_path / "books" / code / "prologue.json")
            blocks += introduction["content"][1:]
        for chapter in book["chapters"]:
            part = files.read_json(
                tmp_path / "books" / code / f"{chapter['number']}.json"
            )
            assert part["content"][0] == doc["content"][0]
            blocks += part["content"][1:]
        assert usj.with_blocks(doc, blocks) == doc
    # Chapter openings start ordinary paragraphs in the shared text, even
    # where Brenton or Scrivener continues the preceding chapter's paragraph.
    for code, chapter in (("GEN", "2"), ("MAT", "5"), ("ROM", "1")):
        part = files.read_json(tmp_path / "books" / code / f"{chapter}.json")
        at = next(i for i, n in enumerate(part["content"]) if n["type"] == "chapter")
        assert usj.paragraph(part["content"][at + 1]) == "p"
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
    # A source subscription remains available as paratext, outside verse words.
    romans = files.read_json(tmp_path / "books" / "ROM" / "16.json")
    sidebar = romans["content"][-1]
    assert (sidebar["type"], sidebar["category"]) == ("sidebar", "colophon")
    assert "Written to the Romans" in usj.text_of(sidebar["content"])
    assert "¶" not in usj.text_of(sidebar["content"])
    acts = files.read_json(tmp_path / "books" / "ACT" / "28.json")
    assert not any(n.get("category") == "colophon" for n in acts["content"])
    assert "Written to the Romans" not in scripture.verses(romans)["16:24"].text
    for code, chapter, years in (
        ("MAT", "28", "eight"),
        ("MRK", "16", "ten"),
        ("LUK", "24", "fifteen"),
        ("JHN", "21", "thirty-two"),
    ):
        gospel = files.read_json(tmp_path / "books" / code / f"{chapter}.json")
        sidebar = gospel["content"][-1]
        assert (sidebar["type"], sidebar["category"]) == ("sidebar", "colophon")
        assert usj.text_of(sidebar["content"]) == (
            f"Published {years} years after the ascension of Christ."
        )
        assert "Published" not in next(reversed(scripture.verses(gospel).values())).text
    # Ordinary footnotes carry reference nodes without cross-reference fields.
    assert any(n["type"] == "ref" for n in usj.walk(genesis["content"]))
    assert all(
        n.get("marker") != "xt"
        for note in usj.notes_of(genesis["content"])
        if note["marker"] == "f"
        for n in usj.walk(note["content"])
    )
    daniel = next(b for b in manifest["books"] if b["id"] == "DAG")
    labels = [c["label"] for c in daniel["chapters"] if c["titled"]]
    assert labels == ["Susanna", "Bel and the Dragon"]
    # Sirach's Prologue is a book introduction, not a chapter.
    sirach = next(b for b in manifest["books"] if b["id"] == "SIR")
    assert sirach["chapters"][0]["number"] == "1"
    assert sirach["introduction"]["slug"] == "prologue"
    assert sirach["introduction"]["title"].startswith(
        "The Prologue to the Wisdom of Jesus"
    )
    prologue = files.read_json(tmp_path / "books" / "SIR" / "prologue.json")
    assert not any(
        n["type"] in {"chapter", "verse"} for n in usj.walk(prologue["content"])
    )
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
    """The front matter and website-only numbering page, in reading order,
    each unit the whole document but for the names the manifest carries,
    with its printed title and its Greek and Hebrew tagged for their fonts."""
    documents = dict(pipeline.view(edition, "pdf"))
    listed = web.matter(edition, documents)
    assert [(unit["id"], unit["section"]) for unit, _ in listed] == [
        ("introduction", "front"),
        ("numbering", "front"),
        ("brenton-preface", "old_testament"),
        ("brenton-introduction", "old_testament"),
        ("dedication", "new_testament"),
        ("translators-to-reader", "new_testament"),
    ]
    units = {unit["id"]: unit for unit, _ in listed}
    assert units["dedication"]["title"] == "The Epistle Dedicatory"
    assert units["introduction"]["title"] == "Introduction"
    source_codes = {unit.slug: code for code, unit in peripherals.UNITS.items()}
    blocks = {}
    for unit, doc in listed:
        code = source_codes[unit["id"]]
        whole = usj.with_content(
            edition.numbering_page if code == "XXA" else documents[code],
            export.font_runs,
        )
        book, division = doc["content"]
        assert book == {
            **whole["content"][0],
            "code": peripherals.book(code),
        }
        assert division["type"] == "periph"
        assert division["id"] == peripherals.UNITS[code].periph
        assert division["alt"] == unit["title"]
        blocks[unit["id"]] = division["content"]
        assert division["content"] == [
            b for b in whole["content"][1:] if b.get("marker") not in web.NAMES
        ]
        assert (
            sum(b.get("marker") == "mt1" for b in usj.objects(division["content"])) == 1
        )
    markers = {
        slug: [b.get("marker") for b in usj.objects(body)]
        for slug, body in blocks.items()
    }
    assert markers["dedication"][:6] == ["mt2", "mt1", "mt2", "mt2", "mt2", "po"]
    assert any(node.get("marker") == "th1" for node in usj.walk(blocks["numbering"]))
    assert "li1" in markers["brenton-introduction"]
    assert "ili2" not in markers["brenton-introduction"]
    tagged = {
        slug: {
            node["marker"]
            for node in usj.walk(body)
            if node.get("marker") in ("wg", "wh")
        }
        for slug, body in blocks.items()
    }
    assert tagged["brenton-preface"] == {"wg", "wh"}
    assert "wg" in tagged["translators-to-reader"]


def test_variants(edition: pipeline.Edition) -> None:
    """The textual variants, by book, each entry the verse it is about,
    with the King James number where it differs and its lanes, with the
    prose that opens the page and without the names the site prints
    itself."""
    listed = web.variants(edition)
    assert listed["title"] == "Textual Variants"
    assert listed["terms"] == {"kjv": "KJV", "apparatus": "apparatus"}
    assert {block["marker"] for block in listed["intro"]} == {"p"}
    assert usj.text_of(listed["intro"][-1]["content"]).startswith(
        "The Greek retains its accents and punctuation"
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
