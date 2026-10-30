"""USJ: reading and writing USFM, and changing content by its words."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pytest

import bible.export
import bible.pipeline
import bible.sources
from bible import assembly, scripture, usj
from bible.checks import CheckFailed
from bible.usj import Node

type Shape = str | tuple[str, str | None, str | None, list[Shape]]

BOOK = (
    "\\id GEN - Brenton\n\\h Genesis\n\\mt1 GENESIS\n\\c 1  \n\\p\n"
    "\\v 1 \\sc In\\sc* the beginning \\add was\\add* light \\f + \\fr 1:1 \\fqa Gr. \\ft a \\+it note\\+it*.\\f*and day.  \n"
    "\\v 2 \\vp 1:2\\vp* Poetry,\n\\q1 line two\n\\c 2\n\\cp A\n\\p\n\\v 1 Next.\n"
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
    # The number a verse prints is the verse's own, as usfmtc reads it.
    assert verse2 == {"type": "verse", "marker": "v", "number": "2", "pubnumber": "1:2"}
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
        "\\id GEN - Brenton\n\\usfm 3.1\n\\h Genesis\n\\mt1 GENESIS\n\\c 1\n\\p\n"
        "\\v 1 \\sc In\\sc* the beginning \\add was\\add* light \\f + \\fr 1:1 \\fqa Gr. \\ft a \\+it note\\+it*.\\f*and day.\n"
        "\\v 2 \\vp 1:2\\vp* Poetry,\n\\q1 line two\n\\c 2\n\\cp A\n\\p\n\\v 1 Next.\n"
    )


def test_every_source_book_survives_reading_and_writing(
    sources: bible.sources.Sources, read: bible.pipeline.Read
) -> None:
    """Nothing but spacing may differ, and what is written reads back the same."""

    def unspaced(text: str) -> str:
        return "".join(text.split())

    def versioned(source: str) -> str:
        """A source as written: its version declared after its book."""
        book, rest = source.split("\n", 1)
        return f"{book}\n\\usfm {usj.VERSION}\n{rest}"

    # The corrections to Brenton's transcription are made before it is read.
    for code, doc in read.kjv.items():
        written = usj.serialize(doc)
        source = assembly.colophon(usj.parse(sources.kjv[code]))
        assert unspaced(written) == unspaced(usj.serialize(source)), code
        assert usj.parse(written) == doc, code
    for code in ("RUT", "PSA", "SIR", "XXA"):
        doc = usj.parse(sources.brenton[code])
        written = usj.serialize(doc)
        assert unspaced(written) == unspaced(versioned(sources.brenton[code])), code
        assert usj.parse(written) == doc, code


@pytest.mark.parametrize(
    "text, refusal",
    [
        ("\\id GEN\n\\zz odd\n", r"Unsupported marker \\zz: "),
        ("\\id GEN\n\\p words \\f + \\ft a \\it b\\f*\n", r"Unclosed \\it: "),
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
        ("\\id GEN\n\\usfm 3.0\n", "Unsupported USFM version"),
        ("\\id GEN\n\\h Genesis\n\\usfm 3.1\n", "USFM version not after the book"),
        ("\\id GEN\n\\usfm 3.1\n\\usfm 3.1\n", "USFM version declared twice"),
    ],
)
def test_malformed_usfm_is_refused(text: str, refusal: str) -> None:
    with pytest.raises(CheckFailed, match=refusal):
        usj.parse(text)


def test_the_version_is_declared_once_after_the_opening_book() -> None:
    books = usj.parse("\\id GEN\n\\id EXO\n")
    written = usj.serialize(books)
    assert written == "\\id GEN\n\\usfm 3.1\n\\id EXO\n"
    assert usj.parse(written) == books


def test_a_document_of_another_version_is_not_written() -> None:
    doc: usj.Document = {**usj.parse("\\id GEN\n"), "version": "3.0"}
    with pytest.raises(CheckFailed, match="Unsupported USJ version"):
        usj.serialize(doc)


def test_a_style_in_a_part_of_a_note_nests_in_it_without_its_plus() -> None:
    """As USFM 3.1 reads it, and as usfmtc writes it for PTXprint."""
    nested = r"\f + \fr 1:1 \ft a \+it note\+it*.\f*"
    assert usj.parse(nested.replace("+it", "it"), fragment=True) == usj.parse(
        nested, fragment=True
    )


def test_nothing_but_a_part_of_a_note_is_written_after_one() -> None:
    # It would be read back as part of the field before it.
    loose = usj.note("f", usj.char("fr", "1:1 "), usj.char("it", "note"))
    with pytest.raises(CheckFailed, match="Content after a part of a note"):
        usj.serialize([loose])


def test_what_ptxprint_writes_reads_back_the_same(tmp_path: Path) -> None:
    import usfmtc
    from ptxprint.usxutils import PTXEmitter

    doc = usj.parse(BOOK)
    path = tmp_path / "GEN.usfm"
    path.write_text(usj.serialize(doc), encoding="utf-8")
    upstream = usfmtc.readFile(str(path))
    for emitter in (None, PTXEmitter):
        options = {"emitter": emitter} if emitter else {}
        processed = upstream.outUsfm(None, **options)
        assert "\\ft a \\it note\\it*." in processed
        assert usj.parse(processed) == doc


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
        """Types, markers, and words, without the spacing each reader keeps."""
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


@pytest.mark.parametrize("marker", ["qr", "qa"])
def test_source_instruction_markers_agree_with_reference_parser(
    marker: str, tmp_path: Path
) -> None:
    import usfmtc

    text = f"\\id LAM\n\\c 1\n\\{marker}\n\\v 1 \\sc Aleph.\\sc*\n"
    path = tmp_path / "LAM.usfm"
    path.write_text(text, encoding="utf-8")
    ours = usj.parse(text)
    theirs = usfmtc.readFile(str(path)).outUsj(None)
    assert ours["content"][2]["marker"] == theirs["content"][2]["marker"] == marker
    assert usj.parse(usj.serialize(ours)) == ours


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


def test_a_note_can_split_nested_styles_without_changing_their_words() -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n" r"\v 1 \sc before \+it these words\+it*\sc*"
    )
    before = usj.serialize(doc)
    note = usj.note("f", usj.char("ft", "a note"))
    verse = scripture.verses(doc)["1:1"]
    offset = verse.text.index("words")
    with pytest.raises(CheckFailed, match="inside a .sc span"):
        scripture.edited(doc, [(verse, offset, offset, [note])])
    changed = scripture.edited(
        doc, [(verse, offset, offset, [note])], split_styles=True
    )
    assert usj.serialize(changed).splitlines()[-1] == (
        r"\v 1 \sc before \+it these \+it*\sc*\f - \ft a note\f*"
        r"\sc \+it words\+it*\sc*"
    )
    assert scripture.verses(changed)["1:1"].notes == ((offset, note),)
    assert scripture.verses(changed)["1:1"].text == verse.text
    assert usj.serialize(doc) == before


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
    assert usj.serialize(changed).splitlines()[6] == (
        "\\v 1 [\\sc In\\sc* the start \\add was\\add* light "
        "\\f + \\fr 1:1 \\fqa Gr. \\ft a \\+it note\\+it*.\\f*\\f - \\ft new\\f*and day."
    )
    with pytest.raises(CheckFailed, match="Overlapping"):
        scripture.edited(doc, [(verse, 0, 5, ["a"]), (verse, 3, 8, ["b"])])


def test_serializing_preserves_a_styles_leading_space() -> None:
    content: usj.Content = [usj.char("sc", " sabachthani"), "?"]
    assert usj.serialize(content) == "\\sc  sabachthani\\sc*?"
    assert usj.parse(usj.serialize(content), fragment=True) == content


@pytest.mark.parametrize("old", ["lama", "lamma"])
def test_a_replacement_retaining_a_style_does_not_split_it(old: str) -> None:
    content: usj.Content = [usj.char("sc", f"Eli, Eli, {old} sabachthani"), "?"]
    note = usj.note("f", usj.char("ft", old))
    changed = usj.replaced(content, 10, 10 + len(old), [usj.char("sc", "lima"), note])
    assert changed == [
        usj.char("sc", "Eli, Eli, "),
        usj.char("sc", "lima", note, " sabachthani"),
        "?",
    ]
    assert usj.parse(usj.serialize(changed), fragment=True) == changed
    assert content == [usj.char("sc", f"Eli, Eli, {old} sabachthani"), "?"]


def test_a_revision_keeps_a_notes_word_separator_before_its_next_field() -> None:
    content: usj.Content = [
        usj.char("ft", "The word "),
        usj.char("fqa", "choenix"),
        usj.char("ft", ", signifieth"),
    ]
    changed = usj.substituted(content, [(16, 17, "")], skip=usj.is_label)
    assert changed == [
        usj.char("ft", "The word "),
        usj.char("fqa", "choenix "),
        usj.char("ft", "signifieth"),
    ]
    assert usj.parse(usj.serialize(changed), fragment=True) == changed
    assert content[-1] == usj.char("ft", ", signifieth")


def test_a_space_never_doubles_across_a_character_styles_close() -> None:
    # eBible's Brenton has "\\add for \\add* teeth" 44 times: the space inside
    # the style and the one after it would print as two in a ragged line.
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 Swords \\add for \\add* teeth, \\add as\\add* knives.\n"
    )
    assert usj.serialize(doc).splitlines()[-1] == (
        "\\v 1 Swords \\add for\\add* teeth, \\add as\\add* knives."
    )
    # A note's fields keep the space that parts one from the next.
    note = usj.parse("\\f + \\fr 1:1 \\fqa Gr. \\ft word.\\f*", fragment=True)
    assert usj.serialize(note) == "\\f + \\fr 1:1 \\fqa Gr. \\ft word.\\f*"
    # Nor does a style that closes the paragraph keep a space at its end, as
    # when a line of verse divides one.
    half = usj.trimmed(["for the ancient ", usj.char("add", "heavens? ")])
    assert half == ["for the ancient ", usj.char("add", "heavens?")]


def test_choenix_spacing_and_italics_survive_preparation_and_export(
    edition: bible.pipeline.Edition, exported: dict[str, str], tmp_path: Path
) -> None:
    import usfmtc

    note = next(
        n
        for n in usj.notes_of(edition.documents["REV"]["content"])
        if n.get("x-key") == "REV 6:6 A measure"
    )
    assert "choenix signifieth" in usj.text_of(note["content"])
    assert any(
        usj.is_type(n, "char", "it") and usj.text_of(n["content"]) == "choenix"
        for n in usj.walk(note["content"])
    )
    text = exported["REV"]
    assert "choenix\\+it* signifieth" in text
    passage = usj.parse("\\id REV\n\\c 6\n\\p\n\\v 6 A measure of wheat.\n")
    block = passage["content"][-1]
    block["content"].append(note)
    text = usj.serialize(bible.export.document("REV", passage, edition))
    doc = usj.parse(text)
    path = tmp_path / "REV.usfm"
    path.write_text(text, encoding="utf-8")
    for parsed in [doc, usfmtc.readFile(str(path)).outUsj(None)]:
        found = next(
            n
            for n in usj.notes_of(parsed["content"])
            if "choenix" in usj.text_of(n["content"])
        )
        assert "choenix signifieth" in usj.text_of(found["content"])
        assert any(
            "choenix" in usj.text_of(n["content"])
            for n in usj.walk(found["content"])
            if n.get("marker") in ("fqa", "it")
        )


@pytest.mark.parametrize("book,reference", [("MAT", "27:46"), ("MRK", "15:34")])
def test_transliteration_is_roman_and_keeps_its_spacing(
    book: str, reference: str, edition: bible.pipeline.Edition, exported: dict[str, str]
) -> None:
    for doc in [edition.documents[book], usj.parse(exported[book])]:
        verse = scripture.verses(doc)[reference]
        spans = [
            n
            for block, lo, hi, _ in verse.parts
            for n in usj.walk(doc["content"][block]["content"][lo:hi])
            if usj.is_type(n, "char", "sc")
        ]
        assert not spans
        assert "lima sabachthani" in verse.text
        note = next(n for _, n in verse.notes if "TR" in usj.text_of(n["content"]))
        assert (
            usj.text_of(
                next(
                    n["content"]
                    for n in usj.objects(note["content"])
                    if n["marker"] == "fq"
                )
            )
            == "lima: "
        )
        assert (
            usj.text_of(
                next(
                    n["content"]
                    for n in usj.objects(note["content"])
                    if n["marker"] == "fqa"
                )
            )
            == "lama"
        )


def test_fk_is_a_note_field_not_scripture() -> None:
    doc = usj.parse(
        "\\id LUK\n\\c 23\n\\p\n\\v 42 in regnum\\f + \\fk Glossa\\ft commentary\\f* tuum."
    )
    assert scripture.verses(doc)["23:42"].text == "in regnum tuum."
