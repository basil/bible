"""The quotation links: each New Testament quotation of the Old joined to
the passage it quotes, both ways, from Turpie's tables (edition/turpie.json)
as edition/quotations.json reviews them, and Brenton's own "See" notes that
the links replace.
"""

from __future__ import annotations

import collections
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import bible.policy
import bible.references
import bible.terminology
from bible import citations, extents, lemmas, notes, quotations, scripture, usj
from bible.checks import require
from bible.extents import Extent
from bible.policy_schema import QuotationsExtent
from bible.references import Passage, Verse
from bible.usj import Content, Node
from bible.versification import mapped_passages, require_own_labels

# The kind a link note's key names, after its verse: "PSA 8:3 link", and
# "PSA 8:3 link#2" for a verse's second.
LINK = "link"

# The table of the links' glosses: its headings, what a link without a
# gloss prints, and what each gloss means, by the agreement it prints (None
# for the reference alone).
GLOSS_HEADS = ("Gloss", "Turpie’s classes", "Meaning")
UNGLOSSED = "reference alone"
GLOSS_MEANINGS: dict[str | None, str] = {
    "A": "follows the Hebrew and the Septuagint where they agree, allowing"
    " differences in wording",
    "B": "follows the Hebrew where it differs from the Septuagint",
    "D": "follows the Septuagint where it differs from the Hebrew",
    None: "departs from the Hebrew and the Septuagint by whole clauses where"
    " they agree, as when a verse is abridged or two passages are joined, or"
    " follows neither where they differ",
}


def gloss(agreement: str | None, terms: bible.terminology.Registry) -> str | None:
    """The printed gloss of a link's agreement, by Turpie's class. C.I, which
    differs from the agreeing Hebrew and Septuagint in words alone, prints as
    A; the rest of C, and E, print the reference alone. A line may break after
    the symbol but not before it, as TeX breaks a formula after a binary
    operation or a relation."""
    hebrew, septuagint = terms.display("hebrew"), terms.display("septuagint")
    both = terms.display("turpie-agreement")
    differs = terms.display("turpie-difference")
    return {
        "A": f"{hebrew}\u00a0{both} {septuagint}",
        "B": f"{hebrew}\u00a0{differs} {septuagint}",
        "D": f"{septuagint}\u00a0{differs} {hebrew}",
    }.get(agreement or "")


def gloss_table(policy: bible.policy.Policy) -> Node:
    """The glosses of the quotation links, each beside Turpie's classes that
    it is printed for and what it means: a class whose divisions are glossed
    alike is named alone, and otherwise each division is named, as C\u00a0I.
    The glosses come first, in the order of their classes, and the reference
    alone last."""
    terms = bible.terminology.registry(policy)
    divisions: dict[str, dict[str | None, str | None]] = collections.defaultdict(dict)
    # The rows the links are made from, so that a class no link prints is
    # not listed.
    for row in quotations.reviewed_rows(policy=policy):
        cls, code = row["class"], row["table_code"]
        divisions[cls][quotations.scope(code)] = agreement(cls, code)
    classes: dict[str | None, list[str]] = collections.defaultdict(list)
    for cls, glossed in sorted(divisions.items()):
        if len(set(glossed.values())) == 1:
            classes[next(iter(glossed.values()))].append(cls)
        else:
            for division, agreed in sorted(glossed.items(), key=lambda d: d[0] or ""):
                classes[agreed].append(f"{cls}\u00a0{division}")
    require(
        all(gloss(a, terms) for a in classes if a is not None),
        "A class of Turpie's glossed as the links print no gloss",
    )
    require(
        set(classes) == set(GLOSS_MEANINGS),
        f"The glosses' meanings are for {sorted(map(str, GLOSS_MEANINGS))},"
        f" and the links print {sorted(map(str, classes))}",
    )

    def printed(agreed: str | None) -> str | Node:
        return gloss(agreed, terms) or usj.char("it", UNGLOSSED)

    return {
        "type": "table",
        "content": [
            usj.row(*(usj.cell(f"th{n}", c) for n, c in enumerate(GLOSS_HEADS, 1))),
            *(
                usj.row(
                    usj.cell("tc1", printed(a)),
                    usj.cell("tc2", ", ".join(c)),
                    usj.cell("tc3", GLOSS_MEANINGS[a]),
                )
                for a, c in sorted(
                    classes.items(), key=lambda g: (g[0] is None, g[0] or "")
                )
            ),
        ],
    }


