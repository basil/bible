"""Rendering swaps quote the translation they displaced, without a TR label."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from conftest import book

from bible import pipeline, policy, renderings, scripture, usj
from bible.byzantine import edit
from bible.byzantine.rows import Disposition
from bible.checks import CheckFailed
from bible.usj import Document


def corrected(
    text: str, operations: list[tuple[str, str, str]]
) -> tuple[Document, Document, list[Disposition]]:
    source = book("MAT", "\\v 1 " + text, chapter=1)
    verse = scripture.verses(source)["1:1"]
    ops: list[Any] = []
    for old, new, kind in operations:
        at = verse.text.index(old)
        ops.append(
            {
                "kind": kind,
                "ref": "MAT 1:1",
                "range": [at, at + len(old)],
                "old": old,
                "new": new,
                "raw_range": True,
            }
        )
    row: Disposition = {
        "unit": "MAT 1:1",
        "ref": "MAT 1:1",
        "disposition": "shared",
        "action": "edit",
        "flags": [],
        "ops": ops,
    }
    docs, rows = edit.execute({"MAT": source}, [row], ["MAT"])
    assert rows[0]["execution"] == "applied"
    return source, docs["MAT"], rows


def comparisons(doc: Document) -> list[tuple[str, str]]:
    return [
        (
            str(n["x-scope"]["declared"]),
            usj.text_of(
                next(
                    c["content"]
                    for c in n["content"]
                    if isinstance(c, dict) and c.get("marker") == "fqa"
                )
            ),
        )
        for _, n in scripture.verses(doc)["1:1"].notes
        if "rendering" in n.get("x-key", "")
    ]


@pytest.mark.parametrize(
    "text,ops,expected",
    [
        ("He spoke unto them.", [("spoke", "said", "replace")], [("said", "spoke")]),
        (
            "He spoke unto them.",
            [("unto", "to", "replace")],
            [("to them", "unto them")],
        ),
        (
            "He spoke unto them.",
            [("spoke unto", "", "delete")],
            [("He them", "He spoke unto them")],
        ),
        (
            "He spoke unto them.",
            [("He", "They", "replace"), ("them", "him", "replace")],
            [("They", "He"), ("him", "them")],
        ),
    ],
)
def test_rendering_notes(
    text: str, ops: list[tuple[str, str, str]], expected: list[tuple[str, str]]
) -> None:
    source, doc, rows = corrected(text, ops)
    before = copy.deepcopy((source, doc, rows))
    result = renderings.kjv("MAT", doc, source, rows, {})
    assert comparisons(result) == expected
    assert (source, doc, rows) == before
    assert scripture.verses(result)["1:1"].text == scripture.verses(doc)["1:1"].text


def test_repeated_lemma_widens_both_readings() -> None:
    source, doc, rows = corrected(
        "He spoke, and he said again.", [("spoke", "said", "replace")]
    )
    result = renderings.kjv("MAT", doc, source, rows, {})
    lemma, former = comparisons(result)[0]
    assert lemma != "said"
    assert lemma.replace("said", "spoke", 1) == former


def test_dependent_edits_restore_together() -> None:
    source, doc, rows = corrected(
        "He alone spoke unto them.",
        [("alone ", "", "delete"), ("them", "them alone", "replace")],
    )
    result = renderings.kjv("MAT", doc, source, rows, {})
    assert len(comparisons(result)) == 1
    lemma, former = comparisons(result)[0]
    assert "alone" in lemma and "alone" in former
    assert former == "He alone spoke unto them"


def test_supplied_words_are_quoted_as_an_alternative() -> None:
    source, doc, rows = corrected(
        "He \\add was\\add* there.", [("was", "stood", "replace")]
    )
    result = renderings.kjv("MAT", doc, source, rows, {})
    note = scripture.verses(result)["1:1"].notes[0][1]
    assert comparisons(result) == [("stood", "was")]
    assert note["category"] == "edition"
    assert "TR" not in usj.text_of(note["content"])


def test_brenton_rendering(read: pipeline.Read, declared: policy.Policy) -> None:
    original = read.brenton["PSA"]
    before = copy.deepcopy(original)
    result = renderings.brenton("PSA", original, declared.brenton_notes["renderings"])
    verses = scripture.verses(result)
    assert (
        verses["67:16"].text
        == "The mountain of God is a rich mountain; a mountain curdled like cheese, a rich mountain."
    )
    assert verses["67:17"].text == scripture.verses(original)["67:17"].text
    note = verses["67:16"].notes[0][1]
    assert note["x-key"] == "PSA 67:16"
    assert note["x-scope"]["declared"] == "mountain curdled like cheese"
    assert usj.text_of(note["content"]) == "67:16 Or, swelling mountain"
    assert original == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("from", "a wrong mountain"),
        ("source_note", "wrong note"),
        ("to", "a swelling mountain"),
        ("lemma", "rich mountain"),
    ],
)
def test_stale_brenton_rendering(
    read: pipeline.Read, declared: policy.Policy, field: str, value: str
) -> None:
    decisions = policy.thaw(declared.brenton_notes["renderings"])
    decisions["PSA 67:16"][field] = value
    with pytest.raises(CheckFailed):
        renderings.brenton("PSA", read.brenton["PSA"], decisions)


def test_reversed_margin_covers_an_edit_with_unchanged_context() -> None:
    source, doc, rows = corrected(
        "Our lamps are gone out.", [("are gone out", "are going out", "replace")]
    )
    margins = {"MAT 1:1 gone out": {"former": "gone out", "anchor": "going out"}}
    result = renderings.kjv("MAT", doc, source, rows, margins)
    assert not comparisons(result)
    with pytest.raises(CheckFailed, match="does not restore"):
        renderings.kjv(
            "MAT",
            doc,
            source,
            rows,
            {"MAT 1:1 gone": {"former": "gone", "anchor": "going out"}},
        )


def test_a_note_does_not_duplicate_the_sentences_stop() -> None:
    source, doc, rows = corrected(
        "He spoke unto them.", [("unto them.", "to him.", "replace")]
    )
    assert comparisons(renderings.kjv("MAT", doc, source, rows, {})) == [
        ("to him", "unto them")
    ]


def test_rendering_and_tr_notes_keep_distinct_labels() -> None:
    source, _, rows = corrected("He spoke unto them.", [("spoke", "said", "replace")])
    tr: Disposition = {
        "unit": "MAT 1:1#1",
        "ref": "MAT 1:1",
        "disposition": "override",
        "action": "edit",
        "flags": [],
        "ops": [
            {
                "kind": "replace",
                "ref": "MAT 1:1",
                "range": [14, 18],
                "old": "them",
                "new": "him",
                "raw_range": True,
            }
        ],
    }
    docs, executed = edit.execute({"MAT": source}, [rows[0], tr], ["MAT"])
    assert all(row["execution"] == "applied" for row in executed)
    result = renderings.kjv("MAT", docs["MAT"], source, executed, {})
    found = [n for _, n in scripture.verses(result)["1:1"].notes]
    assert len(found) == 2
    assert any("Textus Receptus" in usj.text_of(n["content"]) for n in found)
    assert comparisons(result) == [("said", "spoke")]


def test_inserted_words_quote_a_contextual_former_reading() -> None:
    source, doc, rows = corrected("He spoke unto them.", [("", "Then ", "insert")])
    assert comparisons(renderings.kjv("MAT", doc, source, rows, {})) == [
        ("Then He", "He")
    ]
