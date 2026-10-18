"""Front and back matter: the translations' own pages as the edition prints
them, and the notes of Brenton's Appendix that go to the books."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import pytest
from conftest import changed

import bible.annotate
import bible.pipeline
import bible.policy
import bible.scripture
import bible.sources
from bible import alexandrinus, annotate, matter, notes, terminology, usj
from bible.checks import CheckFailed
from bible.policy import source_id
from bible.usj import Content, Document


def test_prose_additions_preserve_order_styles_and_inputs(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse("\\id XXB\n\\ip Before.\n\\ip After.\n")
    policy = declared.replace(
        prose={
            "restored": {
                "why": "Restore a missing paragraph.",
                "changes": [],
                "additions": [
                    {
                        "unit": "XXB",
                        "after": "Before.",
                        "paragraphs": [
                            usj.para("ib"),
                            usj.para(
                                "ip", "An ", usj.char("it", "important"), " reading."
                            ),
                        ],
                    }
                ],
            }
        }
    )
    before, decisions = copy.deepcopy(doc), bible.policy.thaw(policy.prose)
    result = matter.supplemented("XXB", doc, policy)
    assert usj.serialize(result).splitlines() == [
        "\\id XXB",
        "\\usfm 3.1",
        "\\ip Before.",
        "\\ib",
        "\\ip An \\it important\\it* reading.",
        "\\ip After.",
    ]
    # The inserted objects are independent of the frozen decision, too.
    result["content"][3]["content"].append(" Changed.")
    assert doc == before
    assert bible.policy.thaw(policy.prose) == decisions


def test_prose_additions_after_one_paragraph_keep_their_order(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse("\\id XXB\n\\ip Before.\n\\ip After.\n")
    additions = [
        {"unit": "XXB", "after": "Before.", "paragraphs": [usj.para("ip", text)]}
        for text in ("First.", "Second.")
    ]
    policy = declared.replace(
        prose={
            "restored": {
                "why": "Restore missing prose.",
                "changes": [],
                "additions": additions,
            }
        }
    )
    assert usj.serialize(matter.supplemented("XXB", doc, policy)).splitlines()[2:] == [
        "\\ip Before.",
        "\\ip First.",
        "\\ip Second.",
        "\\ip After.",
    ]


@pytest.mark.parametrize("anchor", ["not present", "ambiguous"])
def test_prose_additions_require_one_exact_paragraph(
    declared: bible.policy.Policy, anchor: str
) -> None:
    policy = declared.replace(
        prose={
            "restored": {
                "why": "Restore missing prose.",
                "changes": [],
                "additions": [
                    {
                        "unit": "XXB",
                        "after": anchor,
                        "paragraphs": [usj.para("ip", "Restored.")],
                    }
                ],
            }
        }
    )
    doc = usj.parse("\\id XXB\n\\ip ambiguous\n\\ip ambiguous\n")
    with pytest.raises(CheckFailed, match="Prose addition not met once: XXB: restored"):
        matter.supplemented("XXB", doc, policy)


@pytest.mark.parametrize(
    "addition, error",
    [
        ({"unit": "GEN"}, "not front or back matter"),
        ({"after": " "}, "empty anchor"),
        ({"after": "Before. "}, "anchor with surrounding space"),
        ({"paragraphs": []}, "empty addition"),
        ({"paragraphs": [usj.para("ip", " ")]}, "blank paragraph"),
        ({"paragraphs": [usj.para("ib", "Words.")]}, "blank line takes no content"),
        (
            {"paragraphs": [{"type": "para", "marker": "ib", "content": None}]},
            "blank line takes no content",
        ),
        ({"paragraphs": [usj.para("p", "Scripture.")]}, "introductory paragraph"),
        (
            {"paragraphs": [usj.para("ip", usj.para("ip", "Nested."))]},
            "character style",
        ),
        (
            {"paragraphs": [usj.para("ip", usj.char("ft", "A note's field."))]},
            "character style",
        ),
        ({"paragraphs": [usj.para("ip", "\\it Raw markup.")]}, "markup in text"),
    ],
)
def test_invalid_prose_additions_are_refused(
    declared: bible.policy.Policy, addition: dict[str, Any], error: str
) -> None:
    with pytest.raises(CheckFailed, match=error):
        declared.replace(
            prose={
                "restored": {
                    "why": "Restore missing prose.",
                    "changes": [],
                    "additions": [
                        {
                            "unit": "XXB",
                            "after": "Before.",
                            "paragraphs": [usj.para("ip", "Restored.")],
                            **addition,
                        }
                    ],
                }
            }
        )


def test_brentons_introduction_includes_the_1851_continuation(
    edition: bible.pipeline.Edition, read: bible.pipeline.Read
) -> None:
    introduction = usj.serialize(edition.documents["XXE"])
    assert "The earliest version of the Old Testament Scriptures" in introduction
    assert introduction.count("The principal translations based on the Septuagint") == 1
    assert "as much among Protestants as among those" in introduction
    assert "Petri and Pauli" in introduction
    assert "\\it intentionally\\it*" in introduction
    assert introduction.index("The Old Latin.") < introduction.index("The Gothic.")
    assert introduction.index("The Gothic.") < introduction.index("Cardinal Caraffa")
    assert introduction.index("Cardinal Caraffa") < introduction.index("Tischendorf")
    assert introduction.rstrip().endswith("have been subjoined to the Roman text.")
    assert "Apocryphal books" not in introduction
    # The input still ends where eBible's transcription ends.
    assert (
        usj.serialize(read.brenton["INT"])
        .rstrip()
        .endswith("formed at once from the Hebrew.")
    )


def lines(edition: bible.pipeline.Edition, code: str) -> list[str]:
    return usj.serialize(edition.documents[code]).splitlines()


def prepared(
    code: str,
    policy: bible.policy.Policy,
    read: bible.pipeline.Read,
    ctx: bible.annotate.Context,
) -> tuple[Document, dict[str, list[Content]]]:
    """One unit prepared again under a changed policy."""
    entry = next(e for e in policy.entries if e["id"] == code)
    family = read.brenton if entry["source"] == "brenton" else read.kjv
    doc = family[source_id(entry)]
    changed_ctx = annotate.Context(policy, ctx.inventory, ctx.books)
    return matter.unit(entry, doc, changed_ctx, annotate.Report())


def test_the_appendix_notes_are_footnotes_at_their_verses(
    edition: bible.pipeline.Edition, policy: bible.policy.Policy
) -> None:
    # The Appendix prints nowhere: its notes stand at their verses, at the
    # foot of the page with a numbered caller, without the labels that named
    # the verses.
    assert "BAK" not in edition.documents
    kingdoms = next(
        line
        for line in lines(edition, "2SA")
        if line.startswith("\\v 18 And the Philistines came")
    )
    # After the margin note on the word, which keeps its other words.
    assert (
        "\\fqa Rephaim\\f*\\ef + \\ft Giants. \\+it Heb.\\+it* רפאים. For" in kingdoms
    )
    assert kingdoms.endswith("Isaiah.\\ef*giants.")
    # The verses it supplies carry their numbers in the note.
    exodus = next(line for line in lines(edition, "EXO") if "Complutensian" in line)
    assert exodus.startswith(
        "\\v 23 \\ef + \\ft The following verses are found neither in the Vatican"
    )
    assert "\\+fv 23\\+fv*And thou shalt make upon the oracle" in exodus
    # A note that only sent the reader to the Appendix gives way to it.
    psalm = usj.serialize(edition.documents["PSA"])
    assert "See Appendix" not in psalm
    verse = bible.scripture.verses(edition.documents["PSA"])["41:5"]
    assert (
        next(
            offset
            for offset, note in verse.notes
            if note.get("x-key") == "PSA 41:5 Appendix"
        )
        == 0
    )
    assert len(policy.appendix["notes"]) == 8
    job = bible.scripture.verses(edition.documents["JOB"])["25:2"]
    note = next(n for _, n in job.notes if n.get("x-key") == "JOB 25:2 Appendix")
    assert usj.text_of(note["content"]).endswith(
        "Probably προοίμιον is a mistake of the transcriber."
    )

    job = bible.scripture.verses(edition.documents["JOB"])["39:13"]
    note = next(n for _, n in job.notes if n.get("x-key") == "JOB 39:13 Appendix")
    text = usj.text_of(note["content"])
    assert "נעלסה" in text and "נעלסּה" not in text
    assert "עלס" in text and "עלם" not in text


def test_an_appendix_note_must_be_placed_where_its_decision_says(
    policy: bible.policy.Policy,
    read: bible.pipeline.Read,
    sources: bible.sources.Sources,
    ctx: bible.annotate.Context,
) -> None:
    entry = policy.unprinted[0]
    appendix = alexandrinus.appendix_notes(read.brenton["BAK"])

    def prepare(change: Callable[[dict[str, Any]], object]) -> None:
        changed_policy = changed(policy, "appendix", change)
        changed_ctx = annotate.Context(changed_policy, ctx.inventory, ctx.books)
        matter.unit(entry, appendix, changed_ctx, annotate.Report())

    def relabelled(data: dict[str, Any]) -> None:
        data["notes"]["JOB 25:2"]["label"] = "Job 25. 3.—"

    with pytest.raises(CheckFailed, match="Appendix label not found once"):
        prepare(relabelled)

    def unplaced(data: dict[str, Any]) -> None:
        del data["notes"]["EZK 16:44"]

    with pytest.raises(CheckFailed, match="Paragraphs not placed"):
        prepare(unplaced)
    with pytest.raises(CheckFailed, match="Invalid Appendix note: JOB 25:2"):
        changed(policy, "appendix", lambda d: d["notes"]["JOB 25:2"].update(at="start"))


def test_an_appendix_note_stands_at_words_found_once(
    edition: bible.pipeline.Edition,
) -> None:
    verse = bible.scripture.verses(edition.documents["JOB"])["25:2"]
    with pytest.raises(CheckFailed, match="Note lemma not anchored once: JOB 25:2"):
        alexandrinus.anchor(verse, "fear and beginning", "JOB 25:2")


def test_front_matter_notes_are_numbered_without_origins_that_name_no_verse() -> None:
    # eBible gives the notes of its front matter, which has no verses, the
    # origin "1:0": they print under their callers alone. A real origin stays.
    doc = usj.parse(
        "\\id XXB\n\\ip Words\\f + \\fr 1:0 \\ft A title\\f* and"
        "\\f * \\fr 3:12 \\ft Cited\\f* more.\n"
    )
    assert usj.serialize(matter.numbered_notes(doc)) == (
        "\\id XXB\n\\usfm 3.1\n\\ip Words\\f + \\ft A title\\f* and"
        "\\f + \\fr 3:12 \\ft Cited\\f* more.\n"
    )


@pytest.mark.parametrize("code", ["2SA", "EXO", "DAG"])
def test_footnotes_quote_in_italic_without_marks(
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


def test_the_list_of_abbreviations_is_completed_from_the_registry(
    edition: bible.pipeline.Edition, policy: bible.policy.Policy
) -> None:
    [table] = [b for b in edition.documents["XXD"]["content"] if b["type"] == "table"]
    rows = [
        tuple(
            usj.text_of(cell["content"]).strip() for cell in usj.objects(row["content"])
        )
        for row in usj.objects(table["content"])
    ]
    latin = usj.serialize(edition.documents["XXD"])
    labels = [label for label, _ in rows]
    # Brenton's rows for what the edition prints in full are dropped...
    assert not set(policy.abbreviations["expanded"]["removed"]) & set(labels)
    # ...his meanings are lowercased where they aren't proper nouns...
    assert ("lit.", "for literally") in rows
    assert not {"—", "adds", "omits"} & set(labels)
    # ...the edition's rows join his, in the registry's forms...
    assert {
        ("p., pp.", "for page, pages"),
        ("St.", "for saint"),
        ("Vat.", "for Codex Vaticanus"),
        ("KJV", "for King James Version"),
        ("OLEB", "for Orthodox Liturgical English Bible, this edition"),
        (
            "RP26",
            "for Robinson and Pierpont, The Greek New Testament According to the Byzantine Text (2026)",
        ),
        ("TR", "for Textus Receptus, the Received Text"),
    } <= set(rows)
    # ...and all are in alphabetical order, by their letters alone. Turpie's
    # signs aren't abbreviations: the editor's introduction explains them.
    assert labels == sorted(labels, key=terminology.alphabetical)
    assert labels[:3] == ["AD", "Alex.", "BC"]
    assert not {"+", "≠"} & set(labels)
    assert ("AD", "for anno Domini, in the year of our Lord") in rows
    assert all(not meaning.endswith(".") for _, meaning in rows)
    assert "\\tc2 for \\it anno Domini\\it*, in the year of our Lord\n" in latin
    assert "\\tc2 for \\it quasi dicat\\it*, as if to say\n" in latin
    # A title in a meaning is italic as the Latin is.
    assert "\\tc2 for \\it Textus Receptus\\it*, the Received Text\n" in latin
    assert (
        "\\tc2 for Robinson and Pierpont, \\it The Greek New Testament According"
        " to the Byzantine Text\\it* (2026)\n"
    ) in latin


def test_front_and_back_matter_heading_capitalization(
    edition: bible.pipeline.Edition,
) -> None:
    expected = {
        "XXD": ["\\mt1 Abbreviations Used in the Notes"],
        "XXB": ["\\mt1 Preface"],
        "XXE": ["\\mt1 Introduction"],
        "TDX": [
            "\\mt2 To the Most High and Mighty Prince",
            "\\mt1 James,",
            "\\mt2 by the Grace of God",
            "\\mt2 King of Great Britain, France, and Ireland,",
            "\\mt2 Defender of the Faith, etc.",
            "\\mt2 The Translators of the Bible wish Grace, Mercy, and Peace, through Jesus Christ our Lord.",
        ],
        "NDX": ["\\mt1 The Translators to the Reader"],
        "CNC": ["\\mt1 Editor’s Introduction"],
        "XXF": ["\\mt1 The Old Testament", "\\mt2 Brenton’s Septuagint"],
        "XXG": [
            "\\mt1 The New Testament",
            "\\mt2 King James Version",
            "\\mt2 Conformed to the Byzantine Text",
        ],
        "GLO": ["\\mt1 Appendix", "\\mt2 The Readings of the Byzantine Text"],
        "XXC": ["\\mt1 Readings of the Byzantine Text"],
    }
    for code, headings in expected.items():
        assert [
            line for line in lines(edition, code) if line.startswith("\\mt")
        ] == headings


@pytest.mark.parametrize("unit", ["XXD", "TDX"])
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
        prepared(unit, changed(policy, "prose", stale), read, ctx)


def test_matter_cites_and_names_as_the_edition_does(
    edition: bible.pipeline.Edition,
) -> None:
    preface = usj.serialize(edition.documents["XXB"])
    # Brenton's "Gen. xlvii. 31, compared with Hebrews xi. 21".
    assert "afforded by Gen. 47:31, compared with Heb. 11:21" in preface
    # A declared change keeps the style of the words it replaces.
    assert "\\im \\it Authorized Version\\it* bowed himself" in preface
    # Titles and headings drop their closing full stops.
    assert not [
        line
        for line in lines(edition, "XXE")
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
        prepared("XXB", changed(policy, "prose", twice), read, ctx)


@pytest.mark.parametrize(
    "prose",
    [
        "Words end here.\\f + \\ft Lit. a note.\\f*",
        "Words run on\\f + \\ft Lit. a note.\\f*",
        "Words run on\\f + \\ft A note.\\f*\\f + \\ft Lit. a note.\\f*",
    ],
)
def test_a_footnote_within_prose_is_read_as_a_note_of_its_own(
    policy: bible.policy.Policy, prose: str
) -> None:
    registry = terminology.registry(policy)

    def paragraph(words: str) -> usj.Node:
        doc = usj.parse(f"\\id XXB\n\\ip {words} and more.")
        return next(b for b in doc["content"] if b.get("type") == "para")

    source = paragraph(prose)
    reading = matter.Reading(
        usj.unlabelled(source["content"]),
        (),
        terminology.found(source["content"], registry, note=False),
    )
    # "Lit." opens the note, whatever the prose before it, so it stays as
    # the source has it, and still does once the prose has changed.
    for block in (source, paragraph("Some " + prose)):
        [(printed, _)] = matter.with_terms([(block, {None: reading})], registry)
        assert "\\ft Lit. a note." in usj.serialize(printed["content"])


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


def test_a_paragraph_sent_to_two_verses_is_rejected(
    policy: bible.policy.Policy,
) -> None:
    def duplicate(data: dict[str, Any]) -> None:
        key = data["notes"]["JOB 25:2"]["paragraphs"][0]
        data["notes"]["JOB 39:13"]["paragraphs"].append(key)

    with pytest.raises(CheckFailed, match="paragraphs placed twice"):
        matter.placements(policy.unprinted[0], changed(policy, "appendix", duplicate))


def test_an_appendix_note_follows_the_notes_at_the_start_of_its_verse(
    monkeypatch: pytest.MonkeyPatch,
    policy: bible.policy.Policy,
    read: bible.pipeline.Read,
    sources: bible.sources.Sources,
    ctx: bible.annotate.Context,
) -> None:
    def prepare(
        entry: Any, doc: Any, context: Any, report: Any
    ) -> tuple[Document, dict[str, list[Content]]]:
        moved: dict[str, list[Content]] = {}
        if source_id(entry) == "BAK":
            moved["EXO 28:23"] = [["Appendix."]]
        return doc, moved

    monkeypatch.setattr(matter, "unit", prepare)
    _, appendix_notes, _ = bible.pipeline.front_and_back(read, ctx)
    doc = usj.parse("\\id EXO\n\\c 28\n\\p\n\\v 23 \\f + \\ft Existing.\\f*Text.")
    result = bible.pipeline.linked("EXO", doc, appendix_notes, (), ctx)
    notes_at_start = bible.scripture.verses(result)["28:23"].notes
    assert [(at, usj.text_of(n["content"])) for at, n in notes_at_start] == [
        (0, "Existing."),
        (0, "Appendix."),
    ]
    assert [n["caller"] for _, n in notes_at_start] == ["+", "+"]
    assert notes_at_start[-1][1]["x-key"] == "EXO 28:23 Appendix"
