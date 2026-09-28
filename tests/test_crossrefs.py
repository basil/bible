"""Cross-reference merges preserve the surviving Brenton notes."""

import pytest

from bible import crossrefs, notes, paths, quotations, versemap
from bible import review
from bible.checks import CheckFailed
from bible.crossrefs import (
    LINK,
    LINK_OPERATION,
    MERGE_OPERATION,
    _link_usfm,
    _note_references,
    apply_links,
    planned_links,
)
from bible.edition import scripture_unit as unit
from bible.versemap import mapped_passages
from bible.files import read_json
from bible.prepare import recorder, scripture_text

NAMES = {"MAT": "Matthew", "ISA": "Isaiah"}


def brenton_link(origin, target, display, passage=None, cls="D"):
    """A Brenton verse's link to one New Testament passage."""
    return {
        "origin": origin,
        "passages": [passage or origin],
        "targets": [target],
        "target_display": display,
        "class": cls,
        "row_ids": ["Q-test"],
    }


def isaiah_link(origin="ISA 1:9"):
    return brenton_link(origin, "ROM 9:29", "Romans 9:29")


def row(id, nt, ot, cls="A"):
    return {"id": id, "nt": [nt], "ot": [ot], "class": cls}


def unlinked(code, archives):
    """The book as prepared without any links, to compare a linked one against."""
    return scripture_text(unit(code), archives, links={})


def verse(text, number):
    return text.split(rf"\v {number} ", 1)[1].split(rf"\v {number + 1} ", 1)[0]


def test_matching_brenton_note_becomes_classified_link(archives):
    linked = scripture_text(unit("ISA"), archives, links={"ISA": [isaiah_link()]})
    before, after = verse(unlinked("ISA", archives), 9), verse(linked, 9)
    note = r"\f - \fr 1:9 \ft See \xt Rom. 9. 29\f*"
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
    beyond = {**isaiah_link("ISA 1:31"), "passages": ["ISA 1:31-32"]}
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
        "to": r"\xt Rom. 9.  29.",
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
        "to": r"\xt Luke 1.  17.",
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


@pytest.mark.parametrize("cls", sorted(crossrefs.CLASS_GLOSSES))
def test_every_class_prints_a_link_the_parser_reads(cls):
    link = {**isaiah_link(), "class": cls}
    match = LINK.fullmatch(_link_usfm(link))
    assert match is not None
    assert match.groups() == ("1:9", "Romans 9:29", crossrefs.CLASS_GLOSSES[cls])


def test_classes_that_differ_in_the_hebrew_and_septuagint_are_glossed_apart():
    glosses = crossrefs.CLASS_GLOSSES
    assert len(set(glosses.values())) == len(glosses)
    assert glosses["C"] != glosses["E"]


def test_a_gloss_breaks_before_its_relation_but_not_after():
    for gloss in crossrefs.CLASS_GLOSSES.values():
        for relation in "=≠":
            if relation in gloss:
                assert f" {relation}\u00a0" in gloss, gloss


def test_a_target_with_a_parenthesis_is_refused():
    with pytest.raises(CheckFailed, match="Malformed link target"):
        _link_usfm({**isaiah_link(), "target_display": "Romans 9:29 (x"})


def test_a_quotation_links_once_at_the_first_verse_of_each_passage(links):
    [mark] = [link for link in links["MRK"] if "Q054" in link["row_ids"]]
    [deuteronomy] = [link for link in links["DEU"] if "Q054" in link["row_ids"]]
    assert (mark["origin"], mark["passages"]) == ("MRK 12:29", ["MRK 12:29-30"])
    assert (deuteronomy["origin"], deuteronomy["passages"]) == (
        "DEU 6:4",
        ["DEU 6:4-5"],
    )
    assert mark["target_display"] == "Deuteronomy 6:4–5"
    assert deuteronomy["target_display"] == "Mark 12:29–30"
    assert mark["class"] == deuteronomy["class"] == "B"
    assert _link_usfm(mark).endswith(
        r"\xt Deuteronomy 6:4–5 \xta (Heb. against LXX)\x*"
    )
    # Hebrews 3:7-11 quotes Psalm 94:8-11 in one link each way.
    for code, origin in (("HEB", "HEB 3:7"), ("PSA", "PSA 94:8")):
        assert [
            link["origin"] for link in links[code] if "Q252" in link["row_ids"]
        ] == [origin]


def test_inserted_link_cannot_change_scripture_wording(monkeypatch, archives):
    original = crossrefs._link_usfm
    monkeypatch.setattr(
        crossrefs, "_link_usfm", lambda item: original(item) + " altered"
    )
    with pytest.raises(CheckFailed, match="Scripture wording or notes changed"):
        apply_links(
            "ISA", unlinked("ISA", archives), [isaiah_link()], recorder(None, "ISA")
        )


def test_identical_visible_links_coalesce_without_losing_source_ids(patched):
    patched(quotations, "DECISIONS")["class_conflicts"] = []
    rows = [row("Q-a", "MAT 1:1", "ISA 1:1"), row("Q-b", "MAT 1:1", "ISA 1:1")]
    links = planned_links(rows, NAMES)
    assert sum(map(len, links.values())) == 2
    assert all(
        link["row_ids"] == ["Q-a", "Q-b"]
        for values in links.values()
        for link in values
    )


def test_coalesced_link_keeps_every_passage_it_stands_for(patched):
    patched(quotations, "DECISIONS")["class_conflicts"] = []
    rows = [row("Q-a", "MAT 1:1", "ISA 1:1-2"), row("Q-b", "MAT 1:1", "ISA 1:1")]
    [coalesced] = planned_links(rows, NAMES)["ISA"]
    assert coalesced["origin"] == "ISA 1:1"
    assert coalesced["passages"] == ["ISA 1:1-2", "ISA 1:1"]


