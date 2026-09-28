"""Insert classified reciprocal quotations and merge Brenton's matching notes."""

import collections
import itertools
import re

from bible import edition, quotations
from bible.checks import require
from bible.edition import BOOK_NAME_MARKERS, resolved_book_names, source_usfm
from bible.usfm import book_header, marker_lines, verse_spans
from bible.versemap import RANGE, expand, mapped_passages, parse

# Turpie's classes A-E, glossed by how the quotation's wording stands to the
# Hebrew and the Septuagint. The letters don't print, so the glosses alone must
# tell the classes apart: C and E differ only in whether the two agree. As in
# a displayed equation, a line may break before = or ≠ but not after it; PTXprint
# sets the no-break space as \nobreak\space, so the font needs no glyph for it.
CLASS_GLOSSES = {
    "A": "Heb. and LXX",
    "B": "Heb. against LXX",
    "C": "neither, LXX =\u00a0Heb.",
    "D": "LXX against Heb.",
    "E": "neither, LXX ≠\u00a0Heb.",
}
LINK = re.compile(
    r"\\x - \\xo (\d+:\d+[a-z]?) \\xt ([^\\(]*?) \\xta "
    rf"\(({'|'.join(map(re.escape, CLASS_GLOSSES.values()))})\)\\x\*"
)
# The transformation record of each book's links, which the notes review reads.
LINK_OPERATION = "insert reciprocal classified quotation links"
MERGE_OPERATION = "merge Brenton's See notes into quotation links"


def book_names(archives):
    return {
        entry["id"]: resolved_book_names(entry, source_usfm(entry, archives))[
            "short_title"
        ]
        for entry in edition.MANIFEST["scripture"]
    }


def display_passage(passage, names):
    match = RANGE.fullmatch(passage)
    require(match is not None, f"Malformed displayed passage: {passage}")
    code, chapter, first, last = match.groups()
    require(code in names, f"No display name for {passage}")
    return f"{names[code]} {chapter}:{first}" + (f"–{last}" if last else "")


def planned_links(rows, names):
    """Reciprocal links at the first verse of each quotation's passages, by book.

    Each link names the whole of the other side's passages, and each of those
    passages carries a link back at its own first verse. Identical visible
    links at one origin are kept once with all their rows and passages. A New
    Testament verse and a Brenton verse that rows class differently need an
    explicit editorial decision naming the rows, even where the links that
    join them display different ranges or stand at different verses.
    """
    by_book = collections.defaultdict(list)
    signatures = {}
    # Each (NT verse, Brenton verse) pair with the rows and classes joining it.
    pair_classes = collections.defaultdict(list)
    sources = {unit["id"]: unit["source"] for unit in edition.MANIFEST["scripture"]}
    conflicts = quotations.DECISIONS["class_conflicts"]
    require(all(c.get("why") for c in conflicts), "Unexplained class conflict")
    resolved = {frozenset(c["rows"]) for c in conflicts}

    def add(row, passage, side, targets, target_display):
        origin = expand(passage)[0]
        require(
            sources.get(parse(origin)[0]) == ("kjv" if side == "nt" else "brenton"),
            f"Quotation verse outside its testament's printed books: {origin}",
        )
        signature = (origin, target_display, row["class"])
        if link := signatures.get(signature):
            link["row_ids"].append(row["id"])
            if passage not in link["passages"]:
                link["passages"].append(passage)
            return
        link = {
            "origin": origin,
            # The passages the link stands for, whose verses must all print.
            "passages": [passage],
            "targets": targets,
            "target_display": target_display,
            "class": row["class"],
            "row_ids": [row["id"]],
        }
        signatures[signature] = link
        by_book[parse(origin)[0]].append(link)

    for row in rows:
        mapped_ot = [m for p in row["ot"] for m in mapped_passages(p)]
        to_ot = "; ".join(display_passage(p, names) for p in mapped_ot)
        to_nt = "; ".join(display_passage(p, names) for p in row["nt"])
        for passage in row["nt"]:
            add(row, passage, "nt", mapped_ot, to_ot)
        for passage in mapped_ot:
            add(row, passage, "ot", row["nt"], to_nt)
        for pair in itertools.product(
            quotations.nt_verses(row["nt"]), quotations.brenton_verses(row["ot"])
        ):
            pair_classes[pair].append((row["id"], row["class"]))
    # Judged on every contributor, so the order of the rows doesn't matter.
    used_conflicts = set()
    for pair, contributors in pair_classes.items():
        if len({c for _, c in contributors}) == 1:
            continue
        contributing_rows = frozenset(i for i, _ in contributors)
        require(contributing_rows in resolved, f"Conflicting classes at {pair}")
        used_conflicts.add(contributing_rows)
    require(used_conflicts == resolved, "Unused link class conflict decisions")
    return dict(by_book)


def quotation_links(archives):
    """The edition's reviewed quotation links, by book."""
    return planned_links(quotations.reviewed_rows(), book_names(archives))


def _alias_key(name):
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def _aliases(archives):
    """Each KJV book's code, running head and abbreviation, as Brenton's notes cite it."""
    result = {}
    markers = (BOOK_NAME_MARKERS["short_title"], BOOK_NAME_MARKERS["abbreviation"])
    for code, source in archives["kjv"].items():
        # The names are in the book's header, before its first chapter.
        names = [code, *(n for _, n in marker_lines(book_header(source), markers))]
        for name in names:
            key = _alias_key(name)
            # A name shared by two books would silently cite the later one.
            require(
                result.get(key, code) == code, f"KJV book name is ambiguous: {name}"
            )
            result[key] = code
    return result


