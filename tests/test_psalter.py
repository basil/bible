"""Psalter divisions preserve the scripture and accompany their openings."""

from collections.abc import Callable, Iterable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from conftest import changed

import bible.pipeline
from bible import pipeline, policy, psalter, scripture, usj
from bible.checks import CheckFailed
from bible.usj import Document, Node

type Shape = str | tuple[str, str | None, str | None, list[Shape]]

MAJOR = [
    1,
    9,
    17,
    24,
    32,
    37,
    46,
    55,
    64,
    70,
    77,
    85,
    91,
    101,
    105,
    109,
    118,
    119,
    134,
    143,
]
RULES = [
    4,
    7,
    11,
    14,
    18,
    21,
    27,
    30,
    34,
    36,
    40,
    43,
    49,
    51,
    58,
    60,
    67,
    68,
    72,
    74,
    78,
    81,
    88,
    89,
    94,
    97,
    103,
    104,
    106,
    107,
    112,
    115,
    124,
    129,
    137,
    140,
    145,
    148,
]


def source() -> Document:
    # Put all of Psalm 118 in one poetry paragraph to exercise splitting.
    return usj.parse(
        "\\id PSA\n"
        + "".join(
            f"\\c {chapter}\n\\d Introduction.\n\\q1\n"
            + "".join(
                f"\\v {verse} Word \\add added\\add* \\f + \\ft Note.\\f*end.\n"
                for verse in range(1, (176 if chapter == 118 else 2) + 1)
            )
            for chapter in range(1, 152)
        )
    )


def test_divisions_and_scripture_are_preserved(declared: policy.Policy) -> None:
    doc = source()
    original = deepcopy(doc)
    result = psalter.divided(doc, declared.psalter)
    assert doc == original
    before, after = scripture.verses(doc), scripture.verses(result)
    assert list(before) == list(after)
    assert {k: (v.text, v.notes) for k, v in before.items()} == {
        k: (v.text, v.notes) for k, v in after.items()
    }
    assert usj.notes_of(doc["content"]) == usj.notes_of(result["content"])
    assert scripture.heads(doc) == scripture.heads(result)
    blocks = result["content"]
    major, rules, minor = [], [], []
    chapter = ""
    for at, block in enumerate(blocks):
        if block["type"] == "chapter":
            chapter = block["number"]
        if block.get("marker") == "ms1":
            major.append(int(chapter))
            assert blocks[at - 1]["type"] == "chapter"
            assert blocks[at + 1] == usj.para("d", "Introduction.")
            assert block == usj.para(
                "ms1", f"The {psalter.ORDINALS[len(major)-1]} Kathisma"
            )
        if block.get("marker") == "sd2":
            rules.append(int(blocks[at + 1]["number"]))
            assert blocks[at + 1]["type"] == "chapter"
            assert block["content"] == []
        if block.get("marker") in {"s2", "s3"}:
            following = blocks[at + 1]
            assert following["marker"] == "q1"
            verse = following["content"][0]
            assert usj.is_type(verse, "verse")
            minor.append(
                (
                    chapter,
                    verse["number"],
                    usj.text_of(block["content"]),
                )
            )
    assert major == MAJOR
    assert rules == RULES
    assert minor == [
        ("118", "73", "Second Stasis"),
        ("118", "94", "Middle"),
        ("118", "132", "Third Stasis"),
    ]
    assert usj.parse(usj.serialize(result)) == result


def test_sample_divisions_follow_their_opening_chapters(
    declared: policy.Policy,
) -> None:
    doc = psalter.divided(source(), declared.psalter)
    for selected, expected in [
        ([3], []),
        ([4], ["sd2"]),
        ([8], []),
        ([9], ["ms1"]),
        ([118], ["ms1", "s2", "s3", "s2"]),
        ([151], []),
    ]:
        sample = pipeline.sample_chapters("PSA", doc, selected)
        assert [
            b["marker"]
            for b in sample["content"]
            if b.get("marker") in {"ms1", "sd2", "s2", "s3"}
        ] == expected


@pytest.mark.parametrize(
    "edit, refusal",
    [
        (lambda p: p["kathismata"].pop(), "twenty"),
        (lambda p: p["kathismata"][0].pop(), "three stases"),
        (lambda p: p["kathismata"][0].__setitem__(1, 3), "Unordered"),
        (lambda p: p["kathismata"][-1].__setitem__(2, 151), "cover Psalms"),
        (lambda p: p.__setitem__("middle", "118:71"), "within the Second"),
        (lambda p: p.__setitem__("middle", "118:73"), "within the Second"),
        (lambda p: p["kathismata"][16].__setitem__(0, "118:999"), "Missing Psalter"),
    ],
)
def test_invalid_decisions_stop_the_build(
    declared: policy.Policy, edit: Callable[[dict[str, Any]], object], refusal: str
) -> None:
    amended = changed(declared, "psalter", edit)
    with pytest.raises(CheckFailed, match=refusal):
        psalter.divided(source(), amended.psalter)


def test_new_markup_agrees_with_usfmtc(declared: policy.Policy, tmp_path: Path) -> None:
    import usfmtc

    doc = psalter.divided(source(), declared.psalter)
    path = tmp_path / "PSA.usfm"
    path.write_text(usj.serialize(doc), encoding="utf-8")
    theirs = usfmtc.readFile(str(path)).outUsj(None)

    def shape(items: Iterable[str | Node]) -> list[Shape]:
        return [
            (
                " ".join(item.split())
                if isinstance(item, str)
                else (
                    item["type"],
                    item.get("marker"),
                    item.get("number", item.get("code", item.get("caller"))),
                    shape(item.get("content", [])),
                )
            )
            for item in items
            if not isinstance(item, str) or item.strip()
        ]

    assert shape(doc["content"]) == shape(theirs["content"])


def test_pinned_psalms_keep_every_word_and_note(
    read: bible.pipeline.Read, declared: policy.Policy
) -> None:
    doc = read.brenton["PSA"]
    original = deepcopy(doc)
    result = psalter.divided(doc, declared.psalter)
    assert doc == original
    before, after = scripture.verses(doc), scripture.verses(result)
    assert list(before) == list(after)
    assert {k: (v.text, v.notes) for k, v in before.items()} == {
        k: (v.text, v.notes) for k, v in after.items()
    }
    assert usj.notes_of(doc["content"]) == usj.notes_of(result["content"])
    assert scripture.heads(doc) == scripture.heads(result)
