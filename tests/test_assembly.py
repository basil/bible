"""Assembly: the edition's books from the sources' chapters, under its names."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from conftest import changed

import bible.pipeline
import bible.policy
import bible.sources
from bible import assembly, scripture, usj, versification
from bible.checks import CheckFailed
from bible.policy_schema import Entry
from bible.references import Verse


@pytest.mark.parametrize(
    "book, closing",
    [
        ("ROM", "\\mi ¶ Written from Rome."),
        ("ACT", "\\d The end of the Acts of the Apostles."),
    ],
)
def test_terminal_colophons_are_separate_from_scripture(
    book: str, closing: str
) -> None:
    doc = usj.parse(f"\\id {book}\n\\c 1\n\\p\n\\v 1 Scripture.\n\\b\n{closing}")
    before = deepcopy(doc)
    result = assembly.colophon(doc)
    assert doc == before
    assert scripture.verses(result)["1:1"].text == "Scripture."
    sidebar = result["content"][-1]
    assert sidebar["type"] == "sidebar" and sidebar["category"] == "colophon"
    assert usj.is_type(sidebar["content"][0], "para", "p")
    assert usj.text_of(sidebar["content"]) == closing.split(" ", 1)[1]
    assert result["content"][-2]["marker"] == "p"
    assert usj.parse(usj.serialize(result)) == result


def test_an_ordinary_terminal_paragraph_is_not_a_colophon() -> None:
    doc = usj.parse("\\id ROM\n\\c 1\n\\p\n\\v 1 Scripture.\n\\mi Further scripture.")
    assert assembly.colophon(doc) is doc
    assert scripture.verses(doc)["1:1"].text == "Scripture.\nFurther scripture."


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
    genesis = usj.serialize(edition.documents["GEN"]).splitlines()[:8]
    assert genesis == [
        "\\id GEN - Brenton English Septuagint",
        "\\usfm 3.1",
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
    with pytest.raises(CheckFailed, match="Invalid heading"):
        assembly.heading_lines(
            {"id": "RUT", "heading": (("mt3", "The Book of"), ("mt1", "Ruth"))}, names
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
        (usj.text_of(blocks[n + 1]["content"]), block["number"])
        for n, block in enumerate(blocks)
        if block.get("pubnumber") == scripture.HIDDEN
    ]
    assert hidden == [("Susanna", "0"), ("Bel and the Dragon", "13")]
    assert all(
        blocks[n + 1]["marker"] == "cl"
        for n, block in enumerate(blocks)
        if block.get("pubnumber") == scripture.HIDDEN
    )
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


def test_a_relocated_passage_prints_the_hebrews_labels(
    edition: bible.pipeline.Edition,
) -> None:
    printed = scripture.printed(edition.documents["PRO"])
    # Each passage's first verse names its chapter, as does the verse after
    # it back in chapter 24; the rest are numbered on.
    assert [printed[label] for label in ("24:22f", "24:22g", "24:22t")] == [
        "30:1",
        "30:2",
        "30:14",
    ]
    assert [printed[label] for label in ("24:23", "24:35", "24:53", "24:54")] == [
        "24:23",
        "30:15",
        "30:33",
        "31:1",
    ]
    assert printed["24:62"] == "31:9"
    assert "24:24" not in printed and "24:22e" not in printed
    text = usj.serialize(edition.documents["PRO"])
    assert "\\v 22f \\vp 30:1\\vp* " in text and "\\v 36 \\vp 16\\vp* " in text


def test_a_preface_and_a_title_print_no_number(
    edition: bible.pipeline.Edition,
) -> None:
    # The translator's Prologue is a true introduction, outside scripture
    # numbering; the book's first verse is 1:1.
    assert list(edition.inventory["SIR"])[0] == "1"
    assert "0" not in edition.inventory["SIR"]
    lines = usj.serialize(edition.documents["SIR"]).splitlines()
    first = lines.index("\\c 1")
    assert any(line.startswith("\\imt1 ") for line in lines[:first])
    assert sum(line.startswith("\\ip ") for line in lines[:first]) == 2
    assert not any(line.startswith(("\\c ", "\\v ", "\\cp ")) for line in lines[:first])
    assert next(line for line in lines[first:] if line.startswith("\\v ")).startswith(
        "\\v 1 All wisdom"
    )
    # The Epistle's title is its verse 0, and its verses are 1-72 but 16, which
    # the Greek editions begin inside Brenton's clause.
    assert edition.inventory["LJE"]["1"] == [str(v) for v in range(73) if v != 16]
    assert scripture.printed(edition.documents["LJE"]) == {"1:0": ""}
    title = scripture.verses(edition.documents["LJE"])["1:0"]
    assert all(
        edition.documents["LJE"]["content"][p[0]]["marker"] == "d" for p in title.parts
    )


def test_a_printed_label_must_fit_its_verses(
    policy: bible.policy.Policy, edition: bible.pipeline.Edition
) -> None:
    def unlabelled(items: usj.Content) -> usj.Content:
        return [
            (
                {"type": "verse", "marker": "v", "number": item["number"]}
                if usj.is_type(item, "verse")
                else item
            )
            for item in items
        ]

    plain = usj.with_content(edition.documents["PRO"], unlabelled)

    def relocated(to: str) -> bible.policy.Policy:
        return changed(
            policy,
            "versification",
            lambda data: data["relocations"]["PRO 30:1-14"].update(to=to),
        )

    with pytest.raises(CheckFailed, match="runs past its chapter"):
        assembly.printed("PRO", plain, relocated("PRO 24:62"))
    with pytest.raises(CheckFailed, match="Relocated passage not printed"):
        assembly.printed("PRO", plain, relocated("PRO 24:22j"))
    twice = changed(
        policy,
        "versification",
        lambda data: data["unnumbered"].update({"PRO 24:22f": {"why": "."}}),
    )
    with pytest.raises(CheckFailed, match="printed under two labels"):
        assembly.printed("PRO", plain, twice)
    unexplained = changed(
        policy,
        "versification",
        lambda data: data["unnumbered"].update({"PRO 24:1": {}}),
    )
    with pytest.raises(CheckFailed, match="without its reason"):
        assembly.printed("PRO", plain, unexplained)


def test_a_chapter_is_opened_only_at_the_words_the_file_names(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    def other_words(data: dict[str, Any]) -> None:
        data["relabel"]["MAL 3:19-24"]["opens"] = {"MAL 4:1": "For, lo, a day"}

    with pytest.raises(CheckFailed, match="MAL chapter 4 boundary changed"):
        assembly.scripture_unit(
            policy.unit("MAL"),
            read.brenton,
            read.kjv,
            changed(policy, "versification", other_words),
        )


def renumbered(
    policy: bible.policy.Policy,
    read: bible.pipeline.Read,
    code: str,
    relabel: dict[str, Any] | None = None,
    breaks: dict[str, Any] | None = None,
) -> usj.Document:
    """A book assembled under these renumbering decisions alone, in place of
    the edition's own for it."""

    def others(decided: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in decided.items() if not k.startswith(f"{code} ")}

    def decided(data: dict[str, Any]) -> None:
        data["relabel"] = {**others(data["relabel"]), **(relabel or {})}
        data["breaks"] = {**others(data.get("breaks", {})), **(breaks or {})}

    return assembly.scripture_unit(
        policy.unit(code),
        read.brenton,
        read.kjv,
        changed(policy, "versification", decided),
    )


