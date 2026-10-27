"""Explicit New Testament poetry preserves the text while dividing its lines."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from conftest import changed

import bible.policy
from bible import lines, pipeline, scripture, usj
from bible.checks import CheckFailed
from bible.usj import Document


def decided(
    declared: bible.policy.Policy, entries: dict[str, Any]
) -> bible.policy.Policy:
    result = changed(declared, "lines", lambda data: data.update(new_testament=entries))
    lines.check(result)
    return result


def entry(*starts: tuple[str, str]) -> dict[str, Any]:
    return {
        "why": "The parallel clauses follow the BSB's indentation model.",
        "lines": [{"at": at, "marker": marker} for at, marker in starts],
    }


def reflow(source: str, policy: bible.policy.Policy) -> Document:
    return lines.new_testament({"MAT": usj.parse(source)}, policy)["MAT"]


def poems(doc: Document) -> list[tuple[str, str]]:
    return [
        (
            block["marker"],
            scripture.plain(
                usj.text_of(
                    " " if usj.is_type(item, "verse") else item
                    for item in block["content"]
                )
            ),
        )
        for block in doc["content"]
        if usj.paragraph(block) in lines.LEVELS
    ]


def test_reflow_preserves_prose_stanzas_notes_styles_and_inputs(
    declared: bible.policy.Policy,
) -> None:
    source = usj.parse(
        "\\id MAT\n\\c 1\n\\p \\v 1 He said:\n"
        "\\q1 Sing \\add bright morning,\\add* "
        "\\f + \\fr 1:1 \\ft A note.\\f*all ye lands.\n"
        "\\q1 For ever.\n\\q1 \\v 2 Praise his name.\n"
        "\\q1 And rejoice.\n\\b\n\\q1 \\v 3 Rest in peace.\n"
        "\\p \\v 4 Then he departed.\n"
    )
    usj.notes_of(source["content"])[0]["x-key"] = "MAT 1:1#1"
    before = copy.deepcopy(source)
    policy = decided(
        declared,
        {
            "MAT 1:1": entry(
                ("Sing", "q1"),
                ("morning,", "q2"),
                ("all ye lands.", "q1"),
                ("For ever.", "q2"),
            ),
            "MAT 1:2": entry(("Praise his name.", "q2"), ("And rejoice.", "q1")),
        },
    )
    policy_before = bible.policy.thaw(policy.lines)
    result = lines.new_testament({"MAT": source}, policy)["MAT"]
    assert source == before
    assert bible.policy.thaw(policy.lines) == policy_before
    assert poems(result) == [
        ("q1", "Sing bright"),
        ("q2", "morning,"),
        ("q1", "all ye lands."),
        ("q2", "For ever."),
        ("q2", "Praise his name."),
        ("q1", "And rejoice."),
        ("q1", "Rest in peace."),
    ]
    assert [
        block for block in result["content"] if block.get("marker") in {"p", "b"}
    ] == [block for block in before["content"] if block.get("marker") in {"p", "b"}]
    assert usj.notes_of(result["content"]) == usj.notes_of(before["content"])
    assert [
        (label, scripture.plain(verse.text))
        for label, verse in scripture.verses(result).items()
    ] == [
        (label, scripture.plain(verse.text))
        for label, verse in scripture.verses(before).items()
    ]
    output = usj.serialize(result)
    assert "\\add bright\\add*" in output
    assert "\\add morning,\\add*" in output


def test_a_verse_milestone_can_remain_inside_the_previous_line(
    declared: bible.policy.Policy,
) -> None:
    source = (
        "\\id MAT\n\\c 1\n\\q1 \\v 1 Weeping and wailing,\n"
        "\\v 2 and saying,\n\\q1 Alas, alas.\n"
    )
    result = reflow(
        source,
        decided(
            declared,
            {
                "MAT 1:1": entry(("Weeping", "q2")),
            },
        ),
    )
    assert poems(result) == [
        ("q2", "Weeping and wailing, and saying,"),
        ("q1", "Alas, alas."),
    ]
    assert scripture.verses(result)["1:2"].text == "and saying,\nAlas, alas."


def test_a_verse_wholly_continuing_a_line_needs_no_new_start(
    declared: bible.policy.Policy,
) -> None:
    source = "\\id MAT\n\\c 1\n\\q1 \\v 1 Stood afar off, \\v 2 and cried.\n"
    result = reflow(
        source, decided(declared, {"MAT 1:1": entry(("Stood afar off,", "q2"))})
    )
    assert poems(result) == [("q2", "Stood afar off, and cried.")]
    assert list(scripture.verses(result)) == ["1:1", "1:2"]


@pytest.mark.parametrize(
    "starts",
    [
        (("Absent", "q1"),),
        (("Sing", "q1"), ("Sing", "q2")),
        (("morning,", "q2"), ("Sing bright", "q1")),
        (("morning,", "q1"),),
        (("He said:", "q1"), ("Sing bright", "q2")),
        (("Sing bright", "q3"),),
    ],
)
def test_invalid_boundaries_or_levels_are_refused(
    declared: bible.policy.Policy, starts: tuple[tuple[str, str], ...]
) -> None:
    source = (
        "\\id MAT\n\\c 1\n\\p \\v 1 He said:\n"
        "\\q1 Sing bright morning, all ye lands.\n"
    )
    with pytest.raises(CheckFailed):
        reflow(source, decided(declared, {"MAT 1:1": entry(*starts)}))


def test_an_undecided_verse_keeps_its_lines(declared: bible.policy.Policy) -> None:
    result = reflow(
        "\\id MAT\n\\c 1\n\\q1 \\v 1 Sing.\n\\q1 \\v 2 Rejoice,\n\\q1 and be glad.\n",
        decided(declared, {"MAT 1:1": entry(("Sing.", "q2"))}),
    )
    assert poems(result) == [
        ("q2", "Sing."),
        ("q1", "Rejoice,"),
        ("q1", "and be glad."),
    ]


def test_a_run_without_a_decision_keeps_its_blocks(
    declared: bible.policy.Policy,
) -> None:
    # The second poem's notes stand where the splitter would move them.
    source = usj.parse(
        "\\id MAT\n\\c 1\n\\q1 \\v 1 Sing.\n\\p \\v 2 He said:\n"
        "\\q1 Rejoice ye \\f + \\fr 1:2 \\ft A note.\\f*\n"
        "\\q1 \\f + \\fr 1:2 \\ft Another.\\f*\\v 3 and be glad.\n"
    )
    result = lines.new_testament(
        {"MAT": source, "MRK": source},
        decided(declared, {"MAT 1:1": entry(("Sing.", "q2"))}),
    )
    assert result["MAT"]["content"][3:] == source["content"][3:]
    assert result["MRK"] is source


def test_a_decision_that_removes_a_poems_opening_line_is_named(
    declared: bible.policy.Policy,
) -> None:
    with pytest.raises(CheckFailed, match="opening line: MAT 1:2"):
        reflow(
            "\\id MAT\n\\c 1\n\\p \\v 1 He said:\n\\q1 \\v 2 Sing,\n\\q1 rejoice.\n",
            decided(declared, {"MAT 1:2": entry(("rejoice.", "q2"))}),
        )


def test_a_decision_that_keeps_the_lines_is_refused(
    declared: bible.policy.Policy,
) -> None:
    with pytest.raises(CheckFailed, match="changes nothing: MAT 1:2"):
        reflow(
            "\\id MAT\n\\c 1\n\\q1 \\v 1 Sing.\n\\q1 \\v 2 Rejoice.\n",
            decided(declared, {"MAT 1:2": entry(("Rejoice.", "q1"))}),
        )


def test_a_note_before_the_first_verse_of_a_poem_opens_its_line(
    declared: bible.policy.Policy,
) -> None:
    result = reflow(
        "\\id MAT\n\\c 1\n\\p \\v 1 He said:\n"
        "\\q1 \\f + \\fr 1:1 \\ft A note.\\f*\\v 2 Sing,\n\\q1 all ye lands.\n",
        decided(declared, {"MAT 1:2": entry(("Sing,", "q1"), ("all ye lands.", "q2"))}),
    )
    assert poems(result) == [("q1", "Sing,"), ("q2", "all ye lands.")]
    first = next(b for b in result["content"] if b.get("marker") == "q1")
    assert usj.is_type(first["content"][0], "note")


def test_a_decision_cannot_make_a_prose_verse_poetry(
    declared: bible.policy.Policy,
) -> None:
    with pytest.raises(CheckFailed, match="anchor in prose"):
        reflow(
            "\\id MAT\n\\c 1\n\\q1 \\v 1 Sing.\n\\p \\v 2 He departed.\n",
            decided(
                declared,
                {
                    "MAT 1:1": entry(("Sing.", "q2")),
                    "MAT 1:2": entry(("He departed.", "q1")),
                },
            ),
        )


# An anchor met twice needs its occurrence.
@pytest.mark.parametrize("occurrence", [None, 0, -1, True, 3])
def test_invalid_occurrences_are_refused(
    declared: bible.policy.Policy, occurrence: object
) -> None:
    decision = entry(("Sing,", "q1"))
    if occurrence is not None:
        decision["lines"][0]["occurrence"] = occurrence
    with pytest.raises(CheckFailed):
        reflow(
            "\\id MAT\n\\c 1\n\\q1 \\v 1 Sing, Sing, all ye lands.\n",
            decided(declared, {"MAT 1:1": decision}),
        )


def test_repeated_predicates_can_be_numbered(declared: bible.policy.Policy) -> None:
    decision = entry(("Sing,", "q1"), ("Sing,", "q2"))
    for number, line in enumerate(decision["lines"], 1):
        line["occurrence"] = number
    policy = decided(declared, {"MAT 1:1": decision})
    result = reflow("\\id MAT\n\\c 1\n\\q1 \\v 1 Sing, Sing, all ye lands.\n", policy)
    assert poems(result) == [("q1", "Sing,"), ("q2", "Sing, all ye lands.")]
    with pytest.raises(CheckFailed):
        reflow("\\id MAT\n\\c 1\n\\q1 \\v 1 Sing, all ye lands.\n", policy)


def test_final_view_preserves_explicit_nt_indentation(
    edition: pipeline.Edition,
) -> None:
    viewed = dict(pipeline.view(edition, "pdf"))
    luke = scripture.verses(viewed["LUK"])
    for label in ("1:47", "1:74", "2:31"):
        block = luke[label].parts[0][0]
        assert viewed["LUK"]["content"][block]["marker"] == "q2"
    revelation = scripture.verses(viewed["REV"])
    tribal_blocks = {
        block for verse in range(5, 9) for block, *_ in revelation[f"7:{verse}"].parts
    }
    assert len(tribal_blocks) == 12
    assert all(viewed["REV"]["content"][b]["marker"] == "q1" for b in tribal_blocks)
