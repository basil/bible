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


def presentation_policy(
    declared: bible.policy.Policy, **decisions: Any
) -> bible.policy.Policy:
    return declared.replace(
        prose={
            "presentation": {
                "why": "Editorial presentation.",
                "changes": [],
                **decisions,
            }
        }
    )


def test_prose_presentation_preserves_words_styles_and_inputs(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id NDX\n\\im \\sc Opening\\sc* \\it David\\it* said \\it word\\it*. This begins another topic.\n"
    )
    policy = presentation_policy(
        declared,
        sections=[{"unit": "NDX", "before": "This begins", "heading": "Another Topic"}],
        italics=[{"unit": "NDX", "opening": "Opening", "spans": ["word"]}],
    )
    before, decisions = copy.deepcopy(doc), bible.policy.thaw(policy.prose)
    result = matter.presented("NDX", doc, policy)
    assert usj.serialize(result).endswith(
        "\\im \\sc Opening\\sc* David said \\it word\\it*.\n\\s1 Another Topic\n\\ip This begins another topic.\n"
    )
    assert doc == before
    assert bible.policy.thaw(policy.prose) == decisions


@pytest.mark.parametrize(
    "span", ["Missing", "word", {"text": "word", "within": "Missing word"}]
)
def test_prose_italics_refuse_missing_or_ambiguous_words(
    declared: bible.policy.Policy, span: Any
) -> None:
    doc = usj.parse("\\id NDX\n\\ip A word and another word.\n")
    policy = presentation_policy(
        declared, italics=[{"unit": "NDX", "opening": "A word", "spans": [span]}]
    )
    with pytest.raises(CheckFailed, match="not met once"):
        matter.presented("NDX", doc, policy)


