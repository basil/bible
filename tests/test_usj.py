"""USJ: reading and writing USFM, and changing content by its words."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

import bible.pipeline
import bible.sources
from bible import scripture, usj
from bible.checks import CheckFailed
from bible.usj import Node

type Shape = str | tuple[str, str | None, str | None, list[Shape]]

BOOK = (
    "\\id GEN - Brenton\n\\h Genesis\n\\mt1 GENESIS\n\\c 1  \n\\p\n"
    "\\v 1 \\sc In\\sc* the beginning \\add was\\add* light \\f + \\fr 1:1 \\fqa Gr. \\ft a \\+it note\\+it*.\\f*and day.  \n"
    "\\v 2 Poetry,\n\\q1 line two\n\\c 2\n\\cp A\n\\p\n\\v 1 Next.\n"
)


def test_a_document_is_plain_usj() -> None:
    doc = usj.parse(BOOK)
    assert doc["type"] == "USJ"
    book, h, mt, chapter, para, line, second, last = doc["content"]
    assert book == {
        "type": "book",
        "marker": "id",
        "code": "GEN",
        "content": ["- Brenton"],
    }
    assert chapter == {"type": "chapter", "marker": "c", "number": "1"}
    assert second == {"type": "chapter", "marker": "c", "number": "2", "pubnumber": "A"}
    verse, small, text, added, more, note, rest, verse2, poetry = para["content"]
    assert verse == {"type": "verse", "marker": "v", "number": "1"}
    assert small == {"type": "char", "marker": "sc", "content": ["In"]}
    assert (text, more, rest, poetry) == (
        " the beginning ",
        " light ",
        "and day.",
        "Poetry,",
    )
    assert isinstance(note, dict)
    assert note["caller"] == "+" and [
        part["marker"] for part in usj.objects(note["content"])
    ] == [
        "fr",
        "fqa",
        "ft",
    ]
    # A style within a part of a note nests in it.
    third_part = note["content"][2]
    assert isinstance(third_part, dict)
    assert third_part["content"] == [
        "a ",
        {"type": "char", "marker": "it", "content": ["note"]},
        ".",
    ]


def test_writing_gives_each_verse_a_line_and_nests_styles_in_notes() -> None:
    assert usj.serialize(usj.parse(BOOK)) == (
        "\\id GEN - Brenton\n\\h Genesis\n\\mt1 GENESIS\n\\c 1\n\\p\n"
        "\\v 1 \\sc In\\sc* the beginning \\add was\\add* light \\f + \\fr 1:1 \\fqa Gr. \\ft a \\+it note\\+it*.\\f*and day.\n"
        "\\v 2 Poetry,\n\\q1 line two\n\\c 2\n\\cp A\n\\p\n\\v 1 Next.\n"
    )


def test_every_source_book_survives_reading_and_writing(
    sources: bible.sources.Sources, read: bible.pipeline.Read
) -> None:
    """Nothing but spacing may differ, and what is written reads back the same."""

    def unspaced(text: str) -> str:
        return "".join(text.split())

    # The corrections to Brenton's transcription are made before it is read.
    for code, doc in read.kjv.items():
        written = usj.serialize(doc)
        assert unspaced(written) == unspaced(sources.kjv[code]), code
        assert usj.parse(written) == doc, code
    for code in ("RUT", "PSA", "SIR", "XXA"):
        doc = usj.parse(sources.brenton[code])
        written = usj.serialize(doc)
        assert unspaced(written) == unspaced(sources.brenton[code]), code
        assert usj.parse(written) == doc, code


@pytest.mark.parametrize(
    "text, refusal",
    [
        ("\\id GEN\n\\zz odd\n", "Unsupported marker"),
        ("\\id GEN\n\\p\n\\add open\n\\p\n", "Unclosed"),
        ("\\id GEN\n\\p words \\f + \\fr 1:1 \\ft note\n\\p\n", "Unclosed"),
        ("\\id GEN\n\\p\n\\ft stray\n", "Note field outside a note"),
        ("\\id GEN\n\\c 1\nstray words\n", "Text outside a paragraph"),
        ("\\id GEN\n\\c 1\n\\v 1 words\n", "Verse outside a paragraph"),
        (
            "\\id GEN\n\\c 1\n\\p\n\\v 1 words\n\\cp 11\n",
            "not at the head of a chapter",
        ),
        ("\\id GEN\n\\c 1\n\\cp 11\n\\cp 12\n", "not at the head of a chapter"),
    ],
)
def test_malformed_usfm_is_refused(text: str, refusal: str) -> None:
    with pytest.raises(CheckFailed, match=refusal):
        usj.parse(text)


def test_usj_agrees_with_the_reference_parser(
    sources: bible.sources.Sources, tmp_path: Path
) -> None:
    """usfmtc is the USFM committee's own reader, pinned in the image.

    Read against every book of both sources on 2026-10-01, the two agree but
    for this: usfmtc sets a reference (\\xt) in a footnote inside the field
    before it, and this reader after it, as a field of its own.
    """
    import usfmtc

    path = tmp_path / "RUT.usfm"
    path.write_text(sources.brenton["RUT"], encoding="utf-8")
    theirs = usfmtc.readFile(str(path)).outUsj(None)

    def shape(content: Iterable[str | Node]) -> list[Shape]:
        """Types, markers and words, without the spacing each reader keeps."""
        found: list[Shape] = []
        for item in content:
            if isinstance(item, str):
                if item.strip():
                    found.append(" ".join(item.split()))
            else:
                found.append(
                    (
                        item["type"],
                        item.get("marker"),
                        item.get("number", item.get("code", item.get("caller"))),
                        shape(item.get("content", ())),
                    )
                )
        return found

    assert shape(usj.parse(sources.brenton["RUT"])["content"]) == shape(
        theirs["content"]
    )


CONTENT = usj.parse(
    r"the straight \add way\add* of \f + \fr 1:1 \ft a note\f*life \it ends\it*.",
    fragment=True,
)


def test_words_are_read_without_notes_unless_asked() -> None:
    assert usj.text_of(CONTENT) == "the straight way of life ends."
    assert (
        usj.text_of(CONTENT, skip=usj.is_label)
        == "the straight way of a notelife ends."
    )


def test_replacing_words_takes_their_styles_and_keeps_notes_outside() -> None:
    assert (
        usj.serialize(usj.replaced(CONTENT, 4, 16, ["narrow path"]))
        == r"the narrow path of \f + \fr 1:1 \ft a note\f*life \it ends\it*."
    )


def test_an_insertion_stands_before_a_style_and_among_notes_in_order() -> None:
    note = usj.note("f", usj.char("ft", "x"))
    assert usj.serialize(usj.inserted(CONTENT, 13, [note])).startswith(
        r"the straight \f - \ft x\f*\add way"
    )
    assert r"note\f*\f - \ft x\f*life" in usj.serialize(
        usj.inserted(CONTENT, 20, [note])
    )
    assert r"of \f - \ft x\f*\f + " in usj.serialize(
        usj.inserted(CONTENT, 20, [note], after_notes=False)
    )
    with pytest.raises(CheckFailed, match="inside a .add span"):
        usj.inserted(CONTENT, 14, [note])


def test_rewriting_words_in_place_keeps_their_styles() -> None:
    assert (
        usj.serialize(usj.substituted(CONTENT, [(4, 16, "narrow"), (25, 29, "begins")]))
        == r"the narrow of \f + \fr 1:1 \ft a note\f*life \it begins\it*."
    )
    # A style left without words goes; words within a note are reached on request.
    assert r"\ft a NOTE\f*" in usj.serialize(
        usj.substituted(CONTENT, [(22, 26, "NOTE")], skip=usj.is_label)
    )
    assert usj.serialize(
        usj.substituted(CONTENT, [(0, 3, "A")], unwrap=[(13, 16)])
    ).startswith("A straight way of")


def test_changing_content_leaves_the_original_as_it_was() -> None:
    before = usj.serialize(CONTENT)
    usj.replaced(CONTENT, 0, 3, ["A"])
    usj.substituted(CONTENT, [(0, 3, "A")])
    usj.inserted(CONTENT, 0, ["x"])
    assert usj.serialize(CONTENT) == before


def test_a_verse_runs_across_its_paragraphs_with_its_notes_placed() -> None:
    doc = usj.parse(BOOK)
    verses = scripture.verses(doc)
    assert list(verses) == ["1:1", "1:2", "2:1"]
    first = verses["1:1"]
    assert first.text == "In the beginning was light and day."
    assert [(offset, note["caller"]) for offset, note in first.notes] == [(27, "+")]
    assert verses["1:2"].text == "Poetry,\nline two" and verses["1:2"].lines == (8,)


def test_a_paragraph_that_holds_nothing_of_a_verse_is_no_part_of_it() -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\q1\n\\v 1 One,\n\\b\n\\q1 two.\n"
        "\\p\n\\v 2\n\\p\n\\v 3 Three.\n"
    )
    verses = scripture.verses(doc)
    # Neither a blank line nor the paragraph the next verse opens.
    assert verses["1:1"].text == "One,\ntwo."
    assert [part[0] for part in verses["1:1"].parts] == [2, 4]
    # A verse without words still stands where its number does.
    assert verses["1:2"].parts == ((5, 1, 1, 0),) and verses["1:2"].text == ""


def test_changes_to_a_verse_are_made_together_by_their_offsets() -> None:
    doc = usj.parse(BOOK)
    verse = scripture.verses(doc)["1:1"]
    note = usj.note("f", usj.char("ft", "new"))
    changed = scripture.edited(
        doc,
        [(verse, 3, 16, ["the start"]), (verse, 27, 27, [note]), (verse, 0, 0, ["["])],
    )
    assert usj.serialize(changed).splitlines()[5] == (
        "\\v 1 [\\sc In\\sc* the start \\add was\\add* light "
        "\\f + \\fr 1:1 \\fqa Gr. \\ft a \\+it note\\+it*.\\f*\\f - \\ft new\\f*and day."
    )
    with pytest.raises(CheckFailed, match="Overlapping"):
        scripture.edited(doc, [(verse, 0, 5, ["a"]), (verse, 3, 8, ["b"])])
