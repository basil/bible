"""The English texts of the reconciliation: the King James books the read
stage parsed, and the RV, ASV and Boyd's ASV witnesses, read through the
document model."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import pytest
from lxml import html

from bible import scripture, usj
from bible.byzantine import BOOKS, BOYD_ASV, english
from bible.sources import Content
from bible.usj import Document

type Reading = tuple[dict[str, Document], dict[str, scripture.Verse]]
type KjvReading = tuple[
    dict[str, Document], dict[str, scripture.Verse], dict[str, list[usj.Node]]
]


@pytest.fixture(scope="module")
def kjv_reading(
    byzantine: Mapping[str, Any],
) -> KjvReading:
    return english.kjv(byzantine["kjv_documents"])


@pytest.fixture(scope="module")
def readings(byzantine_inputs: Mapping[str, Content]) -> dict[str, Reading]:
    return {
        "rv": english.rv(byzantine_inputs["rv"]),
        "asv": english.asv(byzantine_inputs["asv"]),
        BOYD_ASV: english.boyd_asv(byzantine_inputs["boyd_asv"]),
    }


# The KJV.


def test_pinned_kjv_inventory_and_real_verses(
    kjv_reading: KjvReading,
    kjv_text: Mapping[str, str],
) -> None:
    documents, verses, _ = kjv_reading
    assert len(documents) == 27 and list(documents) == BOOKS
    assert len(verses) == 7957
    assert {ref: v.text for ref, v in verses.items()} == kjv_text
    assert (
        kjv_text["MAT 1:1"] == "The book of the generation of Jesus Christ, "
        "the son of David, the son of Abraham."
    )
    assert kjv_text["MAT 3:8"] == "Bring forth therefore fruits meet for repentance:"
    assert kjv_text["ROM 16:25"].startswith("Now to him that is of power")
    assert "ROM 14:24" not in kjv_text
    assert kjv_text["ACT 8:37"].startswith("And Philip said, If thou believest")
    assert all(verse.text.strip() for verse in verses.values())
    # Supplied-word styles survive into the document model.
    assert "\\add with\\add*" in usj.serialize(documents["MAT"])
    assert usj.book_code(documents["MAT"]) == "MAT"
    assert documents["MAT"]["content"][0]["content"] == [
        "- The Cambridge Paragraph Bible of the Authorized English Version"
    ]


def test_kjv_reader_is_pure(
    byzantine: Mapping[str, Any],
    kjv_reading: KjvReading,
) -> None:
    before = copy.deepcopy(byzantine["kjv_documents"])
    assert english.kjv(byzantine["kjv_documents"]) == kjv_reading
    assert byzantine["kjv_documents"] == before


def test_kjv_reader_checks_its_inventory(byzantine: Mapping[str, Any]) -> None:
    documents = byzantine["kjv_documents"]
    empty = usj.document([{"type": "book", "marker": "id", "code": "JUD"}])
    with pytest.raises(ValueError, match="KJV inventory"):
        english.kjv({**documents, "JUD": empty})
    # A subscription that is not the close of its book is refused.
    unclosed = usj.with_blocks(
        documents["ROM"],
        [*documents["ROM"]["content"][:-2], documents["ROM"]["content"][-1]],
    )
    with pytest.raises(ValueError, match="subscription is not the book's close"):
        english.kjv({**documents, "ROM": unclosed})


def test_subscriptions_removed_immutably_and_other_matter_kept() -> None:
    doc = usj.parse(
        "\\id ROM\n\\c 1\n\\p\n\\v 1 Scripture.\n\\mi ¶ Subscription.\n\\mi Other matter."
    )
    before = copy.deepcopy(doc)
    clean = english.without_subscriptions(doc)
    assert doc == before
    assert len(doc["content"]) - len(clean["content"]) == 1
    assert "Other matter." in usj.text_of(clean["content"])
    assert "Subscription." not in usj.text_of(clean["content"])


def test_pinned_subscriptions_are_not_verses(
    kjv_reading: KjvReading,
    kjv_text: Mapping[str, str],
) -> None:
    documents, _, taken = kjv_reading
    # Romans' subscription ("Written to the Romans from Corinthus...") is gone.
    assert "Corinthus" not in usj.text_of(
        documents["ROM"]["content"][-1].get("content", [])
    )
    assert kjv_text["ROM 16:27"].endswith("Amen.")
    assert (
        kjv_text["PHM 1:25"]
        == "The grace of our Lord Jesus Christ be with your spirit. Amen."
    )
    # It is taken off with the blank line before it, to be put back.
    assert len(taken) == 14 and all(len(blocks) == 2 for blocks in taken.values())
    assert [b.get("marker") for b in taken["ROM"]] == ["b", "mi"]
    assert "Corinthus" in usj.text_of(taken["ROM"])


# Supplied words and markup.


def test_supplied_spans_keep_punctuation_paragraph_offsets_and_ignore_notes() -> None:
    doc = usj.parse(
        "\\id MAT\n\\c 1\n\\p\n\\v 1 Say \\add it?\\add*"
        "\\f + \\ft A note with \\+add supplied\\+add* words.\\f*"
        "\n\\q1 Then \\add again\\add*."
    )
    verse = scripture.verses(doc)["1:1"]
    before = copy.deepcopy(doc)
    spans = english.supplied_spans(doc, verse)
    assert spans == [(4, 7, "it?"), (13, 18, "again")]
    assert all(verse.text[lo:hi] == text for lo, hi, text in spans)
    assert spans[1][0] == verse.text.index("again")
    assert doc == before
    with pytest.raises(ValueError, match="context differs"):
        english.supplied_spans(doc, replace(verse, text="Changed " + verse.text))


def test_pinned_supplied_words_are_available_for_english_review(
    kjv_reading: KjvReading,
    byzantine: Mapping[str, Any],
    kjv_text: Mapping[str, str],
) -> None:
    documents, verses, _ = kjv_reading
    spans = english.supplied_spans(documents["LUK"], verses["LUK 6:9"])
    assert spans == [(46, 52, "thing;"), (141, 144, "it?")]
    assert byzantine["supplied"]["LUK 6:9"] == spans
    assert len(byzantine["supplied"]) == 3872
    assert byzantine["supplied"]["MAT 3:11"] == [(180, 184, "with")]
    assert kjv_text["MAT 3:11"][180:184] == "with"
    assert "MAT 3:8" not in byzantine["supplied"]


def test_verse_markup_shows_italics_without_usfm(
    kjv_reading: KjvReading,
) -> None:
    documents, verses, _ = kjv_reading
    passage = english.verse_markup(documents["MAT"], verses["MAT 3:11"])
    assert passage.endswith(
        "he shall baptize you with the Holy Ghost, and <i>with</i> fire:"
    )
    assert "\\" not in passage
    assert (
        english.usj_markup(["a ", usj.char("add", "b"), " & ", usj.note("f", "note")])
        == "a <i>b</i> &amp; "
    )
    nested = usj.char("add", "x ", usj.char("it", "y"))
    assert english.usj_markup([nested]) == "<i>x y</i>"


# The revisions.


def test_revision_verse_placements_and_empty_rv_records(
    readings: dict[str, Reading],
) -> None:
    _, rv = readings["rv"]
    _, asv = readings["asv"]
    _, boyd = readings[BOYD_ASV]
    assert len(rv) == 7957 and len(asv) == 7957
    assert sum(not v.text.strip() for v in rv.values()) == 16
    assert sum(not v.text.strip() for v in asv.values()) == 16
    assert "ROM 16:25" in rv and "ROM 14:24" not in rv
    assert not rv["ACT 8:37"].text.strip()
    assert rv["MAT 3:8"].text == "Bring forth therefore fruit worthy of repentance:"
    assert len(boyd) == 7953
    assert "ROM 14:24" in boyd and "ROM 16:25" not in boyd and "3JN 1:15" not in boyd
    assert all(v.text.strip() for v in boyd.values())
    # Boyd's HTML keeps a space before the next verse's marker.
    assert boyd["MAT 3:8"].text == "Bring forth therefore fruit worthy of repentance: "


def test_revisions_round_trip_source_words(readings: dict[str, Reading]) -> None:
    for name in ("rv", BOYD_ASV):
        documents, _ = readings[name]
        assert len(documents) == 27
        for book in ("MAT", "ROM", "PHM", "REV"):
            doc = documents[book]
            before = {
                ref: scripture.plain(v.text) for ref, v in scripture.verses(doc).items()
            }
            after = {
                ref: scripture.plain(v.text)
                for ref, v in scripture.verses(usj.parse(usj.serialize(doc))).items()
            }
            assert before == after, (name, book)


def test_asv_reads_its_poetry_and_indented_paragraphs(
    readings: dict[str, Reading], byzantine: Mapping[str, Any]
) -> None:
    _, asv = readings["asv"]
    assert asv["1TI 3:16"].text.endswith("Received up in glory.")
    assert asv["REV 4:11"].text.startswith("Worthy art thou, our Lord and our God")
    texts = byzantine["texts"]
    assert {ref: v.text for ref, v in asv.items()} == texts["asv"]
    # Boyd's ASV is re-addressed to the KJV's verses for comparison.
    assert len(texts[BOYD_ASV]) == 7957
    assert texts[BOYD_ASV]["ROM 16:25"] == readings[BOYD_ASV][1]["ROM 14:24"].text
    assert sum(not v.strip() for v in texts[BOYD_ASV].values()) == 4


def test_surface_words_drop_lexical_metadata() -> None:
    assert (
        english.surface_words(
            '\\w Bring|strong="G4160"\\w* forth \\+w fruit|lemma="fruit"\\+w*'
        )
        == "Bring forth fruit"
    )
    assert english.surface_words("plain words") == "plain words"


def test_boyd_supplied_words_are_semantic_and_numbers_are_not_verse_text() -> None:
    node = html.fromstring(
        '<div class="q"><span class="verse" id="V1">1&#160;</span>'
        'Before <span class="add">supplied</span> after.</div>'
    )
    before = html.tostring(node)
    para = english.boyd_paragraph(node)
    assert para["marker"] == "q1"
    assert usj.text_of(para["content"]).strip() == "Before supplied after."
    assert [
        n for n in para["content"] if isinstance(n, dict) and n.get("marker") == "add"
    ] == [usj.char("add", "supplied")]
    assert [
        n for n in para["content"] if isinstance(n, dict) and n.get("type") == "verse"
    ] == [{"type": "verse", "marker": "v", "number": "1"}]
    assert html.tostring(node) == before


@pytest.mark.parametrize(
    "fragment, message",
    [
        (
            '<div class="p"><span class="verse" id="V1">2</span>Words</div>',
            "Malformed Boyd verse marker",
        ),
        (
            '<div class="p"><span class="verse" id="bad">1</span>Words</div>',
            "Malformed Boyd verse marker",
        ),
        (
            '<div class="p"><span class="new">Words</span></div>',
            "Unknown Boyd scripture span: new",
        ),
        ('<div class="p"><em>Words</em></div>', "Unknown Boyd scripture child: em"),
        ('<div class="new">Words</div>', "Unknown Boyd scripture paragraph"),
    ],
)
def test_boyd_unknown_markup_and_malformed_markers_fail(
    fragment: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        english.boyd_paragraph(html.fromstring(fragment))


def test_missing_books_and_chapters_fail() -> None:
    with pytest.raises(ValueError, match="Expected one pinned RV book"):
        english.rv(Content({}))
    with pytest.raises(ValueError, match="Expected one pinned ASV book"):
        english.asv(Content({}))
    with pytest.raises(ValueError, match="Boyd ASV inventory"):
        english.boyd_asv(Content({}))


def test_citation_metadata_normalizes_words_and_supplied_offsets_together() -> None:
    doc = usj.parse(
        "\\id MAT\n\\c 1\n\\p\n\\v 1 Before   \\add two   words\\add*  after."
    )
    verse = scripture.verses(doc)["1:1"]
    assert english.citation_metadata(doc, verse) == {
        "text": "Before two words after.",
        "supplied": [(7, 16)],
    }
    # The RV keeps the following space inside its markup; the span stops at the word.
    doc = usj.parse("\\id MAT\n\\c 1\n\\p\n\\v 1 warned \\add of God \\add*in a dream.")
    verse = scripture.verses(doc)["1:1"]
    assert english.citation_metadata(doc, verse) == {
        "text": "warned of God in a dream.",
        "supplied": [(7, 13)],
    }


def test_revision_supplied_spans_are_whole_words(byzantine: Mapping[str, Any]) -> None:
    for witness, rows in byzantine["revision_citations"].items():
        for ref, row in rows.items():
            for lo, hi in (row or {}).get("supplied", []):
                assert row["text"][lo:hi] == row["text"][lo:hi].strip(), (witness, ref)


def test_boyd_citation_metadata_uses_kjv_addresses(
    byzantine: Mapping[str, Any], readings: dict[str, Reading]
) -> None:
    docs, verses = readings[BOYD_ASV]
    moved = byzantine["structure"].moved
    assert moved
    for kjv_ref, source_ref in moved.items():
        assert byzantine["revision_citations"][BOYD_ASV][
            kjv_ref
        ] == english.citation_metadata(docs[source_ref.split()[0]], verses[source_ref])