def test_conflicting_classes_need_an_editorial_resolution(patched):
    patched(quotations, "DECISIONS")["class_conflicts"] = []
    rows = [row("Q-a", "MAT 1:1", "ISA 1:1"), row("Q-b", "MAT 1:1", "ISA 1:1", "D")]
    with pytest.raises(CheckFailed, match="Conflicting classes"):
        planned_links(rows, NAMES)


def test_overlapping_passages_with_conflicting_classes_need_a_decision(patched):
    patched(quotations, "DECISIONS")["class_conflicts"] = []
    # No two links display the same range, but both rows join MAT 1:2 and ISA 1:2.
    rows = [row("Q-a", "MAT 1:1-2", "ISA 1:1-2"), row("Q-b", "MAT 1:2", "ISA 1:2", "D")]
    with pytest.raises(CheckFailed, match="Conflicting classes"):
        planned_links(rows, NAMES)


def test_conflict_decision_covers_every_contributor_in_any_order(patched):
    rows = [row(f"Q-{c}{i}", "MAT 1:1", "ISA 1:1", c) for i, c in enumerate("ADA")]
    patched(quotations, "DECISIONS")["class_conflicts"] = [
        {"rows": [r["id"] for r in reversed(rows)], "why": "x"}
    ]
    links = planned_links(rows, NAMES)
    assert sorted(link["class"] for link in links["MAT"]) == ["A", "D"]


def test_passage_mapped_across_chapters_prints_as_ranges(patched):
    exceptions = patched(versemap, "EXCEPTIONS")
    exceptions.clear()
    exceptions.update(
        {
            "ISA 9:1": {"target": "ISA 8:23", "why": "x"},
            "ISA 9:2": {"target": "ISA 9:1", "why": "x"},
        }
    )
    assert mapped_passages("ISA 9:1-3") == ["ISA 8:23", "ISA 9:1", "ISA 9:3"]
    assert mapped_passages("ISA 9:2-4") == ["ISA 9:1", "ISA 9:3-4"]
    patched(quotations, "DECISIONS")["class_conflicts"] = []
    links = planned_links([row("Q-a", "MAT 4:15", "ISA 9:1-2", "E")], NAMES)
    assert links["MAT"][0]["target_display"] == "Isaiah 8:23; Isaiah 9:1"
    assert {link["origin"] for link in links["ISA"]} == {"ISA 8:23", "ISA 9:1"}


def test_only_a_bare_see_note_is_read_as_references(archives):
    aliases = crossrefs._aliases(archives)
    assert _note_references(r"See \xt Rom. 9. 29.", aliases) == [["ROM 9:29"]]
    assert _note_references(r"\ft See \xt Heb. 2. 6-9; Rom. 4. 7,8.", aliases) == [
        ["HEB 2:6", "HEB 2:7", "HEB 2:8", "HEB 2:9"],
        ["ROM 4:7", "ROM 4:8"],
    ]
    glossed = r"\ft Gr. \fqa seed\ft ; see \xt Rom. 9. 29"
    assert _note_references(glossed, aliases) is None
    assert _note_references(r"\ft See \xt Mat. 12. 18, \ft etc.", aliases) is None
    # A run of dashes is no range, and is refused rather than misread.
    assert _note_references(r"See \xt Heb. 2. 6-9-11", aliases) is None


def test_every_reference_of_a_note_is_read(archives):
    aliases = crossrefs._aliases(archives)
    source = r"\xt Rom. 10. 15. \ft See also \xt Joel 2. 2.,\ft the morning"
    assert crossrefs._cited_verses(source, aliases) == ["ROM 10:15", "JOL 2:2"]
    assert crossrefs._cited_verses(r"\ft See \xt Mat. 12. 18, \ft etc.", aliases) == [
        "MAT 12:18"
    ]
    assert crossrefs._cited_verses(r"\ft See \xt Nowhere 1. 1", aliases) is None


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
    assert r"\xt Rev. 2. 27" in linked


def test_an_unreadable_reference_can_only_be_preserved(archives, with_source, patched):
    damaged = with_source(
        "brenton",
        "ISA",
        lambda t: t.replace(r"\xt Rom. 9. 29", r"\xt Rom. 9. 29; Q. 1. 1", 1),
    )
    decisions = patched(quotations, "DECISIONS")["note_merges"]
    decisions.clear()
    with pytest.raises(CheckFailed, match="needs a merge decision: ISA 1:9"):
        scripture_text(unit("ISA"), damaged, links={"ISA": [isaiah_link()]})
    decisions["ISA 1:9"] = {"action": "merge", "why": "x"}
    with pytest.raises(CheckFailed, match="unreadable reference: ISA 1:9"):
        scripture_text(unit("ISA"), damaged, links={"ISA": [isaiah_link()]})


def psalm_8_link():
    return brenton_link("PSA 8:5", "HEB 2:6-8", "Hebrews 2:6–8", "PSA 8:5-7")


def test_range_note_within_the_links_is_merged(archives, patched):
    # Brenton's "See Rom. 11. 9,10" at Psalm 68:23 lists both linked verses.
    psalm_68 = brenton_link(
        "PSA 68:23", "ROM 11:9-10", "Romans 11:9–10", "PSA 68:23-24"
    )
    patched(quotations, "DECISIONS")["note_merges"] = {}
    note = r"\f - \fr 68:23 \ft See \xt Rom. 11. 9,10\f*"
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
    assert {key for e in merged for key in e["merge_decisions"]} == set(
        quotations.DECISIONS["note_merges"]
    )
