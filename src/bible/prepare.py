"""Preparing each source book as the edition prints it: selecting and
relabelling chapters, grouping Daniel, renaming books, and adding the 1611
notes, with checks that the source's wording, notes and markup survive.

Every change is logged through a recorder into build/<mode>/transformations.json.
"""

import re

from bible.checks import require
from bible.edition import (
    BOOK_NAME_MARKERS,
    DANIEL_PARTS,
    heading_lines,
    normalize_title_lines,
    resolved_book_names,
    source_id,
    source_usfm,
)
from bible.notes import insert_marginal_notes
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
# Every such heading, not just the first: OTH and BAK head book names with them.
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


def scripture_text(entry, archives, log=None):
    code = entry["id"]
    original = source_usfm(entry, archives)
    record = recorder(log, code)
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
        _, susanna = chapter_parts(archives["brenton"]["SUS"])
        _, bel = chapter_parts(archives["brenton"]["BEL"])
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
    if code == "MAL":
        require(
            text.count(r"\v 19 For, behold") == 1, "Malachias chapter boundary changed"
        )
        prefix, tail = text.split(r"\v 19 For, behold", 1)
        # Open chapter 4 before the source's paragraph marker, not inside it.
        require(prefix.endswith("\\p\n"), "Malachias chapter 4 paragraph changed")
        prefix = prefix[: -len("\\p\n")]
        tail = "\\c 4\n\\p\n\\v 1 For, behold" + tail
        for old, new in zip(range(20, 25), range(2, 7)):
            tail = re.sub(
                r"\\v " + str(old) + r"(?=\s)",
                lambda m: r"\v " + str(new),
                tail,
                count=1,
            )
        text, xo = re.subn(r"\\xo 3:23\b", lambda m: r"\xo 4:5", prefix + tail)
        require(xo == 1, "Malachias 3:23 cross-reference origin changed")
        labels = inventory(text)["chapters"]
        require(list(labels) == ["1", "2", "3", "4"], "Wrong chapter grouping: MAL")
        require(
            labels["3"] == [str(i) for i in range(1, 19)]
            and labels["4"] == [str(i) for i in range(1, 7)],
            "Wrong Malachias 3-4 verse labels",
        )
        record(
            "relabel verses",
            source_ids=[source_id(entry)],
            source_verses="3:19-24",
            edition_verses="4:1-6",
            relabelled_note_origins={"3:23": "4:5"},
            moved_paragraph_marker="after the new chapter 4 marker",
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
    if entry["source"] == "kjv":
        # After the source comparisons above, which the added notes would fail.
        text = insert_marginal_notes(code, text, record)
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


def front_matter_text(entry, archives, log=None):
    """A translation's front matter or appendix, under the edition's names if any."""
    code = entry["id"]
    original = source_usfm(entry, archives)
    record = recorder(log, code)
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
    return titled


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