# Each item of a list is a verse or one range, so "6-9-11" isn't read.
VERSE_LIST = r"\d+(?:\s*-\s*\d+)?(?:\s*,\s*\d+(?:\s*-\s*\d+)?)*"


def _reference_verses(chunk, aliases):
    """The verses one reference names, as "Heb. 2. 6-9" or "Rom. 4. 7,8", or None."""
    item = re.fullmatch(rf"\s*(.+?)\s+(\d+)\.\s*({VERSE_LIST})[\s.,]*", chunk)
    if not item or _alias_key(item[1]) not in aliases:
        return None
    code, chapter = aliases[_alias_key(item[1])], int(item[2])
    verses = []
    for part in item[3].split(","):
        first, _, last = part.partition("-")
        first, last = int(first), int(last or first)
        if last < first:
            return None
        verses += [f"{code} {chapter}:{v}" for v in range(first, last + 1)]
    return verses


def _note_references(source, aliases):
    """Each reference of a bare Brenton See note, as its verses.

    Only a note that is nothing but "See" and its references qualifies, since
    merging drops the whole note. A reference may name a verse, a range, or a
    list, as "Heb. 2. 6-9" or "Rom. 4. 7,8".
    """
    match = re.fullmatch(r"\s*(?:\\ft )?[Ss]ee \\xt ([^\\]*?)\.?\s*", source)
    if not match:
        return None
    # As _cited_verses reads them, so a stray semicolon doesn't unmake a bare note.
    chunks = filter(str.strip, match[1].split(";"))
    result = [_reference_verses(chunk, aliases) for chunk in chunks]
    return None if None in result else result


def _cited_verses(source, aliases):
    """Every verse any note cites, bare or not, or None if a reference is unreadable."""
    result = []
    for span in re.findall(r"\\xt ([^\\]*)", source):
        for chunk in filter(str.strip, span.split(";")):
            if (verses := _reference_verses(chunk, aliases)) is None:
                return None
            result += verses
    return result


def _link_usfm(link):
    _, chapter, verse = parse(link["origin"])
    target = link["target_display"]
    # A parenthesis in the target would run into the gloss's.
    require(not set(target) & set("\\\n("), f"Malformed link target: {target}")
    gloss = CLASS_GLOSSES[link["class"]]
    # The reference first, then its gloss: the space before \xta prints.
    return f"\\x - \\xo {chapter}:{verse} \\xt {target} \\xta ({gloss})\\x*"


def merged_notes(code, found, links, archives, record):
    """The keys of Brenton's See notes that the links at their verses replace.

    Read from brenton_notes, before restyling, so a merged note is never
    restyled and needs no exception. A note of one reference, a verse, range or
    list, all of whose verses a link at its verse names, is merged. A note of
    several references, or one naming a verse no link there names, needs a
    reviewed decision: to preserve it, or to merge it naming what it drops.
    """
    # Only a Septuagint verse links to the New Testament, so only a Brenton book
    # has notes to merge.
    nt_rows = collections.defaultdict(lambda: collections.defaultdict(set))
    for link in links:
        reference = link["origin"].partition(" ")[2]
        for passage in link["targets"]:
            for verse in expand(passage):
                nt_rows[reference][verse].update(link["row_ids"])
    if not nt_rows:
        return frozenset()
    aliases = _aliases(archives)
    decisions = quotations.DECISIONS["note_merges"]
    used_decisions = set()
    merges = []
    for note in found:
        if not (linked := nt_rows.get(note.reference)):
            continue
        # A note that cites a linked verse among other words, or cites what
        # can't be read, needs a decision too, lest it print beside its link.
        named = _cited_verses(note.source, aliases)
        if named is not None and not set(named) & set(linked):
            continue
        references = _note_references(note.source, aliases)
        dropped = [verse for verse in named or () if verse not in linked]
        if decision := decisions.get(note.key):
            used_decisions.add(note.key)
            action = decision["action"]
            require(
                named is not None or action == "preserve",
                f"Merge decision for a note with an unreadable reference: {note.key}",
            )
            # A merge loses no reference unless its decision says which.
            require(
                decision.get("drops", []) == (dropped if action == "merge" else []),
                f"Merge decision must name exactly the verses it drops: {note.key}",
            )
        else:
            require(
                references is not None and len(references) == 1 and not dropped,
                f"Brenton cross-reference needs a merge decision: {note.key}",
            )
            action = "merge"
        if action == "merge":
            row_ids = sorted({rid for verse in named for rid in linked.get(verse, ())})
            merges.append(
                {
                    "note": note.key,
                    "verses": named,
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
        all(parse(link["origin"])[0] == code for link in links),
        f"Links for another book passed to {code}",
    )
    by_verse = collections.defaultdict(list)
    for link in links:
        by_verse[link["origin"].partition(" ")[2]].append(link)
    spans = verse_spans(text)
    # A link stands at its passage's first verse, so the rest are checked here.
    passage_verses = {
        verse.partition(" ")[2]
        for link in links
        for passage in link["passages"]
        for verse in expand(passage)
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
            link["origin"].partition(" ")[2],
            link["target_display"],
            CLASS_GLOSSES[link["class"]],
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
                "origin": link["origin"],
                "passages": link["passages"],
                "class": link["class"],
                "target": link["target_display"],
                "row_ids": link["row_ids"],
            }
            for link in links
        ],
    )
    return text
