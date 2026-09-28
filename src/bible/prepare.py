"""Preparing each source book as the edition prints it: correcting eBible's
Brenton text, selecting and relabelling chapters, grouping Daniel, renaming
books, and setting the notes as footnotes, with checks that the source's
wording, notes and markup survive.

Every change is logged through a recorder into build/<mode>/transformations.json.
"""

import re
from dataclasses import dataclass

from bible import citations, edition, introductions, versification
from bible.checks import require
from bible.crossrefs import apply_links, merged_notes
from bible.edition import (
    BOOK_NAME_MARKERS,
    DANIEL_PARTS,
    heading_lines,
    normalize_title_lines,
    resolved_book_names,
    source_id,
    source_usfm,
)
from bible.notes import (
    brenton_notes,
    corrected_brenton,
    insert_marginal_notes,
    read_citations,
    restyle_brenton_notes,
)
from bible.references import Verse, verse_at
from bible.usfm import (
    HEADING_MARKERS,
    chapter_parts,
    inventory,
    marker_lines,
    passage_payload,
    preserved_markers,
    renumber_chapters,
    replace_marker_line,
    verse_spans,
)

# The Epistle Dedicatory's mt2 lines are its address ("&c.") and salutation.
FRONT_PERIOD_FREE_TITLE_MARKERS = ("h", "toc1", "mt1")
# Every such heading, not just the first: BAK heads book names with them. (OTH's
# headings are dropped for the book introductions.)
FRONT_PERIOD_FREE_HEADING_MARKERS = ("is1", "is2")


def recorder(log, code):
    """A function that logs one of a unit's transformations."""
    if log is None:
        log = []

    def record(operation, **details):
        log.append({"project_id": code, "operation": operation, **details})

    return record


def rename_book(entry, original, text, record):
    """The text with the edition's names and heading in place of the source's."""
    code = entry["id"]
    names = resolved_book_names(entry, original)
    text = replace_marker_line(text, "h", names["short_title"], code)
    for field, marker in BOOK_NAME_MARKERS.items():
        text = replace_marker_line(text, marker, names[field], code)
    # The whole heading is replaced, so the source's own subtitle lines go.
    # Only the header block before the first chapter is touched.
    head, chapters = chapter_parts(text)
    head = re.sub(r"^\\mt[23][^\n]*\n", "", head, flags=re.M)
    heading = "".join(
        f"\\{marker} {value}\n" for marker, value in heading_lines(entry, names)
    )
    head, count = re.subn(
        r"^\\mt1[^\n]*\n", lambda m: heading, head, count=1, flags=re.M
    )
    require(count == 1, f"Missing mt1 heading: {code}")
    text = head + "".join(chapters)
    markers = ("h", *BOOK_NAME_MARKERS.values(), *HEADING_MARKERS)
    source_lines = marker_lines(original, markers)
    edition_lines = marker_lines(text, markers)
    headings = {}
    for marker in markers:
        source_values = [v for m, v in source_lines if m == marker]
        edition_values = [v for m, v in edition_lines if m == marker]
        if source_values != edition_values:
            headings[marker] = {"source": source_values, "edition": edition_values}
    if headings:
        record("edition book headings replace the source headings", headings=headings)
    return text


def corrected_source(entry, archives, record, mended_notes=None):
    """The entry's source text, with its corrections if it is Brenton's."""
    original = source_usfm(entry, archives)
    if entry["source"] != "brenton":
        return original
    return corrected_brenton(source_id(entry), original, record, mended_notes)


def introductions_source(archives):
    """The introduction to the Apocrypha, corrected as its front prints it."""
    source = introductions.INTRODUCTIONS["source"]
    return corrected_brenton(
        source, archives["brenton"][source], recorder(None, source)
    )


