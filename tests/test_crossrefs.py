"""Quotation links, and Brenton's "See" notes that they replace."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from conftest import book, changed, verse_lines

import bible.annotate
import bible.crossrefs
import bible.pipeline
import bible.policy
from bible import annotate, crossrefs, pipeline, quotations, scripture, usj
from bible.checks import CheckFailed
from bible.policy_schema import QuotationsNoteMerges
from bible.references import parse_passage, parse_passages


@pytest.fixture(scope="module")
def links(ctx: bible.annotate.Context) -> dict[str, list[crossrefs.Link]]:
    return pipeline.quotation_links(ctx)


def test_every_link_has_its_link_back(
    links: dict[str, list[bible.crossrefs.Link]],
) -> None:
    """A quotation is joined both ways, at the first verse of each passage."""
    forward = {
        (link.origin, target.first)
        for listed in links.values()
        for link in listed
        for target in link.targets
    }
    assert forward and all((there, here) in forward for here, there in forward)


def test_a_link_prints_the_other_passage_and_turpies_judgment(
    edition: bible.pipeline.Edition,
) -> None:
    matthew = usj.serialize(edition.documents["MAT"])
    # The reference alone, where Turpie's class prints no gloss.
    assert "\\v 23 \\x - \\xo 1:23 \\xt Esai. 7:14\\x*Behold, a virgin" in matthew
    assert "\\x - \\xo 2:15 \\xt Hos. 11:1 \\xta (Heb.\u00a0≠ LXX)\\x*" in matthew
    # Quotations sharing a printed agreement are one note, before its footnotes.
    psalms = usj.serialize(edition.documents["PSA"])
    assert (
        "\\v 7 \\x - \\xo 2:7 \\xt Acts 13:33; Heb. 1:5; 5:5 "
        "\\xta (Heb.\u00a0+ LXX)\\x*declaring the ordinance"
    ) in psalms


def test_grouped_notes_keep_categories_and_sort_all_targets(
    edition: bible.pipeline.Edition,
) -> None:
    psalm = scripture.verses(edition.documents["PSA"])["117:22"]
    assert [
        usj.text_of(note["content"]) for _, note in psalm.notes if note["marker"] == "x"
    ] == [
        "117:22 Matt. 21:42; Mark 12:10–11; Luke 20:17; 1 Pet. 2:7 (LXX\u00a0≠ Heb.)",
        "117:22 Acts 4:11",
    ]
    mark = scripture.verses(edition.documents["MRK"])["10:19"]
    assert [
        usj.text_of(note["content"]) for _, note in mark.notes if note["marker"] == "x"
    ] == ["10:19 Ex. 20:12, 13–17; Deut. 5:16, 17–21 (Heb.\u00a0+ LXX)"]


def test_one_note_per_printed_agreement_across_the_edition(
    edition: bible.pipeline.Edition, links: dict[str, list[crossrefs.Link]]
) -> None:
    expected: dict[str, set[str | None]] = {}
    for listed in links.values():
        for link in listed:
            expected.setdefault(str(link.origin), set()).add(link.agreement)
    printed = {
        f"{code} {reference}": sum(note["marker"] == "x" for _, note in verse.notes)
        for code in edition.scripture
        for reference, verse in scripture.verses(edition.documents[code]).items()
        if any(note["marker"] == "x" for _, note in verse.notes)
    }
    assert printed == {
        origin: len(agreements) for origin, agreements in expected.items()
    }
    assert sum(count > 1 for count in printed.values()) == 13


def test_links_joined_in_one_note_may_not_repeat_a_passage(
    ctx: bible.annotate.Context,
) -> None:
    origin = parse_passage("PSA 2:7")

    def link(row: str, targets: str) -> crossrefs.Link:
        return crossrefs.Link(
            origin.first, origin, tuple(parse_passages(targets)), (row,), "A"
        )

    joined = [link("Q1", "ACT 13:33; HEB 1:5"), link("Q2", "HEB 5:5")]
    [note] = crossrefs.link_notes(joined, ctx.books, ctx.terms)["2:7"]
    assert (
        usj.text_of(note["content"])
        == "2:7 Acts 13:33; Heb. 1:5; 5:5 (Heb.\u00a0+ LXX)"
    )
    with pytest.raises(CheckFailed, match="linked twice at one verse: PSA 2:7"):
        crossrefs.link_notes([*joined, link("Q3", "HEB 1:5")], ctx.books, ctx.terms)


def linked(
    verse: str, ctx: bible.annotate.Context, policy: bible.policy.Policy | None = None
) -> tuple[str, bible.annotate.Report]:
    """A verse of Isaiah whose quotation in Matthew is linked, with a note."""
    link = crossrefs.Link(
        parse_passage("ISA 99:3").first,
        parse_passage("ISA 99:3"),
        (parse_passage("MAT 3:3"),),
        ("Q999",),
        "A",
    )
    if policy is not None:
        ctx = annotate.Context(policy, ctx.inventory, ctx.books, ctx.terms, ctx.prose)
    doc, report = annotate.brenton("ISA", book("ISA", verse), [link], frozenset(), ctx)
    return verse_lines(doc)["3"], report


def test_a_see_note_that_a_link_covers_is_replaced_by_it(
    ctx: bible.annotate.Context,
) -> None:
    line, report = linked(
        r"\v 3 \x + \xo 99:3 \xt Mat. 3. 3.\x* The voice of one crying.", ctx
    )
    assert line == "The voice of one crying." and not report.keys
    # A note that says more than "See" can't be dropped for its link unread.
    with pytest.raises(CheckFailed, match="needs a merge decision: ISA 99:3"):
        linked(
            r"\v 3 The voice \f + \fr 99:3 \fqa Gr. \ft a sound. See \xt Mat. 3. 3.\f*of one crying.",
            ctx,
        )


def test_a_see_note_that_names_more_than_its_link_needs_a_decision(
    ctx: bible.annotate.Context, policy: bible.policy.Policy
) -> None:
    verse = r"\v 3 \x + \xo 99:3 \xt Mat. 3. 3; John 1. 23.\x* The voice of one crying."
    with pytest.raises(CheckFailed, match="needs a merge decision: ISA 99:3"):
        linked(verse, ctx)

    def decided(action: str, **more: Sequence[str]) -> bible.policy.Policy:
        def change(data: dict[str, Any]) -> None:
            data["note_merges"]["ISA 99:3"] = {
                "action": action,
                "why": "reviewed",
                **more,
            }

        return changed(policy, "quotations", change)

    # A decision in a verse the edition doesn't link is refused where it is read.
    with pytest.raises(CheckFailed, match="Note merge decision at no link"):
        quotations.reviewed_rows(policy=decided("preserve"))
    line, _ = linked(
        verse,
        ctx,
        policy.replace(
            quotations={
                **policy.quotations,
                "note_merges": {"ISA 99:3": {"action": "preserve", "why": "reviewed"}},
            }
        ),
    )
    assert line.startswith("\\f - \\fr 99:3 \\ft See \\xt Matt. 3:3; John 1:23\\f*")
    # A merge must say which verse it drops.
    merged: dict[str, QuotationsNoteMerges] = {
        "ISA 99:3": {"action": "merge", "why": "reviewed"}
    }
    with pytest.raises(CheckFailed, match="must name exactly the verses it drops"):
        linked(
            verse,
            ctx,
            policy.replace(quotations={**policy.quotations, "note_merges": merged}),
        )
    merged["ISA 99:3"]["drops"] = ("JHN 1:23",)
    line, _ = linked(
        verse,
        ctx,
        policy.replace(quotations={**policy.quotations, "note_merges": merged}),
    )
    assert line == "The voice of one crying."


def test_the_merged_notes_of_the_edition_are_not_printed(
    edition: bible.pipeline.Edition, policy: bible.policy.Policy
) -> None:
    printed = {row["key"] for rows in edition.notes.values() for row in rows}
    for key, decision in policy.quotations["note_merges"].items():
        assert (key in printed) == (decision["action"] == "preserve"), key