def test_a_chapter_eBible_begins_early_can_close_the_one_before(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    doc = renumbered(
        policy,
        read,
        "JOL",
        {"JOL 3:1-5; JOL 4:1-21": {"edition": "JOL 2:28-32; JOL 3:1-21", "why": "."}},
    )
    found = usj.inventory(doc)
    assert list(found) == ["1", "2", "3"]
    assert found["2"] == [str(v) for v in range(1, 33)]
    assert found["3"] == [str(v) for v in range(1, 22)]
    text = usj.serialize(doc)
    assert "\\v 28 And it shall come to pass afterward" in text
    assert "\\c 3\n\\p\n\\v 1 For, behold, in those days" in text


def test_a_chapter_begun_at_a_relabelled_verse_names_its_words(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    relabel = {"edition": "GEN 31:55; GEN 32:1-32", "why": "."}
    doc = renumbered(
        policy,
        read,
        "GEN",
        {"GEN 32:1-33": {**relabel, "opens": {"GEN 32:1": "And Jacob departed"}}},
    )
    found = usj.inventory(doc)
    assert found["31"][-1] == "55" and found["32"] == [str(v) for v in range(1, 33)]
    assert "\\c 32\n\\p\n\\v 1 And Jacob departed for his journey" in usj.serialize(doc)
    with pytest.raises(CheckFailed, match="GEN chapter 32 boundary changed"):
        renumbered(policy, read, "GEN", {"GEN 32:1-33": relabel})
    with pytest.raises(CheckFailed, match="GEN chapter 32 boundary changed"):
        renumbered(
            policy,
            read,
            "GEN",
            {"GEN 32:1-33": {**relabel, "opens": {"GEN 32:1": "And Laban rose"}}},
        )


def test_a_chapter_begun_inside_a_paragraph_divides_it(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    doc = renumbered(
        policy,
        read,
        "JOL",
        {
            "JOL 2:19-27; JOL 3:1-5": {
                "edition": "JOL 3:1-14",
                "opens": {"JOL 3:1": "And the Lord answered"},
                "why": ".",
            }
        },
    )
    found = usj.inventory(doc)
    assert found["2"] == [str(v) for v in range(1, 19)]
    assert found["3"] == [str(v) for v in range(1, 15)]
    text = usj.serialize(doc)
    assert "\\v 18 But the Lord was jealous" in text
    assert "\\c 3\n\\p\n\\v 1 And the Lord answered" in text


def test_verses_are_divided_again_at_the_words_named(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    joined = renumbered(
        policy,
        read,
        "ISA",
        breaks={"ISA 38:14-15": {"edition": {"ISA 38:14": "As a swallow"}, "why": "."}},
    )
    assert "15" not in usj.inventory(joined)["38"]
    assert "who has delivered me, and removed the sorrow" in usj.serialize(joined)
    moved = renumbered(
        policy,
        read,
        "ISA",
        breaks={
            "ISA 38:14-15": {
                "edition": {"ISA 38:14": "As a swallow", "ISA 38:15": "who has"},
                "why": ".",
            }
        },
    )
    assert "\\v 15 who has delivered me" in usj.serialize(moved)
    split = renumbered(
        policy,
        read,
        "ISA",
        {"ISA 38:15-22": {"edition": "ISA 38:16-23", "why": "."}},
        {
            "ISA 38:14": {
                "edition": {"ISA 38:14": "As a swallow", "ISA 38:15": "for mine eyes"},
                "why": ".",
            }
        },
    )
    assert usj.inventory(split)["38"] == [str(v) for v in range(1, 24)]
    assert "\\v 15 for mine eyes have failed" in usj.serialize(split)
    with pytest.raises(CheckFailed, match="Words that don't open one place"):
        renumbered(
            policy,
            read,
            "ISA",
            breaks={
                "ISA 38:14-15": {
                    "edition": {"ISA 38:14": "As a swallow", "ISA 38:15": "my sorrow"},
                    "why": ".",
                }
            },
        )
    with pytest.raises(CheckFailed, match="Verse division out of order"):
        renumbered(
            policy,
            read,
            "ISA",
            breaks={
                "ISA 38:14-15": {"edition": {"ISA 38:14": "so will I"}, "why": "."}
            },
        )


def test_a_division_leaves_its_paragraphs_as_the_parser_would(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    doc = assembly.scripture_unit(policy.unit("TOB"), read.brenton, read.kjv, policy)
    for block in doc["content"]:
        if block["type"] == "para":
            assert block["content"] == usj.trimmed(block["content"])
    verses = scripture.verses(doc)
    # eBible's 7:9 opened the paragraph that the edition's 7:10 now opens:
    # nothing of it is left to 7:9.
    assert len(verses["7:9"].parts) == 1
    # eBible's 7:1, which opened a paragraph, joins the verse before.
    assert verses["7:1"].text.startswith(
        "And he came to Ecbatane.\nAnd he came to the house of Raguel"
    )


def test_a_division_keeps_a_note_that_closes_the_verse_before() -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 One two.\\f + \\ft Note.\\f*\n\\v 2 Three anew.\n"
    )

    def division(*parts: tuple[int, str]) -> versification.Break:
        return versification.Break(
            (Verse("GEN", 1, 1), Verse("GEN", 1, 2)),
            tuple((Verse("GEN", 1, n), words) for n, words in parts),
        )

    # A part that opens where eBible's next verse did keeps the note that
    # closes the verse before in that verse.
    found, _ = assembly.divided(
        doc, division((1, "One"), (2, "two"), (3, "Three")), set()
    )
    verses = scripture.verses(found)
    assert [len(verses[label].notes) for label in ("1:1", "1:2", "1:3")] == [0, 1, 0]
    # The words open a verse only as words of their own.
    with pytest.raises(CheckFailed, match="Words that don't open one place"):
        assembly.divided(doc, division((1, "One"), (2, "new")), set())


def test_a_renumbering_must_match_the_source(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    with pytest.raises(CheckFailed, match="relabelling that matches nothing"):
        renumbered(
            policy, read, "JOL", {"JOL 4:22": {"edition": "JOL 3:22", "why": "."}}
        )
    with pytest.raises(CheckFailed, match="Verses to divide not found together"):
        renumbered(
            policy,
            read,
            "ISA",
            breaks={
                "ISA 38:14; ISA 38:16": {"edition": {"ISA 38:14": "As"}, "why": "."}
            },
        )
    with pytest.raises(CheckFailed, match="Relabelling that changes nothing"):
        renumbered(policy, read, "JOL", {"JOL 3:1": {"edition": "JOL 3:1", "why": "."}})


def test_a_divided_source_must_be_printed_whole(
    policy: bible.policy.Policy, read: bible.pipeline.Read
) -> None:
    documents = {"brenton": read.brenton, "kjv": read.kjv}
    assembly.check_divided(policy, documents)

    def shorter(data: dict[str, Any]) -> None:
        next(u for u in data["scripture"] if u["id"] == "NEH")["chapters"] = [11, 22]

    with pytest.raises(
        CheckFailed, match="Divided source not printed whole: brenton/EZR"
    ):
        assembly.check_divided(changed(policy, "manifest", shorter), documents)


def test_a_relocation_is_carried_out_in_the_book_that_prints_it(
    policy: bible.policy.Policy,
) -> None:
    # The Hebrew's reference may name another book than the one it stands in.
    decided = changed(
        policy,
        "versification",
        lambda data: data["relocations"].update(
            {"DAN 4:1-2": {"to": "DAG 3:24", "why": "."}}
        ),
    )
    doc = usj.parse("\\id DAG\n\\c 3\n\\p\n\\v 23 a\n\\v 24 b\n\\v 25 c\n\\v 26 d\n")
    labels = scripture.printed(assembly.printed("DAG", doc, decided))
    assert (labels["3:24"], labels["3:25"], labels["3:26"]) == ("4:1", "4:2", "3:26")


def test_an_updated_poem_cannot_take_words_set_in_another_chapter(
    policy: bible.policy.Policy,
) -> None:
    # The edition sets the end of eBible's Esaias 63:19 in chapter 64, which
    # the Updated Brenton's labels alone cannot carry.
    def update(marker: str) -> usj.Document:
        return usj.parse(
            f"\\id ISA\n\\c 63\n\\{marker}\n\\v 19 We are become as at the "
            "beginning.\n\\c 64\n\\p\n\\v 1 As wax melteth.\n"
        )

    assembly.renumbered("ISA", update("p"), policy, words=False)
    with pytest.raises(CheckFailed, match="across a chapter in a poem"):
        assembly.renumbered("ISA", update("q1"), policy, words=False)
    # Nor where the verse opens in prose and runs on in a poem's line.
    running = usj.parse(
        "\\id ISA\n\\c 63\n\\p\n\\v 19 We are become as at the beginning.\n"
        "\\q1 If thou wouldest open the heaven,\n\\c 64\n\\p\n\\v 1 As wax melteth.\n"
    )
    with pytest.raises(CheckFailed, match="across a chapter in a poem"):
        assembly.renumbered("ISA", running, policy, words=False)
