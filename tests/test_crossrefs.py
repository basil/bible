"""Cross-reference merges preserve the surviving Brenton notes."""

import pytest

from bible import crossrefs, notes, paths, quotations, versification
from bible import review
from bible.checks import CheckFailed
from bible.crossrefs import (
    LINK,
    LINK_OPERATION,
    MERGE_OPERATION,
    _link_usfm,
    apply_links,
    bare,
    cited_verses,
    planned_links,
)
from bible.edition import scripture_unit as unit
from bible.versification import mapped_passages
from bible.files import read_json
from bible.prepare import recorder, scripture_text
from bible.references import Books, parse_passage, parse_verse

NAMES = Books({"MAT": "Matthew", "ISA": "Isaiah"})
TABLE_CODES = {
    "A": "A.s",
    "B": "B.s",
    "C": "C.I.r",
    "D": "D.s.I.r",
    "E": "E.I.r",
}


def brenton_link(origin, target, display, passage=None, cls="D"):
    """A Brenton verse's link to one New Testament passage."""
    code = TABLE_CODES[cls]
    return {
        "origin": parse_verse(origin),
        "passages": [parse_passage(passage or origin)],
        "targets": [parse_passage(target)],
        "target_display": display,
        "class": cls,
        "table_code": code,
        "gloss": crossrefs.gloss(cls, code),
        "row_ids": ["Q-test"],
    }


def isaiah_link(origin="ISA 1:9"):
    return brenton_link(origin, "ROM 9:29", "Romans 9:29")


def row(id, nt, ot, cls="A"):
    return {
        "id": id,
        "nt": [parse_passage(nt)],
        "ot": [parse_passage(ot)],
        "class": cls,
        "table_code": TABLE_CODES[cls],
    }


def unlinked(code, archives):
    """The book as prepared without any links, to compare a linked one against."""
    return scripture_text(unit(code), archives, links={})


def written(references):
    """References as the edition's files write them."""
    return [str(reference) for reference in references]


def verse(text, number):
    return text.split(rf"\v {number} ", 1)[1].split(rf"\v {number + 1} ", 1)[0]


def test_matching_brenton_note_becomes_classified_link(archives):
    linked = scripture_text(unit("ISA"), archives, links={"ISA": [isaiah_link()]})
    before, after = verse(unlinked("ISA", archives), 9), verse(linked, 9)
    note = r"\f - \fr 1:9 \ft See \xt Romans 9:29\f*"
    marker = r"\x - \xo 1:9 \xt Romans 9:29 \xta (LXX against Heb.)\x*"
    assert note in before and note not in after
    assert marker in after and len(LINK.findall(after)) == 1
    # The link abuts the verse's first word, as a note there does.
    assert marker + "And if" in after
    assert after.replace(marker, "").strip() == before.replace(note, "").strip()


def test_unmatched_note_survives_and_missing_verse_is_rejected(archives):
    isaiah = unlinked("ISA", archives)
    note = r"\f - \fr 1:25 \fq completely: \ft Gr. \fqa to pureness\f*"
    assert note in isaiah
    linked = scripture_text(unit("ISA"), archives, links={"ISA": [isaiah_link()]})
    assert note in linked
    with pytest.raises(CheckFailed, match="Quotation verse missing"):
        apply_links("ISA", isaiah, [isaiah_link("ISA 999:1")], recorder(None, "ISA"))
    # A link stands only at its passage's first verse, but every verse must print.
    beyond = {**isaiah_link("ISA 1:31"), "passages": [parse_passage("ISA 1:31-32")]}
    with pytest.raises(CheckFailed, match="Quotation verse missing"):
        apply_links("ISA", isaiah, [beyond], recorder(None, "ISA"))


def test_merged_note_cannot_keep_a_note_exception(archives, patched):
    patched(notes, "BRENTON_NOTES")["notes"]["ISA 1:9"] = {"lemma": "x", "why": "x"}
    with pytest.raises(
        CheckFailed, match="for a note a link replaces: \\['ISA 1:9'\\]"
    ):
        scripture_text(unit("ISA"), archives, links={"ISA": [isaiah_link()]})


def test_merged_note_cannot_keep_a_correction(archives, patched):
    patched(notes, "BRENTON_NOTES")["corrections"]["ISA 1:9"] = {
        "from": r"\xt Rom. 9. 29.",
        "to": r"\xt Rom. 9. 29",
        "why": "x",
    }
    with pytest.raises(
        CheckFailed, match=r"correction to a note a link replaces: \['ISA 1:9'\]"
    ):
        scripture_text(unit("ISA"), archives, links={"ISA": [isaiah_link()]})


