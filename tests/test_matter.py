"""Front and back matter: the translations' own pages as the edition prints
them, and the introductions that go to the books."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import changed

import bible.annotate
import bible.pipeline
import bible.policy
import bible.sources
from bible import annotate, matter, notes, terminology, usj
from bible.checks import CheckFailed
from bible.policy import source_id
from bible.usj import Content, Document


def lines(edition: bible.pipeline.Edition, code: str) -> list[str]:
    return usj.serialize(edition.documents[code]).splitlines()


def prepared(
    code: str,
    policy: bible.policy.Policy,
    read: bible.pipeline.Read,
    sources: bible.sources.Sources,
    ctx: bible.annotate.Context,
) -> tuple[Document, dict[str, list[Content]]]:
    """One unit prepared again under a changed policy."""
    from bible import assembly

    entry = next(e for e in policy.entries if e["id"] == code)
    family = read.brenton if entry["source"] == "brenton" else read.kjv
    doc = family[source_id(entry)]
    changed_ctx = annotate.Context(
        policy, ctx.inventory, ctx.books, terminology.registry(policy), ctx.prose
    )
    return matter.unit(
        entry,
        doc,
        doc,
        assembly.source_text(entry, sources),
        changed_ctx,
        annotate.Report(),
    )


def test_the_introduction_keeps_its_general_paragraphs_and_sends_the_rest(
    edition: bible.pipeline.Edition,
) -> None:
    front = lines(edition, "OTH")
    assert [line[:28] for line in front[6:]] == [
        "\\ip The Alexandrian Jews pos",
        "\\ip During the Reformation p",
        "\\ip In more recent times it ",
        "\\ip The second book of Esdra",
    ]
    # Its headings, which the books' titles replace, are dropped.
    assert not [line for line in front if line.startswith("\\is")]
    # A gloss is bracketed, and a book is called by the edition's name for it.
    assert (
        "save 1 and 2 Esdras [of the English Apocrypha] and the Prayer of Manasses"
        in front[7]
    )


def test_a_books_introduction_is_a_footnote_on_its_first_verse(
    edition: bible.pipeline.Edition,
) -> None:
    tobit = next(line for line in lines(edition, "TOB") if line.startswith("\\v 1 "))
    assert tobit.startswith(
        "\\v 1 \\ef - \\ft The book of Tobit is one of the most perfect"
    )
    # Several paragraphs make one note; the book name is roman.
    first = next(line for line in lines(edition, "1MA") if line.startswith("\\v 1 "))
    assert "first two as canonical. The First Book of the Maccabees" in first
    # A section's introduction stands at the section's first verse, under its heading.
    daniel = lines(edition, "DAG")
    song = daniel.index("\\s1 The Song of the Three Children")
    assert daniel[song + 2].startswith(
        "\\v 25 \\ef - \\ft The Song of the Three Children contains"
    )


def test_front_matter_notes_drop_the_origin_that_names_no_verse() -> None:
    # eBible gives the notes of its front matter, which has no verses, the
    # origin "1:0": they print under their callers alone. A real origin stays.
    doc = usj.parse(
        "\\id XXB\n\\ip Words\\f + \\fr 1:0 \\ft A title\\f* and"
        "\\f + \\fr 3:12 \\ft Cited\\f* more.\n"
    )
    assert usj.serialize(matter.without_empty_origins(doc)) == (
        "\\id XXB\n\\ip Words\\f + \\ft A title\\f* and"
        "\\f + \\fr 3:12 \\ft Cited\\f* more.\n"
    )


@pytest.mark.parametrize("code", ["1ES", "JDT", "SIR", "DAG"])
def test_prose_footnotes_quote_in_italic_without_marks(
    edition: bible.pipeline.Edition, code: str
) -> None:
    footnotes = usj.notes_of(edition.documents[code]["content"])
    assert footnotes
    for note in footnotes:
        text = usj.text_of(note["content"])
        assert notes.ENGLISH_QUOTE.search(text) is None
        assert not any(mark in text for mark in '‘“”"')
        # Note fields contain character styles, never the reverse.
        for node in usj.walk(note["content"]):
            if usj.is_type(node, "char", "it"):
                assert not any(
                    usj.is_type(child, "char", "ft")
                    for child in usj.walk(node["content"])
                )


def test_brenton_introduction_preserves_emphasis_and_nested_quotation(
    edition: bible.pipeline.Edition,
) -> None:
    content = next(
        n["content"]
        for n in usj.notes_of(edition.documents["XXB"]["content"])
        if "Evil communications" in usj.text_of(n["content"])
    )
    italic = [
        usj.text_of(n["content"])
        for n in usj.walk(content)
        if usj.is_type(n, "char", "it")
    ]
    assert "There" in italic and "is" in italic
    assert (
        "“As certain also of your own poets have said, ‘For we are also his offspring.’”"
        in usj.text_of(content)
    )


def test_every_paragraph_of_the_introduction_is_placed_once(
    policy: bible.policy.Policy,
    read: bible.pipeline.Read,
    sources: bible.sources.Sources,
    ctx: bible.annotate.Context,
) -> None:
    def unplaced(data: dict[str, Any]) -> None:
        data["books"]["TOB"] = []

    with pytest.raises(CheckFailed, match="paragraphs not placed|with no paragraphs"):
        prepared("OTH", changed(policy, "introductions", unplaced), read, sources, ctx)

    def stale(data: dict[str, Any]) -> None:
        data["glosses"]["The book of Tobit"] = [
            {"after": "Hebrew idols", "insert": " [sic]", "why": "no such words"}
        ]

    with pytest.raises(CheckFailed, match="Gloss does not apply"):
        prepared("OTH", changed(policy, "introductions", stale), read, sources, ctx)

    # A gloss that names no words of the source, as by a misspelt field.
    def placeless(data: dict[str, Any]) -> None:
        data["glosses"]["The book of Tobit"] = [{"insert": " [sic]", "why": "x"}]

    with pytest.raises(CheckFailed, match="Gloss does not apply"):
        prepared("OTH", changed(policy, "introductions", placeless), read, sources, ctx)


def test_the_list_of_abbreviations_is_completed_from_the_registry(
    edition: bible.pipeline.Edition, policy: bible.policy.Policy
) -> None:
    table = next(b for b in edition.documents["XXD"]["content"] if b["type"] == "table")
    rows = [
        tuple(
            usj.text_of(cell["content"]).strip() for cell in usj.objects(row["content"])
        )
        for row in usj.objects(table["content"])
    ]
    labels = [label for label, _ in rows]
    # Brenton's rows for what the edition prints in full are dropped...
    assert not set(policy.abbreviations["expanded"]["removed"]) & set(labels)
    # ...his meanings are lowercased where they aren't proper nouns...
    assert ("Lit.", "for literally") in rows
    assert not {"+", "—", "adds", "omits"} & set(labels)
    # ...and the edition's rows follow his, in the registry's forms.
    assert rows[-3:] == [
        ("p., pp.", "for page, pages"),
        ("St.", "for saint"),
        ("Vat.", "for Codex Vaticanus"),
    ]
    assert ("AD", "for anno Domini, in the year of our Lord") in rows
    assert all(not meaning.endswith(".") for _, meaning in rows)
    latin = usj.serialize(edition.documents["XXD"])
    assert "\\tc2 for \\it anno Domini\\it*, in the year of our Lord\n" in latin
    assert "\\tc2 for \\it quasi dicat\\it*, as if to say\n" in latin


def test_front_and_back_matter_heading_capitalization(
    edition: bible.pipeline.Edition,
) -> None:
    expected = {
        "XXD": ["\\mt1 Abbreviations and Signs Used in the Notes"],
        "XXB": ["\\mt1 Preface (1844)"],
        "XXE": ["\\mt1 Introduction (1870)"],
        "OTH": ["\\mt1 The Books of the Apocrypha"],
        "TDX": [
            "\\mt2 To the Most High and Mighty Prince",
            "\\mt1 James,",
            "\\mt2 by the Grace of God",
            "\\mt2 King of Great Britain, France, and Ireland,",
            "\\mt2 Defender of the Faith, etc.",
            "\\mt2 The Translators of the Bible wish Grace, Mercy, and Peace, through Jesus Christ our Lord.",
        ],
        "NDX": ["\\mt1 The Translators to the Reader"],
        "BAK": ["\\mt1 Notes and Supplied Passages"],
        "CNC": ["\\mt1 Editor’s Introduction"],
        "XXF": ["\\mt1 The Old Testament", "\\mt2 Brenton’s Septuagint"],
        "XXG": [
            "\\mt1 The New Testament",
            "\\mt2 Scrivener’s Cambridge Paragraph Bible",
            "\\mt2 King James Version",
        ],
        "GLO": ["\\mt1 Appendices", "\\mt2 Brenton’s notes and supplied passages"],
    }
    for code, headings in expected.items():
        assert [
            line for line in lines(edition, code) if line.startswith("\\mt")
        ] == headings


@pytest.mark.parametrize("unit", ["XXD", "OTH", "TDX", "BAK"])
@pytest.mark.parametrize("source", ["missing heading", "changed capitalization"])
def test_heading_decisions_reject_changed_or_missing_source(
    unit: str,
    source: str,
    policy: bible.policy.Policy,
    read: bible.pipeline.Read,
    sources: bible.sources.Sources,
    ctx: bible.annotate.Context,
) -> None:
    def stale(data: dict[str, Any]) -> None:
        decision = next(c for c in data["headings"]["changes"] if c["unit"] == unit)
        decision["from"] = (
            decision["to"] if source == "changed capitalization" else "Missing heading"
        )

    refusal = (
        f"Prose change that changes nothing: headings: {unit}"
        if source == "changed capitalization"
        else f"Prose change not met once: {unit}"
    )
    with pytest.raises(CheckFailed, match=refusal):
        prepared(unit, changed(policy, "prose", stale), read, sources, ctx)


def test_matter_cites_and_names_as_the_edition_does(
    edition: bible.pipeline.Edition,
) -> None:
    preface = usj.serialize(edition.documents["XXB"])
    # Brenton's "Gen. xlvii. 31, compared with Hebrews xi. 21".
    assert "afforded by Gen. 47:31, compared with Heb. 11:21" in preface
    # A declared change keeps the style of the words it replaces.
    assert "\\im \\it Authorized Version\\it* bowed himself" in preface
    appendix = lines(edition, "BAK")
    assert "\\is2 3 Kingdoms" in appendix and "\\is2 2 Chronicles" in appendix
    # Titles and headings drop their closing full stops.
    assert not [
        line
        for line in appendix
        if line.startswith(("\\is1", "\\is2")) and line.endswith(".")
    ]
    # Only the stop that closes a heading, not one before a style within it.
    heading = usj.parse("\\id XXB\n\\is1 St. \\it John\\it* I.\n")["content"][1]
    ((printed, _),) = matter.unpunctuated([(heading, {})])
    assert usj.serialize(printed["content"]) == "St. \\it John\\it* I"


def test_a_declared_change_must_be_the_units_words_once(
    policy: bible.policy.Policy,
    read: bible.pipeline.Read,
    sources: bible.sources.Sources,
    ctx: bible.annotate.Context,
) -> None:
    def twice(data: dict[str, Any]) -> None:
        data["expanded"]["changes"].append(
            {
                "unit": "XXB",
                "from": "the Hebrew",
                "to": "the Ebrew",
                "why": "met too often",
            }
        )

    with pytest.raises(CheckFailed, match="Prose change not met once: XXB the Hebrew"):
        prepared("XXB", changed(policy, "prose", twice), read, sources, ctx)


def test_what_was_read_is_carried_through_a_change_of_words() -> None:
    reading = matter.Reading("see Gen. 1. 1 and the Sept. here", (), ())
    term = terminology.Term("septuagint", "Sept.", 22, 27)
    moved = matter.rebased(
        matter.Reading(reading.text, (), (term,)), "see Genesis 1:1 and the Sept. here"
    )
    assert moved.text[moved.terms[0].start : moved.terms[0].end] == "Sept."


def test_a_name_change_that_prints_the_same_words_is_refused(
    policy: bible.policy.Policy,
    ctx: bible.annotate.Context,
) -> None:
    before = ctx.books.names["GEN"]
    other = changed(
        policy,
        "citations",
        lambda d: d["names"].update(
            XXB=[
                {
                    "from": before,
                    "to": "{GEN}",
                    "why": "x",
                }
            ]
        ),
    )
    with pytest.raises(CheckFailed, match="Change of name changes nothing: XXB"):
        matter.renamed([(usj.para("ip", before), {})], "XXB", ctx.books, other)


def test_a_prose_edit_that_changes_nothing_is_refused() -> None:
    doc = usj.parse("\\id XXB\n\\ip Some introduction.\n")
    unit: matter.Unit = [
        (doc["content"][1], {None: matter.Reading("Some introduction.")})
    ]
    with pytest.raises(CheckFailed, match="Prose change changes nothing: XXB"):
        matter.edited(
            unit,
            "XXB",
            [{"from": "introduction", "to": "introduction"}],
            "Prose change",
        )
