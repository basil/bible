"""The quotation links: each New Testament quotation of the Old joined to
the passage it quotes, both ways, from Turpie's tables (edition/turpie.json)
as edition/quotations.json reviews them, and Brenton's own "See" notes that
the links replace.
"""

import collections
import re
from dataclasses import dataclass

from bible import quotations, usj
from bible.checks import require
from bible.references import EDITION, Passage, Verse
from bible.versification import mapped_passages

# The printed glosses, by Turpie's class. C.I, which differs from the agreeing
# Hebrew and Septuagint in words alone, prints as A; the rest of C, and E,
# print the reference alone.
GLOSSES = {"A": "Heb. and LXX", "B": "Heb. against LXX", "D": "LXX against Heb."}


@dataclass(frozen=True)
class Relation:
    """One reviewed quotation, both sides in the edition's numbering."""

    id: str
    classification: str
    table_code: str
    nt: tuple[Passage, ...]
    ot: tuple[Passage, ...]

    @property
    def pairs(self):
        return tuple(
            (nt, ot)
            for nt_passage in self.nt
            for nt in nt_passage.verses
            for ot_passage in self.ot
            for ot in ot_passage.verses
        )


@dataclass(frozen=True)
class Link:
    """One direction of a relation, at the first verse of one of its passages."""

    origin: Verse
    passages: tuple[Passage, ...]
    targets: tuple[Passage, ...]
    classification: str
    table_code: str
    row_ids: tuple[str, ...]
    agreement: str | None


def agreement(cls, table_code):
    """Semantic equivalence class used by conflict and duplicate guards."""
    scope = quotations.scope(table_code)
    return (
        "A" if (cls, scope) == ("C", "I") else cls if cls in {"A", "B", "D"} else None
    )


def quotation_relations(rows, *, policy):
    """Resolve each reviewed row once, before deriving either direction."""
    relations = tuple(
        Relation(
            row["id"],
            row["class"],
            row["table_code"],
            tuple(row["nt"]),
            tuple(
                mapped
                for passage in row["ot"]
                for mapped in mapped_passages(passage, policy=policy)
            ),
        )
        for row in rows
    )
    require(
        len({r.id for r in relations}) == len(relations),
        "Duplicate quotation relation id",
    )
    return relations


def planned_links(relations, order, *, policy):
    """Reciprocal links at the first verse of each quotation's passages, by book.

    Each link names the whole of the other side's passages, and each of those
    passages carries a link back at its own first verse. A New Testament verse
    and a Brenton verse that rows gloss differently need an
    explicit editorial decision naming the rows, even where the links that
    join them display different ranges or stand at different verses. Two
    links that would print alike at one verse are refused.
    """
    by_book = collections.defaultdict(list)
    order = {code: index for index, code in enumerate(order)}

    def position(verse):
        return order[verse.book], verse.chapter, verse.number, verse.letter

    # Each (NT verse, Brenton verse) pair with the rows and glosses joining it.
    pair_glosses = collections.defaultdict(list)
    sources = {unit["id"]: unit["source"] for unit in policy.manifest["scripture"]}
    conflicts = policy.quotations["class_conflicts"]
    require(all(c.get("why") for c in conflicts), "Unexplained class conflict")
    resolved = {frozenset(c["rows"]) for c in conflicts}

    def add(relation, printed, passage, side, targets):
        origin = passage.first
        require(
            sources.get(origin.book) == ("kjv" if side == "nt" else "brenton"),
            f"Quotation verse outside its testament's printed books: {origin}",
        )
        link = Link(
            origin,
            (passage,),
            tuple(targets),
            relation.classification,
            relation.table_code,
            (relation.id,),
            printed,
        )
        by_book[origin.book].append(link)

    for relation in relations:
        printed = agreement(relation.classification, relation.table_code)
        for passage in relation.nt:
            add(relation, printed, passage, "nt", relation.ot)
        for passage in relation.ot:
            add(relation, printed, passage, "ot", relation.nt)
        for pair in relation.pairs:
            pair_glosses[pair].append((relation.id, printed))
    # Judged on every contributor, so the order of the rows doesn't matter.
    used_conflicts = set()
    for pair, contributors in pair_glosses.items():
        if len({c for _, c in contributors}) == 1:
            continue
        contributing_rows = frozenset(i for i, _ in contributors)
        require(
            contributing_rows in resolved,
            f"Conflicting glosses at {tuple(map(str, pair))}",
        )
        used_conflicts.add(contributing_rows)
    require(used_conflicts == resolved, "Unused link class conflict decisions")
    for links in by_book.values():
        visible = collections.Counter(
            (link.origin, tuple(link.targets), link.agreement) for link in links
        )
        repeated = sorted(
            (str(key[0]), tuple(map(str, key[1])))
            for key, count in visible.items()
            if count > 1
        )
        require(not repeated, f"Identical quotation links at one verse: {repeated}")
        links.sort(
            key=lambda link: (
                position(link.origin),
                position(link.targets[0].first),
                tuple(link.row_ids),
            )
        )
    return dict(by_book)