def scripture_text(entry, archives, log=None, review=None, *, links):
    # The links, by book, are required: without them the See notes they replace
    # would be restyled and printed, and the text would differ silently from the
    # build's.
    code = entry["id"]
    links = links.get(code, ())
    record = recorder(log, code)
    mended_notes = set()
    original = corrected_source(entry, archives, record, mended_notes)
    if "chapters" in entry:
        # Part of a source file that holds more than one book, numbered from 1.
        first, last = entry["chapters"]
        header, chapters = chapter_parts(original)
        require(
            0 < first <= last <= len(chapters),
            f"Manifest chapters outside the source: {code}",
        )
        selected = chapters[first - 1 : last]
        expected = header + "".join(selected)
        text = header + "".join(renumber_chapters(selected, first - 1))
        require(
            list(inventory(text)["chapters"])
            == [str(c) for c in range(1, last - first + 2)],
            f"Wrong chapter selection: {code}",
        )
        record(
            (
                "select source chapters"
                if first == 1
                else "select source chapters and relabel them"
            ),
            source_ids=[source_id(entry)],
            source_chapters=f"{first}-{last}",
            edition_chapters=f"1-{last - first + 1}",
        )
    elif code == "DAG":
        daniel_header, daniel_chapters = chapter_parts(original)
        (_, susanna), (_, bel) = (
            chapter_parts(corrected_brenton(part, archives["brenton"][part], record))
            for part in ("SUS", "BEL")
        )
        require(
            len(susanna) == len(bel) == 1 and len(daniel_chapters) == 12,
            "Daniel source boundaries changed",
        )
        expected = "".join(susanna + daniel_chapters + bel)
        susanna[0] = re.sub(
            r"^\\c 1",
            lambda m: "\\s1 SUSANNA\n\\c 0\n\\cp \u200b",
            susanna[0],
            count=1,
        )
        bel[0] = re.sub(
            r"^\\c 1",
            lambda m: "\\s1 BEL AND THE DRAGON\n\\c 13\n\\cp \u200b",
            bel[0],
            count=1,
        )
        daniel_chapters[2], song_heading = re.subn(
            r"(?=\\v 25 Then Azarias stood up, and prayed on this manner)",
            lambda m: "\\s1 THE SONG OF THE THREE CHILDREN\n\\p\n",
            daniel_chapters[2],
            count=1,
        )
        require(
            song_heading == 1, "Daniel 3 Song of the Three Children boundary changed"
        )
        text = daniel_header + "".join(susanna + daniel_chapters + bel)
        require(
            list(inventory(text)["chapters"]) == [str(i) for i in range(0, 14)],
            "Wrong chapter grouping: DAG",
        )
        record(
            "group Susanna and Bel and the Dragon with Daniel",
            source_ids=list(DANIEL_PARTS),
            chapter_labels={"SUS 1": "0", "BEL 1": "13"},
            added_section_headings=[
                "SUSANNA",
                "THE SONG OF THE THREE CHILDREN (before Daniel 3:25)",
                "BEL AND THE DRAGON",
            ],
        )
    else:
        expected = original
        text = original
    for labels, printed, opens in versification.new_chapters(code):
        first, chapter = labels[0], printed[0].chapter
        name = resolved_book_names(entry, original)["short_title"]
        opening = rf"\v {first.number} {opens}"
        require(text.count(opening) == 1, f"{name} chapter boundary changed")
        prefix, tail = text.split(opening, 1)
        # Open the chapter before the source's paragraph marker, not inside it.
        require(prefix.endswith("\\p\n"), f"{name} chapter {chapter} paragraph changed")
        prefix = prefix[: -len("\\p\n")]
        tail = f"\\c {chapter}\n\\p\n\\v 1 {opens}" + tail
        for source, target in zip(labels[1:], printed[1:]):
            tail = re.sub(
                rf"\\v {source.number}(?=\s)",
                lambda m, target=target: rf"\v {target.number}",
                tail,
                count=1,
            )
        text = prefix + tail
        # Each note in the relabelled verses, by its source and printed origin.
        origins = {}
        for source, target in zip(labels, printed):
            text, found = re.subn(
                rf"\\(fr|xo) {source.label}\b",
                lambda m, target=target: rf"\{m[1]} {target.label}",
                text,
            )
            if found:
                origins[source.label] = target.label
        # A correction names the note by its source origin, and a merged note's
        # key by its printed one, so the guard below compares them relabelled.
        for source_origin, printed_origin in origins.items():
            mended_notes = {
                re.sub(rf"^{source_origin}(?=#|$)", printed_origin, p)
                for p in mended_notes
            }
        found = inventory(text)["chapters"]
        require(
            list(found) == [str(c) for c in range(1, chapter + 1)],
            f"Wrong chapter grouping: {code}",
        )
        require(
            found[str(first.chapter)] == [str(i) for i in range(1, first.number)]
            and found[str(chapter)] == [str(v.number) for v in printed],
            f"Wrong {name} {first.chapter}-{chapter} verse labels",
        )
        record(
            "relabel verses",
            source_ids=[source_id(entry)],
            source_verses=f"{first.label}-{labels[-1].number}",
            edition_verses=f"{printed[0].label}-{printed[-1].number}",
            relabelled_note_origins=origins,
            moved_paragraph_marker=f"after the new chapter {chapter} marker",
        )
    text = rename_book(entry, original, text, record)
    require(
        passage_payload(expected) == passage_payload(text),
        f"Source wording changed: {code}",
    )
    require(
        preserved_markers(expected) == preserved_markers(text),
        f"Source notes or styling changed: {code}",
    )
    # After the source comparisons above, which the added and restyled notes
    # would fail.
    # What the edition prints, which a citation must name.
    printed = versification.edition_inventory(archives)
    books = edition.books(archives)
    if entry["source"] == "kjv":
        text = insert_marginal_notes(code, text, record, review, printed, books)
    else:
        clean, found = brenton_notes(code, text, printed)
        if found:
            read_citations(
                record,
                citations.dialect("brenton"),
                [(note.key, note.citations) for note in found],
                books,
            )
        merged = merged_notes(code, found, links, record)
        # A merged note doesn't print, so a correction to it would go unused
        # unnoticed, as an exception to it would.
        replaced = sorted(k for k in merged if k.partition(" ")[2] in mended_notes)
        require(
            not replaced, f"Brenton correction to a note a link replaces: {replaced}"
        )
        text = restyle_brenton_notes(code, clean, found, record, review, merged, books)
    text = apply_links(code, text, links, record)
    # Only a book, or a book with a section, that the introduction to the
    # Apocrypha describes; placed_paragraphs checks that each is one of Brenton's.
    if (
        code in introductions.INTRODUCTIONS["books"]
        or code in introductions.INTRODUCTIONS["sections"]
    ):
        text = introductions.with_book_note(
            code, text, introductions_source(archives), record, review
        )
        text = cited_introductions(code, text, archives, record)
    # Any caller, "*" as well as "+"; only "-" sets none.
    require(
        not re.search(r"\\[fx] (?!- )", text),
        f"Note with a caller left in the text: {code}",
    )
    # Relabelling rewrites chapter and verse markers only, so every note must
    # still name the verse that holds it.
    require(
        all(
            ref == reference
            for reference, start, end in verse_spans(text)
            for ref in re.findall(r"\\(?:fr|xo) (\S+)", text[start:end])
        ),
        f"Note reference disagrees with its verse: {code}",
    )
    return text


