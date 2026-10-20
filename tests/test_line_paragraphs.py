"""Checked prose boundaries around poetry, without changing the words."""

import copy
from typing import Any

import pytest
from conftest import changed

import bible.pipeline
import bible.policy
from bible import lines, scripture, usj
from bible.checks import CheckFailed
from bible.usj import Document


def decisions(
    policy: bible.policy.Policy, entries: dict[str, list[dict[str, Any]]]
) -> bible.policy.Policy:
    result = changed(policy, "lines", lambda data: data.update(paragraphs=entries))
    lines.check(result)
    return result


def entry(
    at: str = "And he spoke.", before: str = "p", after: str = "m"
) -> dict[str, Any]:
    return {
        "at": at,
        "from": before,
        "to": after,
        "why": "Continue the quotation's frame.",
    }


def apply(doc: Document, policy: bible.policy.Policy) -> Document:
    return lines.paragraphs({"TST": doc}, policy)["TST"]


def test_marker_and_join_preserve_words_milestones_notes_styles_and_inputs(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id TST\n\\c 1\n\\q1\\v 1 A poem.\n"
        "\\p\\v 2 \\f + \\ft And he spoke.\\f*And \\it he\\it* spoke.\n"
        "\\p\\v 3 \\f + \\ft A caller.\\f*And he said,\n"
        "\\p\\v 4 Another episode.\n"
    )
    snapshot = copy.deepcopy(doc)
    policy = decisions(
        declared,
        {"TST 1:2": [entry()], "TST 1:3": [entry("And he said,", after="join")]},
    )
    result = apply(doc, policy)
    assert doc == snapshot
    assert [b["marker"] for b in result["content"] if b["type"] == "para"] == [
        "q1",
        "m",
        "p",
    ]
    assert result["content"][-1] is doc["content"][-1]
    # The joined paragraph is as the parser reads it: no space before a verse.
    assert result == usj.parse(usj.serialize(result))
    assert {key: verse.text for key, verse in scripture.verses(result).items()} == {
        key: verse.text for key, verse in scripture.verses(doc).items()
    }

    # Compare the objects whose ordering a paragraph operation must preserve.
    def inline(document: Document) -> list[usj.Node]:
        return [
            n
            for n in usj.walk(document["content"])
            if n["type"] in {"verse", "note", "char"}
        ]

    assert inline(result) == inline(doc)


def test_midverse_boundary_ignores_note_words_and_character_styles(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id TST\n\\c 1\n\\q1\\v 1 Poetry.\n"
        "\\p\\f + \\ft And he spoke.\\f*And \\it he\\it* spoke.\n"
    )
    result = apply(doc, decisions(declared, {"TST 1:1": [entry()]}))
    assert result["content"][-1]["marker"] == "m"


def test_a_midverse_join_keeps_a_space_between_the_words(
    declared: bible.policy.Policy,
) -> None:
    doc = usj.parse("\\id TST\n\\c 1\n\\p\\v 1 Prose,\n\\p and he went.\n")
    policy = decisions(declared, {"TST 1:1": [entry("and he went.", after="join")]})
    result = apply(doc, policy)
    assert scripture.verses(result)["1:1"].text == "Prose, and he went."
    assert result == usj.parse(usj.serialize(result))


def test_declared_prose_labels_and_join_reach_the_edition(
    edition: bible.pipeline.Edition,
) -> None:
    def first_block(code: str, verse: str) -> usj.Node:
        doc = edition.documents[code]
        block, *_ = scripture.verses(doc)[verse].parts[0]
        return doc["content"][block]

    for verse in ("7", "8", "12", "13", "18", "20", "22", "23", "24"):
        assert first_block("DEU", f"33:{verse}")["marker"] == "m"
    # Boyd's flush-left continuations that no decision changes, Scrivener's
    # paragraphing at Exodus 15:19 and 2 Kingdoms 3:35 notwithstanding.
    for code, verse in (("NUM", "24:25"), ("EXO", "15:19"), ("2SA", "3:35")):
        assert first_block(code, verse)["marker"] == "m"
    assert first_block("NUM", "24:14") is first_block("NUM", "24:15")
    for code, verse in (
        ("NUM", "23:14"),
        ("GEN", "25:24"),
        ("GEN", "49:28"),
        ("EXO", "15:22"),
        ("JOB", "4:1"),
        ("JOB", "42:7"),
    ):
        assert first_block(code, verse)["marker"] == "p"


@pytest.mark.parametrize(
    ("body", "entries", "message"),
    [
        (
            "\\p\\v 1 And he spoke.",
            {"TST 1:1": [entry("Missing words")]},
            "anchor not met once",
        ),
        ("\\p\\v 1 Before. And he spoke.", {"TST 1:1": [entry()]}, "does not open"),
        (
            "\\p\\v 1 And he spoke. And he spoke.",
            {"TST 1:1": [entry()]},
            "anchor not met once",
        ),
        ("\\m\\v 1 And he spoke.", {"TST 1:1": [entry()]}, "expected p"),
        ("\\p\\v 1 And he spoke.", {"TST 1:1": [entry(after="p")]}, "changes nothing"),
        ("\\p\\v 1 And he spoke.", {"TST 1:1": [entry(), entry()]}, "conflicting"),
        ("\\p\\v 1 And he spoke.", {"TST 1:2": [entry()]}, "missing verse"),
        ("\\p\\v 1 And he spoke.", {"GEN 1:1": [entry()]}, "no Old Testament book"),
        (
            "\\q1\\v 1 Poetry.\n\\p\\v 2 And he spoke.",
            {"TST 1:2": [entry(after="join")]},
            "join must follow",
        ),
        (
            "\\p\\v 1 Prose.\n\\b\n\\p\\v 2 And he spoke.",
            {"TST 1:2": [entry(after="join")]},
            "join must follow",
        ),
        (
            "\\p\\v 1 Prose.\n\\s1 Heading\n\\p\\v 2 And he spoke.",
            {"TST 1:2": [entry(after="join")]},
            "join must follow",
        ),
        (
            "\\p\\v 1 Prose.\n\\c 2\n\\p\\v 1 And he spoke.",
            {"TST 2:1": [entry(after="join")]},
            "join must follow",
        ),
        (
            "\\p\\v 1 Prose.\n\\mi\\v 2 And he spoke.",
            {"TST 1:2": [entry(after="join")]},
            "expected p",
        ),
    ],
)
def test_stale_conflicting_and_unsafe_decisions_stop(
    declared: bible.policy.Policy,
    body: str,
    entries: dict[str, list[dict[str, Any]]],
    message: str,
) -> None:
    doc = usj.parse("\\id TST\n\\c 1\n" + body + "\n")
    with pytest.raises(CheckFailed, match=message):
        apply(doc, decisions(declared, entries))


@pytest.mark.parametrize(
    "change",
    [
        {"from": "mi"},
        {"to": "inline"},
        {"at": " And he spoke."},
        {"why": ""},
        {"unexpected": True},
    ],
)
def test_paragraph_decision_shape_is_checked(
    declared: bible.policy.Policy, change: dict[str, Any]
) -> None:
    with pytest.raises(CheckFailed):
        decisions(declared, {"TST 1:1": [{**entry(), **change}]})