def bare(note):
    """Whether a note is nothing but "See" and what it cites: only such a
    note can be merged whole, since merging drops the note."""
    plain = note.text
    for citation in reversed(note.citations):
        plain = plain[: citation.start] + plain[citation.end :]
    return bool(note.citations) and re.fullmatch(r"\s*[Ss]ee[\s;.]*", plain) is not None


def cited_verses(note):
    """Every verse a note cites, or None if it cites what names no verse, as
    a chapter: even beside verses, as "Ps. 22; 23. 4", since a merge would
    drop it unnamed."""
    items = [
        item
        for citation in note.citations
        for _, runs in citation.targets
        for run in runs
        for item in run
    ]
    if not all(citation.passages for citation in note.citations) or any(
        item.first is None for item in items
    ):
        return None
    return [verse for citation in note.citations for verse in citation.verses]


def merged_notes(code, found, links, *, policy):
    """The keys of Brenton's See notes that the links at their verses replace.

    Read from brenton_notes, before restyling, so a merged note is never
    restyled and needs no exception. A note of one citation, of a verse, range
    or list, all of whose verses a link at its verse names, is merged. A note of
    several references, or one naming a verse no link there names, needs a
    reviewed decision: to preserve it, or to merge it naming what it drops.
    """
    # Only a Septuagint verse links to the New Testament, so only a Brenton book
    # has notes to merge.
    nt_rows = collections.defaultdict(lambda: collections.defaultdict(set))
    for link in links:
        for passage in link.targets:
            for verse in passage.verses:
                nt_rows[link.origin.label][verse].update(link.row_ids)
    if not nt_rows:
        return frozenset()
    decisions = policy.quotations["note_merges"]
    used_decisions = set()
    merges = []
    for note in found:
        if not (linked := nt_rows.get(note.reference)):
            continue
        # A note that cites a linked verse among other words, or cites what
        # names no verse, needs a decision too, lest it print beside its link.
        named = cited_verses(note)
        if named is not None and not set(named) & set(linked):
            continue
        dropped = [str(verse) for verse in named or () if verse not in linked]
        if decision := decisions.get(note.key):
            used_decisions.add(note.key)
            action = decision["action"]
            require(
                named is not None or action == "preserve",
                f"Merge decision for a note that names no verse: {note.key}",
            )
            # A merge loses no reference unless its decision says which.
            require(
                list(decision.get("drops", ()))
                == (dropped if action == "merge" else []),
                f"Merge decision must name exactly the verses it drops: {note.key}",
            )
        else:
            # A note that names no verse, as a chapter, can't be merged without
            # dropping what it names, so it needs a decision like any other.
            require(
                named is not None
                and bare(note)
                and len(note.citations) == 1
                and not dropped,
                f"Brenton cross-reference needs a merge decision: {note.key}",
            )
            action = "merge"
        if action == "merge":
            merges.append(note.key)
    linked_verses = {f"{code} {reference}" for reference in nt_rows}
    require(
        {k for k in decisions if k.partition("#")[0] in linked_verses}
        <= used_decisions,
        f"Unused note merge decisions in {code}",
    )
    return frozenset(merges)


def link_note(link, books):
    """A link as it prints: the other side's passages, and Turpie's judgment
    of the quotation's wording where the edition prints one."""
    target = EDITION.listed(link.targets, books)
    require(not set(target) & set("\\\n("), f"Malformed link target: {target}")
    gloss = GLOSSES.get(link.agreement)
    content = [usj.char("xo", f"{link.origin.label} ")]
    if gloss:
        content += [usj.char("xt", f"{target} "), usj.char("xta", f"({gloss})")]
    else:
        content.append(usj.char("xt", target))
    return usj.note("x", *content)