@dataclass(frozen=True)
class Relation:
    """One reviewed quotation, both sides in the edition's numbering, each
    passage with the words of it that the quotation covers."""

    id: str
    classification: str
    table_code: str
    nt: tuple[Extent, ...]
    ot: tuple[Extent, ...]

    @property
    def pairs(self) -> tuple[tuple[Verse, Verse], ...]:
        return tuple(
            (nt, ot)
            for nt_extent in self.nt
            for nt in nt_extent.passage.verses
            for ot_extent in self.ot
            for ot in ot_extent.passage.verses
        )


@dataclass(frozen=True)
class Link:
    """One direction of a relation, at one of its passages: the note stands
    before the first quoted word, in the first verse of the passage that has
    one (origin), and the quotation milestones around the quoted words, from
    that word to the extent's last."""

    extent: Extent
    targets: tuple[Passage, ...]
    row_ids: tuple[str, ...]
    agreement: str | None

    @property
    def origin(self) -> Verse:
        return self.extent.first

    @property
    def passage(self) -> Passage:
        return self.extent.passage

    @property
    def start(self) -> int:
        """The index of the first quoted word among the origin's words."""
        return self.extent.start

    @property
    def sid(self) -> str:
        """What the quotation milestones around the words carry: the row and
        the passage."""
        return f"{self.row_ids[0]} {self.passage}"


def agreement(cls: str, table_code: str) -> str | None:
    """Semantic equivalence class used by conflict and duplicate guards."""
    scope = quotations.scope(table_code)
    return (
        "A" if (cls, scope) == ("C", "I") else cls if cls in {"A", "B", "D"} else None
    )


def row_extents(
    row: quotations.ReviewedRow,
    verses: extents.Verses,
    decisions: Mapping[str, QuotationsExtent],
    used: set[str],
    *,
    policy: bible.policy.Policy,
) -> tuple[tuple[Extent, ...], tuple[Extent, ...]]:
    """The words of one row's quotation on both sides, each passage in the
    edition's numbering: Turpie's English found there, or an extent decision
    carried out, which is added to those used."""

    def side(
        passages: Sequence[Passage], texts: Sequence[str], *, septuagint: bool
    ) -> tuple[Extent, ...]:
        # A Septuagint passage prints as the Brenton verses it maps to.
        def printed(passage: Passage) -> list[Passage]:
            return mapped_passages(passage, policy=policy) if septuagint else [passage]

        def find(key: str, quoted: str, ranges: Sequence[Passage]) -> list[Extent]:
            if key in decisions:
                used.add(key)
            found = extents.located(key, quoted, ranges, verses, decisions.get(key))
            require_own_labels(
                (verse for extent in found for verse in extent.passage.verses),
                f"Quotation {key}",
                policy=policy,
            )
            return found

        # One text he prints under several headings runs through their
        # passages, or gives the words of each; the words decide which.
        if len(passages) > 1 and len(set(texts)) == 1:
            ranges = [r for passage in passages for r in printed(passage)]
            key = extents.decision_key(row["id"], passages)
            if key in decisions or extents.spanning(texts[0], ranges, verses):
                return tuple(find(key, texts[0], ranges))
        return tuple(
            extent
            for passage, quoted in zip(passages, texts, strict=True)
            for extent in find(
                extents.decision_key(row["id"], [passage]), quoted, printed(passage)
            )
        )

    return (
        side(row["nt"], row["nt_quoted"], septuagint=False),
        side(row["ot"], row["ot_quoted"], septuagint=True),
    )


def quotation_relations(
    rows: Iterable[quotations.ReviewedRow],
    verses: extents.Verses,
    *,
    policy: bible.policy.Policy,
) -> tuple[Relation, ...]:
    """Resolve each reviewed row once, before deriving either direction: each
    passage of either side in the edition's numbering, with the words of it
    Turpie's English finds there, or an extent decision gives."""
    decisions = policy.quotations.get("extents", {})
    used: set[str] = set()
    relations = []
    for row in rows:
        nt, ot = row_extents(row, verses, decisions, used, policy=policy)
        relations.append(Relation(row["id"], row["class"], row["table_code"], nt, ot))
    require(
        len({r.id for r in relations}) == len(relations),
        "Duplicate quotation relation id",
    )
    require(
        used == set(decisions),
        f"Unused extent decisions: {sorted(set(decisions) - used)}",
    )
    return tuple(relations)