def test_merged_note_cannot_keep_a_correction_under_its_source_label(archives, patched):
    # The correction names Malachias 3:23, the note's source origin, which the
    # edition prints as 4:5.
    patched(notes, "BRENTON_NOTES")["corrections"]["MAL 3:23"] = {
        "from": r"\xt Luke 1. 17.",
        "to": r"\xt Luke 1. 17",
        "why": "x",
    }
    link = brenton_link("MAL 4:5", "LUK 1:17", "Luke 1:17")
    with pytest.raises(
        CheckFailed, match=r"correction to a note a link replaces: \['MAL 4:5'\]"
    ):
        scripture_text(unit("MAL"), archives, links={"MAL": [link]})


def test_merged_note_is_never_restyled(archives, monkeypatch):
    # A note a link replaces is merged from its source, so restyling, and any
    # exception it would need, never reaches it.
    note_body = notes.note_body

    def refusing(pieces, override, key, source):
        assert key != "ISA 1:9", "restyled a merged note"
        return note_body(pieces, override, key, source)

    monkeypatch.setattr(notes, "note_body", refusing)
    entries = []
    scripture_text(
        unit("ISA"), archives, review=entries, links={"ISA": [isaiah_link()]}
    )
    assert "ISA 1:9" not in {entry["key"] for entry in entries}


def test_notes_review_leaves_out_merged_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "BUILD_DIR", tmp_path)
    review.notes_review()
    keys = {entry["key"] for entry in read_json(tmp_path / "notes-review.json")}
    # Genesis 1:27's See note is merged into its link; 1:24's note survives.
    assert "GEN 1:27" not in keys and "GEN 1:24" in keys


def test_malformed_link_is_rejected_by_link_parser():
    assert not LINK.fullmatch(r"\x - \xo 1:9 \xt Romans 9:29 \xta (LXX)\x*")
    assert not LINK.fullmatch(
        r"\x - \xo 1:9 \xta (LXX against Heb.) \xt Romans 9:29\x*"
    )


@pytest.mark.parametrize(
    "code", ["A.s", "B.s", "C.I.r", "C.II.r.o", "D.s.II.r.o", "E.I.r"]
)
def test_every_printed_outcome_parses(code):
    cls = code[0]
    link = {**isaiah_link(), "class": cls, "gloss": crossrefs.gloss(cls, code)}
    match = LINK.fullmatch(_link_usfm(link))
    assert match is not None
    assert (*match.groups()[:2], match[3] or "") == (
        "1:9",
        "Romans 9:29",
        link["gloss"] or "",
    )


def test_scope_glosses():
    assert crossrefs.gloss("C", "C.I.r") == crossrefs.gloss("A", "A.s")
    assert crossrefs.gloss("C", "C.II.r.o") is None
    assert crossrefs.gloss("C", "C.III.a.2.a") is None
    assert crossrefs.gloss("E", "E.I.r") is None
    assert crossrefs.gloss("D", "D.s.II.r.o") == "LXX against Heb."


def test_bare_link_parses_but_unknown_gloss_does_not():
    assert LINK.findall(r"\x - \xo 1:9 \xt Romans 9:29\x*") == [
        ("1:9", "Romans 9:29", "")
    ]
    assert not LINK.fullmatch(r"\x - \xo 1:9 \xt Romans 9:29 \xta (unknown)\x*")


def test_glossed_and_bare_links_round_trip(archives):
    original = unlinked("ISA", archives)
    bare = {**isaiah_link(), "target_display": "Matthew 4:6", "gloss": None}
    linked = apply_links("ISA", original, [isaiah_link(), bare], recorder(None, "ISA"))
    assert LINK.sub("", linked) == original


def test_a_target_with_a_parenthesis_is_refused():
    with pytest.raises(CheckFailed, match="Malformed link target"):
        _link_usfm({**isaiah_link(), "target_display": "Romans 9:29 (x"})