@dataclass
class PreparedUnit:
    """A scripture unit as the build prints it, with what preparing it recorded."""

    text: str
    transformations: list
    review: list


def prepared_scripture(archives, links):
    """Every scripture unit prepared, by id, in the manifest's order."""
    result = {}
    for unit in edition.MANIFEST["scripture"]:
        log, review = [], []
        text = scripture_text(unit, archives, log, review, links=links)
        result[unit["id"]] = PreparedUnit(text, log, review)
    return result


INTRODUCTION = re.compile(r"(\\f - \\ft )(.*?)(\\f\*)", re.S)


def cited_introductions(code, text, archives, record):
    """A book whose introduction is a footnote, with what the introduction
    cites as the edition cites it: of all the footnotes, it alone opens
    with no reference."""
    unit = introductions.INTRODUCTIONS["source"]
    tongue = citations.dialect(citations.DATA["units"][unit])
    printed = versification.edition_inventory(archives)
    books = edition.books(archives)
    first = next(iter(printed[code]))
    opening = verse_at(code, f"{first}:{printed[code][first][0]}")
    spans = verse_spans(text)
    read, used = [], []

    def cited(note):
        # A section's introduction stands at the section's first verse, which
        # is where a verse or chapter it names by number alone is.
        home = next(
            (
                verse_at(code, reference)
                for reference, start, end in spans
                if start <= note.start() < end
            ),
            opening,
        )
        decided = citations.unit_decisions(unit, citations.printable(note[2])[0], code)
        body, found = citations.rewritten(
            note[2], tongue, home, unit, printed, books, list(decided.values())
        )
        used.extend(decided)
        read.extend(found)
        return note[1] + body + note[3]

    text = INTRODUCTION.sub(cited, text)
    log_citations(record, tongue, unit, read, used, books)
    return text