def planned_links(
    relations: Iterable[Relation],
    books: bible.references.Books,
    *,
    policy: bible.policy.Policy,
) -> dict[str, list[Link]]:
    """Reciprocal links at the first quoted word of each quotation's
    passages, by book.

    Each link names the whole of the other side's passages, and each of those
    passages carries a link back at its own first quoted word. A New Testament verse
    and a Brenton verse that rows gloss differently need an
    explicit editorial decision naming the rows, even where the links that
    join them display different ranges or stand at different verses. Two
    links that would print alike at one verse are refused; those that share
    a verse and a gloss print as one note (link_notes).
    """
    by_book: collections.defaultdict[str, list[Link]] = collections.defaultdict(list)
    # Each (NT verse, Brenton verse) pair with the rows and glosses joining it.
    pair_glosses: collections.defaultdict[
        tuple[Verse, Verse], list[tuple[str, str | None]]
    ] = collections.defaultdict(list)
    sources = {unit["id"]: unit["source"] for unit in policy.manifest["scripture"]}
    conflicts = policy.quotations["class_conflicts"]
    require(all(c.get("why") for c in conflicts), "Unexplained class conflict")
    resolved = {frozenset(c["rows"]) for c in conflicts}

    def add(
        relation: Relation,
        printed: str | None,
        extent: Extent,
        side: str,
        targets: Sequence[Extent],
    ) -> None:
        origin = extent.first
        require(
            sources.get(origin.book) == ("kjv" if side == "nt" else "brenton"),
            f"Quotation verse outside its testament's printed books: {origin}",
        )
        link = Link(
            extent,
            tuple(target.passage for target in targets),
            (relation.id,),
            printed,
        )
        by_book[origin.book].append(link)

    for relation in relations:
        printed = agreement(relation.classification, relation.table_code)
        for extent in relation.nt:
            add(relation, printed, extent, "nt", relation.ot)
        for extent in relation.ot:
            add(relation, printed, extent, "ot", relation.nt)
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
            (link.origin, link.start, tuple(link.targets), link.agreement)
            for link in links
        )
        repeated = sorted(
            (str(key[0]), key[1], tuple(map(str, key[2])))
            for key, count in visible.items()
            if count > 1
        )
        require(not repeated, f"Identical quotation links at one verse: {repeated}")
        links.sort(
            key=lambda link: (
                books.position(link.origin),
                link.start,
                books.position(link.targets[0].first),
                tuple(link.row_ids),
            )
        )
    return dict(by_book)


def bare(note: notes.Read) -> bool:
    """Whether a note is nothing but "See" and what it cites: only such a
    note can be merged whole, since merging drops the note."""
    plain = note.text
    for citation in reversed(note.citations):
        plain = plain[: citation.start] + plain[citation.end :]
    return bool(note.citations) and re.fullmatch(r"\s*[Ss]ee[\s;.]*", plain) is not None


def cited_verses(note: notes.Read) -> list[Verse] | None:
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


def merged_notes(
    code: str,
    found: Sequence[notes.Read],
    links: Sequence[Link],
    *,
    policy: bible.policy.Policy,
) -> frozenset[str]:
    """The keys of Brenton's See notes that their passages' links replace.

    Read from brenton_notes, before restyling, so a merged note is never
    restyled and needs no exception. A note of one citation, of a verse, range
    or list, all of whose verses its passages' links name, is merged. A note of
    several references, or one naming a verse none of those links names, needs
    a reviewed decision: to preserve it, or to merge it naming what it drops.
    """
    # Only a Septuagint verse links to the New Testament, so only a Brenton book
    # has notes to merge.
    nt_verses: collections.defaultdict[str, set[Verse]] = collections.defaultdict(set)
    for link in links:
        targets = bible.references.verses_of(link.targets)
        for verse in link.passage.verses:
            nt_verses[verse.label].update(targets)
    if not nt_verses:
        return frozenset()
    decisions = policy.quotations["note_merges"]
    used_decisions = set()
    merges = []
    for note in found:
        if not (linked := nt_verses.get(note.reference)):
            continue
        # A note that cites a linked verse among other words, or cites what
        # names no verse, needs a decision too, lest it print beside its link.
        named = cited_verses(note)
        if named is not None and not set(named) & linked:
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
    linked_verses = {f"{code} {reference}" for reference in nt_verses}
    require(
        {k for k in decisions if quotations.note_verse(k) in linked_verses}
        <= used_decisions,
        f"Unused note merge decisions in {code}",
    )
    return frozenset(merges)