def test_a_quotation_links_once_at_the_first_verse_of_each_passage(links):
    [mark] = [link for link in links["MRK"] if "Q054" in link["row_ids"]]
    [deuteronomy] = [link for link in links["DEU"] if "Q054" in link["row_ids"]]
    assert str(mark["origin"]) == "MRK 12:29"
    assert written(mark["passages"]) == ["MRK 12:29-30"]
    assert str(deuteronomy["origin"]) == "DEU 6:4"
    assert written(deuteronomy["passages"]) == ["DEU 6:4-5"]
    assert mark["target_display"] == "Deuteronomy 6:4–5"
    assert deuteronomy["target_display"] == "Mark 12:29–30"
    assert mark["class"] == deuteronomy["class"] == "B"
    assert _link_usfm(mark).endswith(
        r"\xt Deuteronomy 6:4–5 \xta (Heb. against LXX)\x*"
    )
    # Hebrews 3:7-11 quotes Psalm 94:8-11 in one link each way.
    for code, origin in (("HEB", "HEB 3:7"), ("PSA", "PSA 94:8")):
        assert written(
            link["origin"] for link in links[code] if "Q252" in link["row_ids"]
        ) == [origin]


def test_shared_origin_uses_manifest_book_order(links):
    assert [
        link["target_display"].split()[0]
        for link in links["ISA"]
        if str(link["origin"]) == "ISA 40:3"
    ] == ["Matthew", "Mark", "Luke", "John"]


def test_real_link_gloss_counts(links):
    from collections import Counter

    counts = Counter(link["gloss"] for book in links.values() for link in book)
    assert counts == {
        "Heb. and LXX": 257,
        "Heb. against LXX": 20,
        "LXX against Heb.": 72,
        None: 226,
    }


def test_inserted_link_cannot_change_scripture_wording(monkeypatch, archives):
    original = crossrefs._link_usfm
    monkeypatch.setattr(
        crossrefs, "_link_usfm", lambda item: original(item) + " altered"
    )
    with pytest.raises(CheckFailed, match="Scripture wording or notes changed"):
        apply_links(
            "ISA", unlinked("ISA", archives), [isaiah_link()], recorder(None, "ISA")
        )


def test_conflicting_classes_need_an_editorial_resolution(patched):
    patched(quotations, "DECISIONS")["class_conflicts"] = []
    rows = [row("Q-a", "MAT 1:1", "ISA 1:1"), row("Q-b", "MAT 1:1", "ISA 1:1", "D")]
    with pytest.raises(CheckFailed, match="Conflicting glosses"):
        planned_links(rows, NAMES)


def test_equal_printed_glosses_do_not_conflict(patched):
    patched(quotations, "DECISIONS")["class_conflicts"] = []
    rows = [
        row("Q-a", "MAT 1:1", "ISA 1:1"),
        # Its links name other ranges, so none prints the same as Q-a's.
        row("Q-c", "MAT 1:1-2", "ISA 1:1-2", "C"),
    ]
    links = planned_links(rows, NAMES)
    assert {link["gloss"] for link in links["MAT"]} == {"Heb. and LXX"}


def test_overlapping_passages_with_conflicting_classes_need_a_decision(patched):
    patched(quotations, "DECISIONS")["class_conflicts"] = []
    # No two links display the same range, but both rows join MAT 1:2 and ISA 1:2.
    rows = [row("Q-a", "MAT 1:1-2", "ISA 1:1-2"), row("Q-b", "MAT 1:2", "ISA 1:2", "D")]
    with pytest.raises(CheckFailed, match="Conflicting glosses"):
        planned_links(rows, NAMES)


def test_identical_links_at_one_verse_are_refused(patched):
    patched(quotations, "DECISIONS")["class_conflicts"] = []
    rows = [row("Q-a", "MAT 1:1", "ISA 1:1"), row("Q-c", "MAT 1:1", "ISA 1:1", "C")]
    # A and C.I print alike, so the two would print the same link twice.
    with pytest.raises(CheckFailed, match="Identical quotation links at one verse"):
        planned_links(rows, NAMES)


def test_conflict_decision_covers_every_contributor_in_any_order(patched):
    rows = [
        row("Q-A0", "MAT 1:1", "ISA 1:1"),
        row("Q-D1", "MAT 1:1", "ISA 1:1", "D"),
        # Joins the same verses, but its links name other ranges.
        row("Q-A2", "MAT 1:1-2", "ISA 1:1-2"),
    ]
    patched(quotations, "DECISIONS")["class_conflicts"] = [
        {"rows": [r["id"] for r in reversed(rows)], "why": "x"}
    ]
    links = planned_links(rows, NAMES)
    assert sorted(link["class"] for link in links["MAT"]) == ["A", "A", "D"]