def log_citations(record, tongue, key, read, used, books):
    doubled = sorted(d for d in set(used) if used.count(d) > 1)
    require(not doubled, f"Citation decisions met more than once: {doubled}")
    if read or used:
        record(
            "read citations",
            dialect=tongue.name,
            citations=[citations.logged(key, citation, books) for citation in read],
            decided=used,
        )


def cited_matter(code, text, archives, record):
    """Front or back matter with what it cites as the edition cites it,
    paragraph by paragraph.

    edition/citations.json says how each unit writes its citations, or that
    it has none, and decides the ones its grammar can't read, each by the
    words it decides, which must be the unit's once.
    """
    units = citations.DATA["units"]
    require(code in units, f"Unit whose citations nothing reads: {code}")
    if units[code] is False:
        return text
    tongue = citations.dialect(units[code])
    printed = versification.edition_inventory(archives)
    books = edition.books(archives)
    text, changes = citations.renamed(code, text, books)
    if changes:
        record("name as the edition does", names=changes)
    lines, read, used = [], [], []
    # A paragraph that names no book is of the book last cited: a correction's
    # account of it follows its citation, on a line of its own.
    standing = None
    for line in text.split("\n"):
        if not line.startswith("\\id "):
            decided = citations.unit_decisions(code, citations.printable(line)[0])
            line, found = citations.rewritten(
                line,
                tongue,
                None,
                code,
                printed,
                books,
                list(decided.values()),
                standing,
            )
            used += decided
            read += found
            for citation in found:
                if citation.items and not citation.relative:
                    *_, last = (item for run in citation.items for item in run)
                    standing = Verse(citation.book, last.chapter, last.first or 1)
        lines.append(line)
    log_citations(record, tongue, code, read, used, books)
    return "\n".join(lines)


def front_matter_text(entry, archives, log=None):
    """A translation's front matter or appendix, under the edition's names if
    any, citing as the edition cites."""
    code = entry["id"]
    record = recorder(log, code)
    original = corrected_source(entry, archives, record)
    if (entry["source"], source_id(entry)) == (
        "brenton",
        introductions.INTRODUCTIONS["source"],
    ):
        original = introductions.front_text(original, record)
    text = (
        rename_book(entry, original, original, record) if "title" in entry else original
    )
    titled = normalize_title_lines(text, FRONT_PERIOD_FREE_TITLE_MARKERS)
    titled, stripped_headings = re.subn(
        r"^(\\(?:"
        + "|".join(FRONT_PERIOD_FREE_HEADING_MARKERS)
        + r")\s+[^\n]*?)\.(\s*)$",
        r"\1\2",
        titled,
        flags=re.M,
    )
    if titled != text:
        record(
            "drop closing full stops from titles and headings",
            markers=list(
                FRONT_PERIOD_FREE_TITLE_MARKERS + FRONT_PERIOD_FREE_HEADING_MARKERS
            ),
            headings=stripped_headings,
        )
    require(
        inventory(original) == inventory(titled),
        f"Preparation changed source markup: {code}",
    )
    return cited_matter(code, titled, archives, record)


def sample_chapters(code, text, wanted):
    """The header and the wanted chapters of a book, for the typesetting sample.

    A heading set just before a chapter marker (Susanna, Bel and the Dragon)
    opens that chapter, so it is kept or dropped with it. A chapter cannot
    continue the paragraph of an omitted chapter, so its nb becomes p.
    """
    header, chapters = chapter_parts(text)
    parts = [header, *chapters]
    for i in range(len(chapters)):
        lead_in = re.search(r"(?:\\s\d?\s[^\n]*\n)+\Z", parts[i])
        if lead_in:
            parts[i] = parts[i][: lead_in.start()]
            parts[i + 1] = lead_in[0] + parts[i + 1]
    kept = [parts[0]]
    previous_kept = True
    for part in parts[1:]:
        selected = int(re.search(r"\\c (\d+)", part)[1]) in wanted
        if selected:
            if not previous_kept:
                part = re.sub(r"(\\c \d+\s+)\\nb\b", r"\1\\p", part, count=1)
            kept.append(part)
        previous_kept = selected
    require(
        len(kept) - 1 == len(set(wanted)),
        f"Sample chapters missing from {code}: {wanted}",
    )
    return "".join(kept)
