"""Assembly: the edition's books from the sources' chapters, under its names."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import changed

import bible.pipeline
import bible.policy
import bible.sources
from bible import assembly, usj
from bible.checks import CheckFailed
from bible.policy_schema import Entry


def test_every_book_prints_under_the_editions_name_and_heading(
    edition: bible.pipeline.Edition, policy: bible.policy.Policy
) -> None:
    for entry in policy.scripture:
        headings = [
            (block["marker"], usj.text_of(block["content"]))
            for block in edition.documents[entry["id"]]["content"]
            if block.get("marker") in ("mt1", "mt2", "mt3")
        ]
        assert headings == [
            tuple(line) for line in entry.get("heading", (("mt1", entry["title"]),))
        ]
    genesis = usj.serialize(edition.documents["GEN"]).splitlines()[:7]
    assert genesis == [
        "\\id GEN - Brenton English Septuagint",
        "\\h Genesis",
        "\\toc1 The First Book of Moses, Called Genesis",
        "\\toc2 Genesis",
        "\\toc3 Gen.",
        "\\mt2 The First Book of Moses, Called",
        "\\mt1 Genesis",
    ]


def test_heading_lines_must_spell_the_contents_title() -> None:
    names = {"title": "The Book of Ruth"}
    assert assembly.heading_lines({"id": "RUT"}, names) == [("mt1", "The Book of Ruth")]
    split: Entry = {"id": "RUT", "heading": (("mt2", "The Book of"), ("mt1", "Ruth"))}
    assert assembly.heading_lines(split, names) == [
        ("mt2", "The Book of"),
        ("mt1", "Ruth"),
    ]
    with pytest.raises(CheckFailed, match="do not spell the contents title"):
        assembly.heading_lines({"id": "RUT", "heading": (("mt1", "Ruth"),)}, names)
    with pytest.raises(CheckFailed, match="Heading that changes nothing"):
        assembly.heading_lines(
            {"id": "RUT", "heading": (("mt1", "The Book of Ruth"),)}, names
        )
    with pytest.raises(CheckFailed, match="Invalid heading"):
        assembly.heading_lines(
            {"id": "RUT", "heading": (("mt2", "The Book of Ruth"),)}, names
        )


def test_nehemias_is_the_close_of_the_file_that_holds_esdras(
    edition: bible.pipeline.Edition, read: bible.pipeline.Read
) -> None:
    assert list(edition.inventory["EZR"]) == [str(c) for c in range(1, 11)]
    assert list(edition.inventory["NEH"]) == [str(c) for c in range(1, 14)]
    assert usj.book_code(edition.documents["NEH"]) == "NEH"
    # Its first chapter is the source's eleventh, verse for verse.
    source = usj.inventory(read.brenton["EZR"])
    assert edition.inventory["NEH"]["1"] == source["11"]
    assert edition.inventory["NEH"]["13"] == source["23"]


def test_daniel_stands_between_susanna_and_bel_and_the_dragon(
    edition: bible.pipeline.Edition,
) -> None:
    blocks = edition.documents["DAG"]["content"]
    assert list(edition.inventory["DAG"]) == [str(c) for c in range(14)]
    # Each addition is a chapter that prints no number, under its heading.
    hidden = [
        (usj.text_of(blocks[n - 1]["content"]), block["number"])
        for n, block in enumerate(blocks)
        if block.get("pubnumber") == assembly.HIDDEN
    ]
    assert hidden == [("Susanna", "0"), ("Bel and the Dragon", "13")]
    lines = usj.serialize(edition.documents["DAG"]).splitlines()
    song = lines.index("\\s1 The Song of the Three Children")
    assert lines[song + 1 : song + 3] == ["\\p", lines[song + 2]]
    assert (
        lines[song + 2].startswith("\\v 25 ")
        and "Then Azarias stood up" in lines[song + 2]
    )


def test_the_close_of_malachias_is_a_chapter_of_its_own(
    edition: bible.pipeline.Edition, read: bible.pipeline.Read
) -> None:
    assert len(usj.inventory(read.brenton["MAL"])["3"]) == 24
    assert edition.inventory["MAL"]["3"] == [str(v) for v in range(1, 19)]
    assert edition.inventory["MAL"]["4"] == [str(v) for v in range(1, 7)]
    text = usj.serialize(edition.documents["MAL"])
    assert "\\c 4\n\\p\n\\v 1 For, behold, a day cometh burning as an oven" in text


def test_a_chapter_is_opened_only_at_the_words_the_file_names(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    def other_words(data: dict[str, Any]) -> None:
        data["relabel"]["MAL 3:19-24"]["opens"] = "For, lo, a day"

    with pytest.raises(CheckFailed, match="MAL chapter 4 boundary changed"):
        assembly.scripture_unit(
            policy.unit("MAL"),
            read.brenton,
            read.kjv,
            changed(policy, "versification", other_words),
        )


def test_a_divided_source_must_be_printed_whole(
    policy: bible.policy.Policy, sources: bible.sources.Sources
) -> None:
    assembly.check_divided(policy, sources)

    def shorter(data: dict[str, Any]) -> None:
        next(u for u in data["scripture"] if u["id"] == "NEH")["chapters"] = [11, 22]

    with pytest.raises(
        CheckFailed, match="Divided source not printed whole: brenton/EZR"
    ):
        assembly.check_divided(changed(policy, "manifest", shorter), sources)