def test_passage_mapped_across_chapters_prints_as_ranges(patched):
    exceptions = patched(versification, "EXCEPTIONS")
    exceptions.clear()
    exceptions.update(
        {
            "ISA 9:1": {"target": "ISA 8:23", "why": "x"},
            "ISA 9:2": {"target": "ISA 9:1", "why": "x"},
        }
    )
    assert written(mapped_passages(parse_passage("ISA 9:1-3"))) == [
        "ISA 8:23",
        "ISA 9:1",
        "ISA 9:3",
    ]
    assert written(mapped_passages(parse_passage("ISA 9:2-4"))) == [
        "ISA 9:1",
        "ISA 9:3-4",
    ]
    patched(quotations, "DECISIONS")["class_conflicts"] = []
    links = planned_links([row("Q-a", "MAT 4:15", "ISA 9:1-2", "E")], NAMES)
    assert links["MAT"][0]["target_display"] == "Isaiah 8:23; 9:1"
    assert set(written(link["origin"] for link in links["ISA"])) == {
        "ISA 8:23",
        "ISA 9:1",
    }


def note(body, archives, kind="f"):
    """A note of Isaias 1:9 as eBible would have it, read."""
    origin = "fr" if kind == "f" else "xo"
    text = (
        "\\c 1\n\\p\n\\v 9 And if "
        + f"\\{kind} + \\{origin} 1:9 {body}\\{kind}*"
        + "the Lord.\n"
    )
    inventory = versification.edition_inventory(archives)
    _, [found] = notes.brenton_notes("ISA", text, inventory)
    return found


def test_only_a_bare_see_note_can_be_merged_whole(archives):
    assert bare(note(r"\xt Rom. 9. 29.", archives, "x"))
    several = note(r"\ft See \xt Heb. 2. 6-9; Rom. 4. 7,8.", archives)
    assert bare(several)
    assert [written(citation.verses) for citation in several.citations] == [
        ["HEB 2:6", "HEB 2:7", "HEB 2:8", "HEB 2:9"],
        ["ROM 4:7", "ROM 4:8"],
    ]
    assert not bare(note(r"\ft Gr. \fqa seed\ft ; see \xt Rom. 9. 29", archives))
    assert not bare(note(r"\ft See \xt Mat. 12. 18, \ft etc.", archives))
    assert not bare(note(r"\ft Gr. \fqa seed", archives))


def test_every_citation_of_a_note_is_read(archives):
    source = r"\xt Rom. 10. 15. \ft See also \xt Joel 2. 2.,\ft the morning"
    assert written(cited_verses(note(source, archives))) == ["ROM 10:15", "JOL 2:2"]
    cited = cited_verses(note(r"\ft See \xt Mat. 12. 18, \ft etc.", archives))
    assert written(cited) == ["MAT 12:18"]
    # One that eBible doesn't mark is read as well.
    assert written(cited_verses(note(r"\ft See 1 Cor 2. 16.", archives))) == [
        "1CO 2:16"
    ]
    # A chapter names no verse.
    assert cited_verses(note(r"\ft See \xt Gen. 43.", archives)) is None


def test_a_citation_that_cannot_be_read_is_refused(archives):
    with pytest.raises(CheckFailed, match=r"can't be read: ISA 1:9 \(1. 1\)"):
        note(r"\ft See \xt Nowhere 1. 1", archives)
    # Nor is a verse the edition doesn't print, however well it is written.
    with pytest.raises(CheckFailed, match=r"doesn't print: ISA 1:9"):
        note(r"\ft See \xt Heb. 2. 6-99", archives)
    # A run of dashes is no range, and is refused rather than misread.
    with pytest.raises(CheckFailed, match=r"can't be read: ISA 1:9"):
        note(r"\ft See \xt Heb. 2. 6-9-11", archives)


def test_a_glossed_note_citing_a_link_needs_a_decision(archives, patched):
    # Psalm 2:9's note glosses "rule" before citing Rev. 2. 27, which the link
    # names; merging it would lose the gloss, so it can't merge unreviewed.
    psalm_2 = brenton_link("PSA 2:9", "REV 2:27", "Revelation 2:27", cls="D")
    decisions = patched(quotations, "DECISIONS")["note_merges"]
    decisions.clear()
    with pytest.raises(CheckFailed, match="needs a merge decision: PSA 2:9"):
        scripture_text(unit("PSA"), archives, links={"PSA": [psalm_2]})
    decisions["PSA 2:9"] = {"action": "preserve", "why": "x"}
    linked = scripture_text(unit("PSA"), archives, links={"PSA": [psalm_2]})
    assert r"\xt Revelation 2:27" in linked


