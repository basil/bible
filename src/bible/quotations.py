"""Turpie's quotation heads as transcribed, and the edition's choices among them."""

from __future__ import annotations

import functools
import re
from collections.abc import Iterable, Sequence
from typing import TypedDict

import bible.policy
import bible.references
from bible.checks import require
from bible.policy_schema import TurpieRows
from bible.references import parse_passage, parse_passages
from bible.versification import lxx_to_edition, mapped_passages, unused_exceptions

ReviewedRow = TypedDict(
    "ReviewedRow",
    {
        "id": str,
        "class": str,
        "table_code": str,
        "nt": list[bible.references.Passage],
        "ot": list[bible.references.Passage],
    },
)


CLASSES = {"A", "B", "C", "D", "E"}
# Turpie's heads as read from the page, and the edition's exclusions, class
# conflicts, and Brenton note merges.


def scope(table_code: str) -> str | None:
    """The first Roman numeral component of a Turpie table code, if any."""
    match = re.match(r"^[A-E]\.(?:[sd]\.)?(I{1,3})(?:\.|$)", table_code)
    return match[1] if match else None


def nt_verses(
    passages: Iterable[bible.references.Passage],
) -> list[bible.references.Verse]:
    """Every verse of New Testament passages."""
    return [verse for passage in passages for verse in passage.verses]


def brenton_verses(
    passages: Iterable[bible.references.Passage], *, policy: bible.policy.Policy
) -> list[bible.references.Verse]:
    """Every printed Brenton verse of Septuagint passages."""
    return [
        lxx_to_edition(verse, policy=policy)
        for passage in passages
        for verse in passage.verses
    ]


def _unique(values: Sequence[bible.references.Verse], label: str) -> None:
    require(len(values) == len(set(values)), f"Duplicate {label}")


def _check_transcription(heads: Sequence[TurpieRows]) -> None:
    ids = [head["id"] for head in heads]
    require(
        ids == [f"Q{i:03d}" for i in range(1, 283)],
        "Turpie transcription must cover its 282 heads, Q001-Q282, once each in order",
    )
    for head in heads:
        require(head.get("pdf_page"), f"Missing Turpie page: {head['id']}")
        require(
            head.get("kind") in {"table", "appendix"}
            and (
                head.get("class") in CLASSES
                if head["kind"] == "table"
                else head.get("class") is None
            ),
            f"Invalid Turpie classification: {head['id']}",
        )
        require(
            head["nt"].get("printed") and head["nt"].get("normalized"),
            f"Missing printed NT heading: {head['id']}",
        )
        if head.get("source_headings") == "none":
            require(
                not head["lxx"].get("printed") and not head["hebrew"].get("printed"),
                f"Unexpected source-column heading: {head['id']}",
            )
        else:
            require(
                head["lxx"].get("printed") and head["lxx"].get("normalized"),
                f"Missing printed LXX heading: {head['id']}",
            )
            require(
                head["hebrew"].get("printed") and head["hebrew"].get("normalized"),
                f"Missing printed Hebrew heading: {head['id']}",
            )
        if head["kind"] == "table":
            require(
                head.get("table_code", "").startswith((head["class"] or "") + ".")
                and head.get("printed_sequence"),
                f"Missing table heading or sequence: {head['id']}",
            )
            # A and B divide by word order alone; C-E also by words or clauses.
            require(
                (scope(head["table_code"]) is None) == (head["class"] in {"A", "B"}),
                f"Invalid table scope: {head['id']}",
            )


@functools.cache
def reviewed_rows(*, policy: bible.policy.Policy) -> list[ReviewedRow]:
    """Turpie's heads that the edition links, as passages, with its decisions checked.

    The edition links each head's primary normalized passages; only an exclusion,
    or a narrowing to part of a head that Turpie withdraws the rest of, departs
    from Turpie, each with its reason.
    """
    heads = policy.turpie["rows"]
    _check_transcription(heads)
    excluded = policy.quotations["excluded"]
    require(
        set(excluded) <= {head["id"] for head in heads} and all(excluded.values()),
        "Exclusion of no Turpie head, or without a reason",
    )
    narrowed = policy.quotations["narrowed"]
    require(
        set(narrowed) <= {head["id"] for head in heads} - set(excluded)
        and all(n.get("why") for n in narrowed.values()),
        "Narrowing of no linked Turpie head, or without a reason",
    )
    rows: list[ReviewedRow] = []
    # Every Septuagint verse the rows link, so an exception no link reaches is
    # caught. An alternative the edition doesn't link can't justify one: the
    # introduction's table would owe it a row for a verse no link names.
    linked_passages = []
    for head in heads:
        if head["id"] in excluded:
            continue
        # An appendix discussion has no class for a link to carry.
        require(
            head["kind"] == "table",
            f"Unclassified appendix discussion included: {head['id']}",
        )
        # A passage read from Turpie's prose, not his heading, would carry his
        # class to a target he never tabled.
        require(
            head["lxx"].get("printed") and head["lxx"].get("normalized"),
            f"No printed Septuagint heading: {head['id']}",
        )
        normalized = head["lxx"]["normalized"]
        assert normalized is not None
        ot = parse_passages(normalized)
        if narrowing := narrowed.get(head["id"]):
            part = parse_passages(narrowing["lxx"])
            require(
                {v for p in part for v in p.verses} < {v for p in ot for v in p.verses},
                f"Narrowing to what isn't part of its head: {head['id']}",
            )
            ot = part
        classification = head["class"]
        assert classification is not None
        normalized_nt = head["nt"]["normalized"]
        assert normalized_nt is not None
        row: ReviewedRow = {
            "id": head["id"],
            "class": classification,
            "table_code": head["table_code"],
            "nt": parse_passages(normalized_nt),
            "ot": ot,
        }
        mapped = brenton_verses(row["ot"], policy=policy)
        _unique(nt_verses(row["nt"]), f"NT verses in {row['id']}")
        _unique(mapped, f"Brenton verses in {row['id']}")
        alternatives = [
            parse_passage(passage)
            for passage in head["lxx"].get("alternative_normalized", [])
        ]
        require(
            not set(brenton_verses(alternatives, policy=policy)) & set(mapped),
            f"Alternative selected as linked source: {row['id']}",
        )
        linked_passages += row["ot"]
        rows.append(row)
    unused = unused_exceptions(linked_passages, policy=policy)
    require(not unused, f"Verse mapping exceptions no quotation uses: {unused}")
    # A merge decision is used where a link lands on its note's verse, the first
    # of a printed passage, so one anywhere else would go unused unnoticed.
    linked = {
        str(printed.first)
        for row in rows
        for passage in row["ot"]
        for printed in mapped_passages(passage, policy=policy)
    }
    for key, decision in policy.quotations["note_merges"].items():
        require(
            decision.get("action") in {"merge", "preserve"}
            and decision.get("why")
            and decision.keys() <= {"action", "why", "drops"},
            f"Incomplete note merge decision: {key}",
        )
        # A merge that drops a verse of the note says which; preserving drops none.
        require(
            "drops" not in decision
            or (decision["action"] == "merge" and decision["drops"]),
            f"Note merge decision's drops without a merge: {key}",
        )
        require(
            key.partition("#")[0] in linked, f"Note merge decision at no link: {key}"
        )
    return rows