def test_prose_italics_use_context_for_repeated_words(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse("\\id NDX\n\\ip A word and another word.\n")
    policy = presentation_policy(
        declared,
        italics=[
            {
                "unit": "NDX",
                "opening": "A word",
                "spans": [{"text": "word", "within": "another word"}],
            }
        ],
    )
    assert "A word and another \\it word\\it*." in usj.serialize(
        matter.presented("NDX", doc, policy)
    )


@pytest.mark.parametrize(
    ("text", "within"), [("by", "urpose by"), ("purpose", "purpose b")]
)
def test_prose_italics_refuse_context_within_a_word(
    declared: bible.policy.Policy, text: str, within: str
) -> None:
    doc = usj.parse("\\id NDX\n\\ip A purpose by which.\n")
    policy = presentation_policy(
        declared,
        italics=[
            {
                "unit": "NDX",
                "opening": "A purpose",
                "spans": [{"text": text, "within": within}],
            }
        ],
    )
    with pytest.raises(CheckFailed, match="context within a word"):
        matter.presented("NDX", doc, policy)


def test_prose_italics_keep_notes_and_their_own_italics(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id XXB\n\\ip A \\f + \\ft \\it Note\\it*.\\f*word and"
        " more\\f + \\ft Other.\\f* here.\n"
    )
    policy = presentation_policy(
        declared,
        italics=[{"unit": "XXB", "opening": "A word", "spans": ["word", "and more"]}],
    )
    assert usj.serialize(matter.presented("XXB", doc, policy)).endswith(
        "\\ip A \\f + \\ft \\+it Note\\+it*.\\f*\\it word\\it* \\it and more\\it*"
        "\\f + \\ft Other.\\f* here.\n"
    )


@pytest.mark.parametrize("before", ["Missing", "word"])
def test_prose_sections_refuse_missing_or_ambiguous_breaks(
    declared: bible.policy.Policy, before: str
) -> None:
    doc = usj.parse("\\id NDX\n\\ip A word and another word.\n")
    policy = presentation_policy(
        declared, sections=[{"unit": "NDX", "before": before, "heading": "Topic"}]
    )
    with pytest.raises(CheckFailed, match="section not met once"):
        matter.presented("NDX", doc, policy)


def test_prose_references_move_inline_citations_without_losing_words(
    ctx: bible.annotate.Context,
) -> None:
    doc = usj.parse("\\id NDX\n\\p One. John 5. 39. Two. Luke 24. 25. Three.\n")
    policy = presentation_policy(
        ctx.policy,
        references=[
            {
                "unit": "NDX",
                "after": "Two",
                "passages": "LUK 24:25",
                "remove": "Luke 24. 25. ",
            },
            {
                "unit": "NDX",
                "after": "One",
                "passages": "JHN 5:39",
                "remove": "John 5. 39. ",
            },
            {"unit": "NDX", "after": "Three", "passages": "1CO 14"},
        ],
    )
    context = bible.annotate.Context(policy, ctx.inventory, ctx.books)
    unit, _ = matter.read("NDX", doc, {}, context)
    unit = matter.resolved(unit, "NDX", ctx.inventory, policy)
    before = copy.deepcopy(unit)
    decisions = bible.policy.thaw(policy.prose)
    result = matter.referenced(unit, "NDX", context)
    block, readings = result[-1]
    assert usj.text_of(block["content"]) == "One. Two. Three."
    assert [n["loc"] for n in usj.walk(block["content"]) if n["type"] == "ref"] == [
        "JHN 5:39",
        "LUK 24:25",
        "1CO 14",
    ]
    assert not readings[None].citations
    assert unit == before
    assert bible.policy.thaw(policy.prose) == decisions


@pytest.mark.parametrize(
    "punctuation", [".", ",", ";", ":", "!", "?", "),", '."', "—", "--"]
)
def test_prose_reference_callers_follow_punctuation_except_dashes(
    ctx: bible.annotate.Context, punctuation: str
) -> None:
    doc = usj.parse(f"\\id NDX\n\\p \\it Quotation\\it*{punctuation} Next.\n")
    policy = presentation_policy(
        ctx.policy,
        references=[{"unit": "NDX", "after": "Quotation", "passages": "JHN 5:39"}],
    )
    context = bible.annotate.Context(policy, ctx.inventory, ctx.books)
    unit, _ = matter.read("NDX", doc, {}, context)
    result = matter.referenced(unit, "NDX", context)
    content = result[-1][0]["content"]
    before = []
    for item in content:
        if usj.is_type(item, "note"):
            break
        before.append(item)
    assert usj.text_of(before) == "Quotation" + (
        "" if punctuation in {"—", "--"} else punctuation
    )
    assert usj.text_of(content) == f"Quotation{punctuation} Next."


def test_prose_caller_moves_unchanged_note_to_declared_sentence_end(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse("\\id XXB\n\\p There\\f + \\ft Evidence.\\f* is a claim. Next.\n")
    policy = presentation_policy(
        declared,
        callers=[{"unit": "XXB", "note": "Evidence.", "after": "is a claim."}],
    )
    before = copy.deepcopy(doc)
    result = matter.presented("XXB", doc, policy)
    assert "There is a claim.\\f + \\ft Evidence.\\f* Next." in usj.serialize(result)
    assert doc == before
    with pytest.raises(CheckFailed, match="changes nothing"):
        matter.presented("XXB", result, policy)


@pytest.mark.parametrize(
    "override, refusal",
    [
        ({"after": "Missing"}, "anchor not met once"),
        ({"after": "One"}, "anchor not met once"),
        # An anchor ends where a word does.
        ({"after": "Tw"}, "anchor not met once"),
        ({"after": "John 5"}, "caller within a citation"),
        ({"passages": "JHN5:39"}, "invalid chapter"),
        ({"after": "Two", "remove": "Missing"}, "inline citation not met once"),
        ({"after": "Two", "remove": "John 5. 39. End."}, "removal changes prose"),
        (
            {"after": "Two", "remove": "John 5. 39. ", "passages": "JHN 5:40"},
            "changes its target",
        ),
    ],
)
def test_prose_references_reject_stale_or_changed_decisions(
    ctx: bible.annotate.Context, override: dict[str, str], refusal: str
) -> None:
    doc = usj.parse("\\id NDX\n\\p One. One. Two. John 5. 39. End.\n")
    decision = {"unit": "NDX", "after": "Two", "passages": "JHN 5:39", **override}
    policy = presentation_policy(ctx.policy, references=[decision])
    context = bible.annotate.Context(policy, ctx.inventory, ctx.books)
    unit, _ = matter.read("NDX", doc, {}, context)
    unit = matter.resolved(unit, "NDX", ctx.inventory, policy)
    with pytest.raises(CheckFailed, match=refusal):
        matter.referenced(unit, "NDX", context)


def test_prose_references_name_each_book_once_and_keep_every_caller(
    ctx: bible.annotate.Context,
) -> None:
    doc = usj.parse("\\id NDX\n\\p One. John 5. 39. Two.\n")
    listed = {
        "unit": "NDX",
        "after": "Two",
        "passages": "ACT 17:11; ACT 8:28-29; LUK 24:25",
    }
    policy = presentation_policy(ctx.policy, references=[listed])
    context = bible.annotate.Context(policy, ctx.inventory, ctx.books)
    unit, _ = matter.read("NDX", doc, {}, context)
    unit = matter.resolved(unit, "NDX", ctx.inventory, policy)
    note = usj.notes_of(matter.referenced(unit, "NDX", context)[-1][0]["content"])[0]
    assert usj.text_of(note["content"]) == "Acts 17:11; 8:28–29; Luke 24:25"
    # A caller at the very end of another's removal would be removed with it.
    moved = {
        "unit": "NDX",
        "after": "One",
        "passages": "JHN 5:39",
        "remove": "John 5. 39.",
    }
    after = {"unit": "NDX", "after": "John 5. 39", "passages": "LUK 1:1"}
    policy = presentation_policy(ctx.policy, references=[moved, after])
    context = bible.annotate.Context(policy, ctx.inventory, ctx.books)
    unit, _ = matter.read("NDX", doc, {}, context)
    unit = matter.resolved(unit, "NDX", ctx.inventory, policy)
    with pytest.raises(CheckFailed, match="Overlapping prose references"):
        matter.referenced(unit, "NDX", context)


def test_translators_preface_headings_notes_and_modern_italics(
    edition: bible.pipeline.Edition,
    exported: dict[str, str],
) -> None:
    doc = edition.documents["NDX"]
    headings = [
        usj.text_of(b["content"]) for b in doc["content"] if b.get("marker") == "s1"
    ]
    assert len(headings) == 15
    assert [h.split(",")[0] for h in headings] == [
        "The Best Things Have Been Calumniated",
        "The Highest Personages Have Been Calumniated",
        "His Majesty’s Constancy",
        "The Praise of the Holy Scriptures",
        "Translation Necessary",
        "The Translation of the Old Testament out of the Hebrew into Greek",
        "Translation out of Hebrew and Greek into Latin",
        "The Translating of the Scripture into the Vulgar Tongues",
        "The Unwillingness of Our Chief Adversaries",
        "The Speeches and Reasons",
        "A Satisfaction to Our Brethren",
        "An Answer to the Imputations of Our Adversaries",
        "The Purpose of the Translators",
        "Reasons Moving Us to Set Diversity of Senses in the Margin",
        "Reasons Inducing Us Not to Stand Curiously upon an Identity of Phrasing",
    ]
    # A heading drops a closing full stop, not an abbreviation's period.
    assert headings[8].endswith("in the Mother Tongue, etc.")
    assert headings[12].endswith("Furniture, Care, etc.")
    majesty = next(
        i
        for i, b in enumerate(doc["content"])
        if b.get("marker") == "s1"
        and usj.text_of(b["content"]).startswith("His Majesty")
    )
    assert usj.text_of(doc["content"][majesty + 1]["content"]).startswith(
        "This, and more to this purpose"
    )
    notes = list(usj.notes_of(doc["content"]))
    assert len(notes) == 33
    assert all(n["marker"] == "x" and n["caller"] == "+" for n in notes)
    refs = [n["loc"] for n in usj.walk(doc["content"]) if n["type"] == "ref"]
    assert refs == [
        "2SA 11:25",
        "1KI 22:31",
        "2SA 6:16",
        "1KI 12:4",
        "NUM 32:14",
        "ECC 1:9",
        "ACT 7:51",
        "1SA 2:30",
        "JHN 5:39",
        "ISA 8:20",
        "ACT 17:11",
        "ACT 8:28",
        "MAT 22:29",
        "LUK 24:25",
        "2TI 3:15",
        "1CO 14",
        "GEN 29:10",
        "JHN 4:11",
        "ISA 29:11",
        "ISA 31:3",
        "2KI 7:9",
        "PSA 47:9",
        "JHN 3:20",
        "NEH 3:35",
        "JDG 8:2",
        "2KI 13:18",
        "JER 23:28",
        "JAS 3:2",
        "EZR 3:12",
        "GAL 4:16",
        "HEB 7:11",
        "HEB 8:7",
        "GEN 26:15",
        "JER 2:13",
        "MAT 8:34",
        "HEB 12:16",
        "HEB 10:31",
    ]
    assert "\\ref " not in exported["NDX"]
    assert "\\x + \\xt 2 Kgdms. 11:25\\x*" in exported["NDX"]
    assert "as it is in Samuel;\\x +" in exported["NDX"]
    assert "saith the wise man:\\x +" in exported["NDX"]
    assert "his own wife.\\x + \\xt 2 Kgdms. 6:16\\x* Solomon" in exported["NDX"]
    assert (
        "280 BC.\\f + \\ft See Preface to Lambert Bos’s edition of the LXX.\\f*"
        in exported["XXB"]
    )
    italic = [
        usj.text_of(n["content"])
        for n in usj.walk(doc["content"])
        if usj.is_type(n, "char", "it")
    ]
    assert "Hexapla" in italic and "Ethics" in italic
    assert "the sword devoureth as well one as another" in italic
    assert not {"David", "Solomon", "Moses", "Augustine", "England", "Greek"} & set(
        italic
    )
    prose = " ".join(
        usj.text_of(b["content"])
        for b in doc["content"]
        if b.get("marker") in {"p", "m"}
    )
    assert "The Scriptures we are commanded to search. They are commended" in prose
    assert (
        "yet the gleaning of grapes of Ephraim was not to be despised. Joash" in prose
    )


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


STRUCTURED = (
    "\\id XXB\n\\mt1 Title\n\\is1 Heading\n\\ip Opening words.\n\\ib\n"
    "\\ip A topic.\n\\ib\n\\im Gr. quoted.\n\\ip Plain.\n"
)


def with_markers(
    declared: bible.policy.Policy, *markers: dict[str, str]
) -> bible.policy.Policy:
    return declared.replace(
        prose={"structure": {"why": "Roles.", "changes": [], "markers": list(markers)}}
    )


def test_marker_decisions_give_front_matter_its_roles(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse(STRUCTURED)
    before = copy.deepcopy(doc)
    policy = with_markers(
        declared,
        {"unit": "XXB", "from": "ib", "to": "sd1", "before": "A topic", "why": "."},
        {"unit": "XXB", "from": "im", "to": "pm", "opening": "Gr.", "why": "."},
        {"unit": "XXB", "from": "ip", "to": "li1", "opening": "Plain", "why": "."},
    )
    result = matter.structured("XXB", doc, policy)
    assert doc == before
    assert [usj.paragraph(b) for b in result["content"][1:]] == [
        "mt1",
        "s1",
        "p",
        "sd1",
        "p",
        "pm",
        "li1",
    ]
    assert usj.text_of(result["content"][-1]["content"]) == "Plain."
    assert result["content"][4] == usj.para("sd1")


def test_a_heading_replaces_a_division_without_changing_its_paragraph(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse(STRUCTURED)
    before = copy.deepcopy(doc)
    policy = with_markers(
        declared,
        {
            "unit": "XXB",
            "from": "ib",
            "to": "s1",
            "before": "A topic",
            "heading": "A New Section",
            "why": "Name the topic instead of leaving a division.",
        },
    )
    decisions = bible.policy.thaw(policy.prose)
    result = matter.structured("XXB", doc, policy)
    assert result["content"][4] == usj.para("s1", "A New Section")
    assert result["content"][5] == {**doc["content"][5], "marker": "p"}
    assert not any(usj.paragraph(b) in {"ib", "sd1"} for b in result["content"])
    assert "\\s1 A New Section\n\\p A topic." in usj.serialize(result)
    assert doc == before
    assert bible.policy.thaw(policy.prose) == decisions


@pytest.mark.parametrize(
    "overrides, refusal",
    [
        ({}, "heading text is required"),
        ({"heading": ""}, "empty heading"),
        ({"heading": " Heading"}, "heading with surrounding space"),
        ({"heading": "Heading", "to": "sd1"}, "heading text is required only"),
        ({"heading": "Heading", "before": "Absent"}, "not met once"),
    ],
)
def test_invalid_heading_decisions_are_refused(
    declared: bible.policy.Policy, overrides: dict[str, str], refusal: str
) -> None:
    marker = {
        "unit": "XXB",
        "from": "ib",
        "to": "s1",
        "before": "A topic",
        "why": ".",
        **overrides,
    }
    with pytest.raises(CheckFailed, match=refusal):
        matter.structured("XXB", usj.parse(STRUCTURED), with_markers(declared, marker))


@pytest.mark.parametrize(
    "marker, refusal",
    [
        (
            {"unit": "XXB", "from": "ip", "to": "li1", "opening": "Absent", "why": "."},
            "not met once",
        ),
        (
            {"unit": "XXB", "from": "ip", "to": "li1", "opening": "", "why": "."},
            "known by its opening words",
        ),
        (
            {"unit": "XXB", "from": "ib", "to": "sd1", "before": "Nothing", "why": "."},
            "not met once",
        ),
        (
            {
                "unit": "XXB",
                "from": "ib",
                "to": "sd1",
                "opening": "A topic",
                "why": ".",
            },
            "known by its opening words",
        ),
        (
            {"unit": "XXB", "from": "ip", "to": "ip", "opening": "Plain", "why": "."},
            "changes nothing",
        ),
        (
            {"unit": "GEN", "from": "ip", "to": "li1", "opening": "Plain", "why": "."},
            "not front or back matter",
        ),
        (
            {"unit": "XXB", "from": "ip", "to": "li1", "opening": "Plain ", "why": "."},
            "surrounding space",
        ),
    ],
)
def test_marker_decisions_that_describe_nothing_are_refused(
    declared: bible.policy.Policy, marker: dict[str, str], refusal: str
) -> None:
    with pytest.raises(CheckFailed, match=refusal):
        matter.structured("XXB", usj.parse(STRUCTURED), with_markers(declared, marker))


def test_a_paragraph_two_marker_decisions_describe_is_refused(
    declared: bible.policy.Policy,
) -> None:
    policy = with_markers(
        declared,
        {"unit": "XXB", "from": "ip", "to": "li1", "opening": "Plain", "why": "."},
        {"unit": "XXB", "from": "ip", "to": "m", "opening": "Plain.", "why": "."},
    )
    with pytest.raises(CheckFailed, match="two marker decisions"):
        matter.structured("XXB", usj.parse(STRUCTURED), policy)


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
    # The early translations are the entries of a list, each with the
    # source's run-in name.
    assert introduction.index("\\li1 \\it The Old Latin.\\it*—") < introduction.index(
        "\\li1 \\it The Gothic.\\it*—"
    )
    assert introduction.index("\\li1 \\it The Gothic.\\it*—") < introduction.index(
        "Cardinal Caraffa"
    )
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
    assert "\\fqa Rephaim\\f*\\f + \\ft Giants. \\+it Heb.\\+it* רפאים. For" in kingdoms
    assert kingdoms.endswith("Isaiah.\\f*giants.")
    # The verses it supplies carry their numbers in the note.
    exodus = next(line for line in lines(edition, "EXO") if "Complutensian" in line)
    assert exodus.startswith(
        "\\v 23 \\f + \\ft The following verses are found neither in Codex Vaticanus"
        " nor Codex Alexandrinus, but appear thus in the Complutensian text:"
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
    assert not {"—", "adds", "omits", "St.", "p., pp."} & set(labels)
    # ...the edition's rows join his, in the registry's forms...
    assert {
        ("Vat.", "for Codex Vaticanus"),
        ("KJV", "for King James Version"),
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


def test_front_and_back_matter_heading_capitalization(
    edition: bible.pipeline.Edition,
) -> None:
    expected = {
        "XXD": ["\\mt1 Abbreviations Used in the Notes"],
        "XXB": ["\\mt1 Preface"],
        "XXE": [
            "\\mt1 Introduction",
            "\\mt2 A Historical Account of the Septuagint Version",
        ],
        "TDX": [
            "\\mt2 To the Most High and Mighty Prince",
            "\\mt1 James,",
            "\\mt2 by the Grace of God",
            "\\mt2 King of Great Britain, France, and Ireland,",
            "\\mt2 Defender of the Faith, etc.",
        ],
        "NDX": ["\\mt1 The Translators to the Reader"],
        "CNC": ["\\mt1 Editor’s Introduction"],
        "XXF": ["\\mt1 The Old Testament", "\\mt2 Brenton’s Septuagint"],
        "XXG": [
            "\\mt1 The New Testament",
            "\\mt2 King James Version",
            "\\mt2 Conformed to the Byzantine Text",
        ],
    }
    for code, headings in expected.items():
        assert [
            line for line in lines(edition, code) if line.startswith("\\mt")
        ] == headings
    assert (
        "\\po The Translators of the Bible wish Grace, Mercy, and Peace, through Jesus Christ our Lord."
        in lines(edition, "TDX")
    )
    # The textual variants, prepared for the website alone.
    assert [
        line
        for line in usj.serialize(edition.variants_page).splitlines()
        if line.startswith("\\mt")
    ] == ["\\mt1 Textual Variants"]


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
    assert "\\pm \\it Authorized Version\\it* bowed himself" in preface
    # Titles and headings drop their closing full stops.
    assert not [
        line
        for line in lines(edition, "XXE")
        if line.startswith(("\\s1", "\\s2", "\\mt")) and line.endswith(".")
    ]
    # Only the stop that closes a heading, not one before a style within it.
    heading = usj.parse("\\id XXB\n\\s1 St. \\it John\\it* I.\n")["content"][1]
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


def test_colophon_decisions_preserve_styles_scripture_and_inputs(
    declared: bible.policy.Policy,
) -> None:
    romans = usj.parse(
        "\\id ROM\n\\c 16\n\\p\n\\v 24 Amen.\n"
        "\\esb \\cat colophon\\cat*\n\\p ¶ Written \\add from\\add* Rome.\n\\esbe\n"
    )
    acts = usj.parse(
        "\\id ACT\n\\c 28\n\\p\n\\v 31 No man forbidding him.\n"
        "\\esb \\cat colophon\\cat*\n\\p The end of the Acts of the Apostles.\n\\esbe\n"
    )
    books = {"ROM": romans, "ACT": acts}
    before = copy.deepcopy(books)
    policy = presentation_policy(
        declared,
        colophons=[
            {"book": "ROM", "from": "¶ ", "to": ""},
            # Words rewritten across a style keep it.
            {"book": "ROM", "from": "from Rome", "to": "from Roma"},
            {"book": "ACT", "from": "The end of the Acts of the Apostles.", "to": ""},
        ],
    )
    result = matter.colophons(books, policy)
    assert books == before
    assert result["ACT"]["content"] == acts["content"][:-1]
    assert usj.text_of(result["ROM"]["content"][-1]["content"]) == "Written from Roma."
    assert "\\add from\\add*" in usj.serialize(result["ROM"])
    for code in books:
        assert bible.scripture.verses(result[code]) == bible.scripture.verses(
            books[code]
        )


@pytest.mark.parametrize("closing", [None, "Missing prefix.", "¶ Once ¶ twice."])
def test_colophon_decisions_refuse_stale_or_ambiguous_matches(
    declared: bible.policy.Policy,
    closing: str | None,
) -> None:
    doc = usj.parse(
        "\\id ROM\n\\c 16\n\\p\n\\v 24 Amen.\n"
        + (f"\\esb \\cat colophon\\cat*\n\\p {closing}\n\\esbe\n" if closing else "")
    )
    policy = presentation_policy(
        declared,
        colophons=[
            {"book": "ROM", "from": "¶ ", "to": ""},
        ],
    )
    with pytest.raises(CheckFailed, match="Colophon change.*ROM"):
        matter.colophons({"ROM": doc}, policy)


def test_all_nt_colophons_are_edited(edition: bible.pipeline.Edition) -> None:
    expected = set("ROM 1CO 2CO GAL EPH PHP COL 1TH 2TH 1TI 2TI TIT PHM HEB".split())
    found = set()
    for code, doc in edition.documents.items():
        for block in doc["content"]:
            if block.get("category") == "colophon":
                found.add(code)
                assert "¶" not in usj.text_of(block["content"])
    assert found == expected
    assert "The end of the Acts of the Apostles." not in usj.text_of(
        edition.documents["ACT"]["content"]
    )