def test_a_note_that_names_no_verse_can_only_be_preserved(
    archives, with_source, patched
):
    damaged = with_source(
        "brenton",
        "ISA",
        lambda t: t.replace(r"\xt Rom. 9. 29", r"\xt Rom. 9. 29; Gen. 43", 1),
    )
    decisions = patched(quotations, "DECISIONS")["note_merges"]
    decisions.clear()
    with pytest.raises(CheckFailed, match="needs a merge decision: ISA 1:9"):
        scripture_text(unit("ISA"), damaged, links={"ISA": [isaiah_link()]})
    decisions["ISA 1:9"] = {"action": "merge", "why": "x"}
    with pytest.raises(CheckFailed, match="names no verse: ISA 1:9"):
        scripture_text(unit("ISA"), damaged, links={"ISA": [isaiah_link()]})


def test_a_bare_note_of_a_chapter_needs_a_decision(archives, with_source, patched):
    # "See Gen. 43" is bare, but names no verse for a link to name.
    damaged = with_source(
        "brenton",
        "ISA",
        lambda t: t.replace(r"\xt Rom. 9. 29", r"\xt Gen. 43", 1),
    )
    patched(quotations, "DECISIONS")["note_merges"] = {}
    with pytest.raises(CheckFailed, match="needs a merge decision: ISA 1:9"):
        scripture_text(unit("ISA"), damaged, links={"ISA": [isaiah_link()]})


def psalm_8_link():
    return brenton_link("PSA 8:5", "HEB 2:6-8", "Hebrews 2:6–8", "PSA 8:5-7")


def test_range_note_within_the_links_is_merged(archives, patched):
    # Brenton's "See Rom. 11. 9,10" at Psalm 68:23 lists both linked verses.
    psalm_68 = brenton_link(
        "PSA 68:23", "ROM 11:9-10", "Romans 11:9–10", "PSA 68:23-24"
    )
    patched(quotations, "DECISIONS")["note_merges"] = {}
    note = r"\f - \fr 68:23 \ft See \xt Romans 11:9, 10\f*"
    assert note in unlinked("PSA", archives)
    log = []
    linked = scripture_text(unit("PSA"), archives, log, links={"PSA": [psalm_68]})
    assert note not in linked
    [merge] = [e for e in log if e["operation"] == MERGE_OPERATION][0]["merges"]
    assert merge["verses"] == ["ROM 11:9", "ROM 11:10"] and merge["dropped"] == []


def test_range_note_beyond_the_links_needs_a_decision_naming_its_drops(
    archives, patched
):
    decisions = patched(quotations, "DECISIONS")["note_merges"]
    decisions.clear()
    with pytest.raises(CheckFailed, match="needs a merge decision: PSA 8:5"):
        scripture_text(unit("PSA"), archives, links={"PSA": [psalm_8_link()]})
    decisions["PSA 8:5"] = {"action": "merge", "why": "x"}
    with pytest.raises(CheckFailed, match="exactly the verses it drops: PSA 8:5"):
        scripture_text(unit("PSA"), archives, links={"PSA": [psalm_8_link()]})
    decisions["PSA 8:5"]["drops"] = ["HEB 2:9"]
    linked = scripture_text(unit("PSA"), archives, links={"PSA": [psalm_8_link()]})
    assert r"\ft See \xt Heb. 2. 6-9" not in linked


def test_merge_decision_cannot_drop_an_unlinked_reference(archives, patched):
    deuteronomy = brenton_link("DEU 5:16", "MAT 15:4", "Matthew 15:4", cls="A")
    patched(quotations, "DECISIONS")["note_merges"] = {
        "DEU 5:16": {"action": "merge", "why": "x"}
    }
    with pytest.raises(CheckFailed, match="exactly the verses it drops: DEU 5:16"):
        scripture_text(unit("DEU"), archives, links={"DEU": [deuteronomy]})


def test_every_link_lands_and_every_merge_decision_is_used(prepared, links):
    log = [e for unit in prepared.values() for e in unit.transformations]
    applied = [e for e in log if e["operation"] == LINK_OPERATION]
    merged = [e for e in log if e["operation"] == MERGE_OPERATION]
    assert sum(len(e["links"]) for e in applied) == sum(map(len, links.values()))
    assert all(
        {"class", "table_code", "gloss", "row_ids"} <= entry.keys()
        for operation in applied
        for entry in operation["links"]
    )
    assert {key for e in merged for key in e["merge_decisions"]} == set(
        quotations.DECISIONS["note_merges"]
    )