def link_notes(
    links: Sequence[Link],
    verses: Mapping[str, scripture.Verse],
    books: bible.references.Books,
    terms: bible.terminology.Registry,
) -> list[tuple[Verse, int, Node]]:
    """One note per origin, first quoted word, and printed agreement, with
    targets in edition order, each with the offset in its verse where it
    stands: before the first quoted word, naming the quotation's opening
    words where it does not open the verse. A verse's notes are keyed in
    their order, "link", "link#2".

    Keep the relations separate upstream, where their classes and row ids
    govern reciprocal links, conflicts, and source-note merges.
    """
    groups: dict[tuple[Verse, int, str | None], list[Link]] = {}
    for link in links:
        groups.setdefault((link.origin, link.start, link.agreement), []).append(link)
    for (origin, _, _), grouped in groups.items():
        targets = [target for link in grouped for target in link.targets]
        # Identical links are refused where they are planned; joined in one
        # note, two that share a passage would print it twice.
        require(
            len(set(targets)) == len(targets),
            f"Quotation passage linked twice at one verse: {origin}",
        )

    def position(passage: Passage) -> tuple[int, int, int, str, int]:
        return (*books.position(passage.first), passage.last.number)

    ordered = sorted(
        groups.items(),
        key=lambda group: (
            books.position(group[0][0]),
            group[0][1],
            position(min((t for l in group[1] for t in l.targets), key=position)),
        ),
    )
    result: list[tuple[Verse, int, Node]] = []
    counted: collections.Counter[Verse] = collections.Counter()
    for (origin, start, agreement), grouped in ordered:
        verse = verses[origin.label]
        words = scripture.word_spans(verse.text)
        require(start < len(words), f"Quotation begins past its verse: {origin}")
        # The last word in this verse of the shortest of the quotations the
        # note joins: each ends there, or at the verse's last.
        last = min(
            link.extent.end if link.extent.last == origin else len(words) - 1
            for link in grouped
        )
        span = lemmas.quotation_lemma(verse.text, words, start, last)
        lemma = lemmas.lemma_text(verse.text, words, span) if span else None
        counted[origin] += 1
        key = f"{origin} {LINK}" + (
            f"#{counted[origin]}" if counted[origin] > 1 else ""
        )
        targets = sorted((t for link in grouped for t in link.targets), key=position)
        note = link_note(origin, lemma, targets, agreement, books, terms, key)
        result.append((origin, lemmas.opening(verse.text, words[start][1]), note))
    return result


def quotation_milestones(
    links: Sequence[Link], verses: Mapping[str, scripture.Verse]
) -> list[tuple[scripture.Verse, int, int, Content]]:
    """The quotation milestones of each link, as changes to its verses: one
    before the first quoted word, after the notes already there and before
    the link's own, and one after the last, each carrying the row and the
    passage."""
    changes: list[tuple[scripture.Verse, int, int, Content]] = []
    for link in links:
        first, last = verses[link.origin.label], verses[link.extent.last.label]
        start = scripture.word_spans(first.text)[link.start]
        end = scripture.word_spans(last.text)[link.extent.end]
        opening = lemmas.opening(first.text, start[1])
        changes.append(
            (
                first,
                opening,
                opening,
                [usj.milestone(usj.QUOTATION_START, sid=link.sid)],
            )
        )
        changes.append(
            (last, end[2], end[2], [usj.milestone(usj.QUOTATION_END, eid=link.sid)])
        )
    # The opening milestones first, so that at one place they precede the notes.
    return changes


def link_note(
    origin: Verse,
    lemma: str | None,
    targets: Sequence[Passage],
    agreement: str | None,
    books: bible.references.Books,
    terms: bible.terminology.Registry,
    key: str,
) -> Node:
    """Ordered references sharing one origin, opening words, and printed
    agreement: the verse's number, the quotation's opening words where it
    does not open the verse, the passages, and the gloss."""
    linked = citations.listed(targets, books.abbreviated)
    target = usj.text_of(linked)
    require(not set(target) & set("\\\n("), f"Malformed link target: {target}")
    glossed = gloss(agreement, terms)
    content = [usj.char("xo", f"{origin.label} ")]
    if lemma is not None:
        content.append(usj.char("xq", f"{lemma}: "))
    if glossed:
        content += [usj.char("xt", *linked, " "), usj.char("xta", f"({glossed})")]
    else:
        content.append(usj.char("xt", *linked))
    extra: usj.Extra = {
        "x-key": key,
        "x-scope": {"declared": lemma},
        "category": "edition",
    }
    return usj.note("x", *content, **extra)
