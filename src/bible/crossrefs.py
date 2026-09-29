"""Insert reciprocal quotation links and merge Brenton's matching notes."""

import collections
import itertools
import re

from bible import edition, quotations
from bible.checks import require
from bible.references import EDITION, VERSE_LABEL
from bible.usfm import verse_spans
from bible.versification import mapped_passages

# The printed glosses, by Turpie's class. C.I, which differs from the agreeing
# Hebrew and Septuagint in words alone, prints as A; the rest of C, and E,
# print the reference alone.
GLOSSES = {"A": "Heb. and LXX", "B": "Heb. against LXX", "D": "LXX against Heb."}


def gloss(cls, table_code):
    """What a link prints after its reference, or None for the reference alone."""
    scope = quotations.scope(table_code)
    return GLOSSES.get("A" if (cls, scope) == ("C", "I") else cls)


LINK = re.compile(
    rf"\\x - \\xo (\d+:{VERSE_LABEL}) \\xt ([^\\(]*?)"
    rf"(?: \\xta \(({'|'.join(map(re.escape, GLOSSES.values()))})\))?\\x\*"
)
# The transformation record of each book's links, which the notes review reads.
LINK_OPERATION = "insert reciprocal classified quotation links"
MERGE_OPERATION = "merge Brenton's See notes into quotation links"


def planned_links(rows, books):
    """Reciprocal links at the first verse of each quotation's passages, by book.

    Each link names the whole of the other side's passages, and each of those
    passages carries a link back at its own first verse. A New Testament verse
    and a Brenton verse that rows gloss differently need an
    explicit editorial decision naming the rows, even where the links that
    join them display different ranges or stand at different verses. Two
    links that would print alike at one verse are refused.
    """
    by_book = collections.defaultdict(list)
    # Each (NT verse, Brenton verse) pair with the rows and glosses joining it.
    pair_glosses = collections.defaultdict(list)
    sources = {unit["id"]: unit["source"] for unit in edition.MANIFEST["scripture"]}
    conflicts = quotations.DECISIONS["class_conflicts"]
    require(all(c.get("why") for c in conflicts), "Unexplained class conflict")
    resolved = {frozenset(c["rows"]) for c in conflicts}

    def add(row, printed, passage, side, targets, target_display):
        origin = passage.first
        require(
            sources.get(origin.book) == ("kjv" if side == "nt" else "brenton"),
            f"Quotation verse outside its testament's printed books: {origin}",
        )
        link = {
            "origin": origin,
            # The passages the link stands for, whose verses must all print.
            "passages": [passage],
            "targets": targets,
            "target_display": target_display,
            "class": row["class"],
            "table_code": row["table_code"],
            "gloss": printed,
            "row_ids": [row["id"]],
        }
        by_book[origin.book].append(link)

    for row in rows:
        printed = gloss(row["class"], row["table_code"])
        mapped_ot = [m for p in row["ot"] for m in mapped_passages(p)]
        to_ot = EDITION.listed(mapped_ot, books)
        to_nt = EDITION.listed(row["nt"], books)
        for passage in row["nt"]:
            add(row, printed, passage, "nt", mapped_ot, to_ot)
        for passage in mapped_ot:
            add(row, printed, passage, "ot", row["nt"], to_nt)
        for pair in itertools.product(
            quotations.nt_verses(row["nt"]), quotations.brenton_verses(row["ot"])
        ):
            pair_glosses[pair].append((row["id"], printed))
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
            (str(link["origin"]), link["target_display"], link["gloss"])
            for link in links
        )
        repeated = sorted(key[:2] for key, count in visible.items() if count > 1)
        require(not repeated, f"Identical quotation links at one verse: {repeated}")
        links.sort(
            key=lambda link: (
                books.position(link["origin"]),
                books.position(link["targets"][0].first),
            )
        )
    return dict(by_book)


def quotation_links(archives):
    """The edition's reviewed quotation links, by book."""
    return planned_links(quotations.reviewed_rows(), edition.books(archives))


def bare(note):
    """Whether a note is nothing but "See" and what it cites: only such a
    note can be merged whole, since merging drops the note."""
    plain = "".join(text for _, text in note.pieces)
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


def _link_usfm(link):
    target = link["target_display"]
    # A parenthesis in the target would run into the gloss's.
    require(not set(target) & set("\\\n("), f"Malformed link target: {target}")
    marker = f"\\x - \\xo {link['origin'].label} \\xt {target}"
    if link["gloss"]:
        marker += f" \\xta ({link['gloss']})"
    return marker + "\\x*"


def merged_notes(code, found, links, record):
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
        for passage in link["targets"]:
            for verse in passage.verses:
                nt_rows[link["origin"].label][verse].update(link["row_ids"])
    if not nt_rows:
        return frozenset()
    decisions = quotations.DECISIONS["note_merges"]
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
                decision.get("drops", []) == (dropped if action == "merge" else []),
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
            row_ids = sorted({rid for verse in named for rid in linked.get(verse, ())})
            merges.append(
                {
                    "note": note.key,
                    "verses": [str(verse) for verse in named],
                    "dropped": dropped,
                    "row_ids": row_ids,
                }
            )
    linked_verses = {f"{code} {reference}" for reference in nt_rows}
    require(
        {k for k in decisions if k.partition("#")[0] in linked_verses}
        <= used_decisions,
        f"Unused note merge decisions in {code}",
    )
    record(
        MERGE_OPERATION,
        merges=merges,
        merge_decisions=sorted(used_decisions),
    )
    return frozenset(merge["note"] for merge in merges)


def apply_links(code, text, links, record):
    """Add each link at the start of its verse, changing nothing else."""
    # Brenton's own cross-references are footnotes by now; only the links are \x.
    require("\\x " not in text, f"Cross-reference other than a quotation link: {code}")
    if not links:
        return text
    original = text
    require(
        all(link["origin"].book == code for link in links),
        f"Links for another book passed to {code}",
    )
    by_verse = collections.defaultdict(list)
    for link in links:
        by_verse[link["origin"].label].append(link)
    spans = verse_spans(text)
    # A link stands at its passage's first verse, so the rest are checked here.
    passage_verses = {
        verse.label
        for link in links
        for passage in link["passages"]
        for verse in passage.verses
    }
    require(
        passage_verses <= {reference for reference, _, _ in spans},
        f"Quotation verse missing from prepared scripture: {code}",
    )
    for reference, start, _ in reversed(spans):
        if reference in by_verse:
            # Like Brenton's notes, the links abut the verse's words: a space
            # after one would print as a second space after the verse number.
            markers = "".join(_link_usfm(link) for link in by_verse[reference])
            text = text[:start] + markers + text[start:]
    expected = sorted(
        (
            link["origin"].label,
            link["target_display"],
            link["gloss"] or "",
        )
        for link in links
    )
    require(
        sorted(LINK.findall(text)) == expected,
        f"Malformed or stale classified links: {code}",
    )
    require(
        LINK.sub("", text) == original,
        f"Scripture wording or notes changed by quotation links: {code}",
    )
    record(
        LINK_OPERATION,
        links=[
            {
                "origin": str(link["origin"]),
                "passages": [str(passage) for passage in link["passages"]],
                "class": link["class"],
                "table_code": link["table_code"],
                "gloss": link["gloss"],
                "target": link["target_display"],
                "row_ids": link["row_ids"],
            }
            for link in links
        ],
    )
    return text
