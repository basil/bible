"""Front and back matter: the translations' own pages as the edition prints
them, and the introductions that go to the books."""

import pytest
from conftest import changed

from bible import annotate, matter, terminology, usj
from bible.checks import CheckFailed
from bible.policy import source_id


def lines(edition, code):
    return usj.serialize(edition.documents[code]).splitlines()


def prepared(code, policy, read, sources, ctx):
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


def test_the_introduction_keeps_its_general_paragraphs_and_sends_the_rest(edition):
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


def test_a_books_introduction_is_a_footnote_on_its_first_verse(edition):
    tobit = next(line for line in lines(edition, "TOB") if line.startswith("\\v 1 "))
    assert tobit.startswith(
        "\\v 1 \\ef - \\ft The book of Tobit is one of the most perfect"
    )
    # Several paragraphs make one note, and its italics nest in it.
    first = next(line for line in lines(edition, "1MA") if line.startswith("\\v 1 "))
    assert (
        "first two as canonical. The \\+it First\\+it* Book of the Maccabees" in first
    )
    # A section's introduction stands at the section's first verse, under its heading.
    daniel = lines(edition, "DAG")
    song = daniel.index("\\s1 THE SONG OF THE THREE CHILDREN")
    assert daniel[song + 2].startswith(
        "\\v 25 \\ef - \\ft The Song of the Three Children contains"
    )


def test_every_paragraph_of_the_introduction_is_placed_once(policy, read, sources, ctx):
    def unplaced(data):
        data["books"]["TOB"] = []

    with pytest.raises(CheckFailed, match="paragraphs not placed|with no paragraphs"):
        prepared("OTH", changed(policy, "introductions", unplaced), read, sources, ctx)

    def stale(data):
        data["glosses"]["The book of Tobit"] = [
            {"after": "Hebrew idols", "insert": " [sic]", "why": "no such words"}
        ]

    with pytest.raises(CheckFailed, match="Gloss does not apply"):
        prepared("OTH", changed(policy, "introductions", stale), read, sources, ctx)


def test_the_list_of_abbreviations_is_completed_from_the_registry(edition, policy):
    table = next(b for b in edition.documents["XXD"]["content"] if b["type"] == "table")
    rows = [
        tuple(usj.text_of(cell["content"]).strip() for cell in row["content"])
        for row in table["content"]
    ]
    labels = [label for label, _ in rows]
    # Brenton's rows for what the edition prints in full are dropped...
    assert not set(policy.abbreviations["expanded"]["removed"]) & set(labels)
    # ...his meanings are lowercased where they aren't proper nouns...
    assert ("Lit.", "for literally.") in rows and ("—", "for sign of omission.") in rows
    # ...and the edition's rows follow his, in the registry's forms.
    assert rows[-3:] == [
        ("p., pp.", "for page, pages."),
        ("St.", "for saint."),
        ("Vat.", "for Vatican Text."),
    ]
    assert ("AD", "for anno Domini.") in rows
    latin = usj.serialize(edition.documents["XXD"])
    assert "\\tc2 for \\it anno Domini\\it*." in latin


def test_matter_cites_and_names_as_the_edition_does(edition):
    preface = usj.serialize(edition.documents["XXB"])
    # Brenton's "Gen. xlvii. 31, compared with Hebrews xi. 21".
    assert "afforded by Genesis 47:31, compared with Hebrews 11:21" in preface
    # A declared change keeps the style of the words it replaces.
    assert "\\im \\it Authorized Version\\it* bowed himself" in preface
    appendix = lines(edition, "BAK")
    assert "\\is2 3 KINGDOMS" in appendix and "\\is2 2 CHRONICLES" in appendix
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


def test_a_declared_change_must_be_the_units_words_once(policy, read, sources, ctx):
    def twice(data):
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


def test_what_was_read_is_carried_through_a_change_of_words():
    reading = matter.Reading("see Gen. 1. 1 and the Sept. here", (), ())
    term = terminology.Term("septuagint", "Sept.", 22, 27)
    moved = matter.rebased(
        matter.Reading(reading.text, (), (term,)), "see Genesis 1:1 and the Sept. here"
    )
    assert moved.text[moved.terms[0].start : moved.terms[0].end] == "Sept."
