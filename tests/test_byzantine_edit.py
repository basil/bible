"""Edits on real verses: seams, supplied words, structural moves and omissions."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from typing import Any

import pytest

import bible.pipeline
from bible import scripture, usj
from bible.byzantine import edit
from bible.byzantine.rows import Disposition, Edit, InstructionEdit
from bible.byzantine.stages import Context
from bible.scripture import Verse
from bible.usj import Document, Node

type EditsAt = dict[str, list[tuple[Disposition, Edit]]]


@pytest.fixture(scope="module")
def context(edition: bible.pipeline.Edition) -> Context:
    return edition.byzantine.context


@pytest.fixture(scope="module")
def edits_at(context: Context) -> EditsAt:
    found: EditsAt = {}
    for row in context["dispositions"]:
        if row.get("execution") == "applied":
            for e in row.get("edits", []):
                found.setdefault(e["ref"], []).append((row, e))
    return found


def note_text(note: Node) -> str:
    return " ".join(
        usj.text_of(n["content"]) if isinstance(n, dict) else n for n in note["content"]
    )


def field(note: Node, marker: str) -> Node:
    """The first of a note's fields with the marker."""
    return next(
        n for n in note["content"] if isinstance(n, dict) and n["marker"] == marker
    )


# Seam rules on real verses


def test_matthew_3_11_removal_takes_its_comma_and_the_supplied_with(
    kjv_text: Mapping[str, str],
    prepared_verses: Mapping[str, Verse],
    edits_at: EditsAt,
) -> None:
    assert kjv_text["MAT 3:11"].endswith("with the Holy Ghost, and with fire:")
    assert prepared_verses["MAT 3:11"].text.endswith("with the Holy Ghost:")
    ((row, e),) = edits_at["MAT 3:11"]
    assert (e["kind"], e["old"], e["new"]) == ("delete", "and with fire", "")
    assert kjv_text["MAT 3:11"][slice(*e["applied_range"])] == ", and with fire"
    assert [s["rule"] for s in e["seams"]] == [2]
    assert "\\+add with\\+add*" in usj.serialize([e["note"]])
    # "adds: and with fire" would lose the KJV's comma: the note quotes the
    # KJV's own words for a lemma that spans the gap.
    assert "Ghost: Textus Receptus: Ghost, and with fire" in " ".join(
        note_text(e["note"]).split()
    )


def test_matthew_7_14_stays_lowercase_after_the_colon_of_7_13(
    kjv_text: Mapping[str, str],
    prepared_verses: Mapping[str, Verse],
    edits_at: EditsAt,
) -> None:
    assert kjv_text["MAT 7:13"].endswith("thereat:")
    assert kjv_text["MAT 7:14"].startswith("because strait")
    assert prepared_verses["MAT 7:14"].text.startswith("how strait")
    ((row, e),) = edits_at["MAT 7:14"]
    assert (e["old"], e["rendered"]) == ("because", "how")
    assert not any(s["rule"] == 1 for s in e["seams"])


def test_luke_6_9_replaces_destroy_it_with_kill(
    kjv_text: Mapping[str, str],
    prepared_verses: Mapping[str, Verse],
    edits_at: EditsAt,
) -> None:
    assert kjv_text["LUK 6:9"].endswith("or to destroy it?")
    assert prepared_verses["LUK 6:9"].text.endswith("or to kill?")
    ((row, e),) = edits_at["LUK 6:9"]
    assert (e["kind"], e["old"], e["new"]) == ("replace", "destroy it", "kill")
    assert note_text(e["note"]).endswith("Textus Receptus:  destroy it")


def test_acts_9_5_omission_is_one_construction_with_9_6(
    prepared_verses: Mapping[str, Verse], edits_at: EditsAt
) -> None:
    # Pierpont's one row omits words in both verses; one reading takes both.
    assert (
        prepared_verses["ACT 9:5"].text
        == "And he said, Who art thou, Lord? And the Lord said, I am Jesus whom thou persecutest."
    )
    ((row, e),) = edits_at["ACT 9:5"]
    assert row["disposition"] == "witnessed"
    assert e["old"] == "it is hard for thee to kick against the pricks"
    assert e["new"] == ""


def test_acts_9_6_instruction_starts_the_verse_with_a_capital(
    prepared_verses: Mapping[str, Verse], edits_at: EditsAt
) -> None:
    assert (
        prepared_verses["ACT 9:6"].text
        == "But arise, and go into the city, and it shall be told thee what thou must do."
    )
    (deletion, omitted), (row, e) = edits_at["ACT 9:6"]
    assert deletion["disposition"] == row["disposition"] == "witnessed"
    assert omitted["kind"] == "delete"
    assert omitted["old"].startswith("And he trembling and astonished said")
    assert e["kind"] == "insert" and e["old"] == "" and e["rendered"] == "But"
    assert any(
        s["rule"] == 4 and s["from"] == "A" and s["to"] == "a" for s in e["seams"]
    )
    assert "it shall be told thee" in prepared_verses["ACT 9:6"].text


def test_revelation_22_21_has_two_edits_each_with_its_note(
    kjv_text: Mapping[str, str],
    prepared_verses: Mapping[str, Verse],
    edits_at: EditsAt,
) -> None:
    assert (
        kjv_text["REV 22:21"]
        == "The grace of our Lord Jesus Christ be with you all. Amen."
    )
    assert (
        prepared_verses["REV 22:21"].text
        == "The grace of the Lord Jesus Christ be with all the saints. Amen."
    )
    changes = sorted((e["old"], e["new"]) for _, e in edits_at["REV 22:21"])
    assert changes == [("our", "the"), ("you all", "all the saints")]
    notes = [note_text(n) for _, n in prepared_verses["REV 22:21"].notes]
    assert any("Textus Receptus:  our Lord" in n for n in notes)
    assert any("Textus Receptus:  you all" in n for n in notes)


def test_seam_keeps_exact_replacement_case() -> None:
    for text, lo, hi, new in [
        ("And he said.", 0, 3, "then"),
        ("He said. And he went.", 9, 12, "then"),
        ("When Jesus came", 5, 10, "he"),
        ("He said. because", 9, 16, "how"),
        ("because strait is the gate", 0, 7, "How"),
    ]:
        assert edit.seam(text, lo, hi, new) == (lo, hi, new, [])


def test_seam_deletion_rules_on_plain_text() -> None:
    text = "Heal the sick, cleanse the lepers, raise the dead, cast out devils:"
    lo, hi = text.index("raise"), text.index("raise") + len("raise the dead")
    start, end, new, seams = edit.seam(text, lo, hi, "")
    assert (
        text[:start] + text[end:]
        == "Heal the sick, cleanse the lepers, cast out devils:"
    )
    assert seams[0]["rule"] == 2
    text = "Go ye therefore, and teach all nations"
    lo, hi = text.index("therefore"), text.index("therefore") + len("therefore")
    start, end, *_ = edit.seam(text, lo, hi, "")
    assert text[:start] + text[end:] == "Go ye, and teach all nations"
    text = "be with you. Amen."
    lo, hi = text.index("Amen"), text.index("Amen") + 4
    start, end, *_ = edit.seam(text, lo, hi, "")
    assert text[:start] + text[end:] == "be with you."


def test_no_edit_leaves_a_doubled_space_and_every_old_is_the_source(
    kjv_text: Mapping[str, str], edits_at: EditsAt
) -> None:
    for ref, items in edits_at.items():
        for row, e in items:
            assert kjv_text[ref][slice(*e["range"])] == e["old"], row["unit"]
            assert "  " not in e["rendered"]


def test_no_edit_leaves_two_stops_together(
    context: Context,
    kjv_text: Mapping[str, str],
    prepared_verses: Mapping[str, Verse],
) -> None:
    # MAT 27:41 once read "and Pharisees., said" from Pierpont's cell period.
    doubled = re.compile(r"[.,;:!]\s?[.,;:]")
    structure = context["structure"]
    for ref, verse in prepared_verses.items():
        source = kjv_text.get(ref) or kjv_text.get(structure.kjv_ref(ref), "")
        assert set(doubled.findall(verse.text)) <= set(doubled.findall(source)), (
            ref,
            verse.text,
        )


# Supplied words


def test_supplied_content_turns_brackets_into_add_characters() -> None:
    content = edit.supplied_content("for I behold [them] as trees")
    assert usj.text_of(content) == "for I behold them as trees"
    assert "\\add them\\add*" in usj.serialize(content)
    assert edit.supplied_content("plain words") == ["plain words"]
    with pytest.raises(ValueError):
        edit.supplied_content("a [broken bracket")


def test_an_inserted_bracketed_word_is_supplied_in_the_edition(
    context: Context, prepared_verses: Mapping[str, Verse], edits_at: EditsAt
) -> None:
    inserted = [
        (row, e)
        for items in edits_at.values()
        for row, e in items
        if e["kind"] == "insert" and "[" in e["rendered"]
    ]
    assert inserted
    for row, e in inserted:
        book, address = e["ref"].split()
        assert "\\add " in usj.serialize(context["prepared"][book])
        assert "[" not in prepared_verses[e["ref"]].text


# Structural changes


def test_the_four_omitted_verses_are_absent_and_noted_on_the_verse_before(
    context: Context,
    kjv_text: Mapping[str, str],
    prepared_verses: Mapping[str, Verse],
    dispositions: Mapping[str, Disposition],
) -> None:
    omitted = context["structure"].omitted
    assert omitted == {"LUK 17:36", "ACT 8:37", "ACT 15:34", "ACT 24:7"}
    for ref in omitted:
        assert ref not in prepared_verses
        book, address = ref.split()
        chapter, number = address.split(":")
        before = f"{book} {chapter}:{int(number) - 1}"
        notes = [n for _, n in prepared_verses[before].notes]
        assert any(
            f"Textus Receptus adds verse {number}:" in note_text(n) for n in notes
        ), (ref, notes)
        # The note is keyed by the verse it stands at.
        assert f"{before} TR" in [n.get("x-key") for n in notes]
        row = dispositions[f"{ref}#1"]
        assert (
            row["execution"] == "applied"
            and row["action"] == "omit"
            and row["note_ref"] == before
        )
        assert row["old"] == kjv_text[ref]


def test_omitted_verses_are_quoted_whole_with_their_supplied_style(
    kjv_text: Mapping[str, str], dispositions: Mapping[str, Disposition]
) -> None:
    row = dispositions["LUK 17:36#1"]
    note = row["note"]
    assert note is not None
    quote = field(note, "fqa")
    assert (
        usj.text_of(quote["content"]) + row["note_scope"].get("terminal_stop", "")
        == kjv_text["LUK 17:36"]
    )
    assert "\\+add men\\+add*" in usj.serialize([note])


def test_romans_doxology_stands_at_14_24_to_26_with_a_note_at_each_end(
    context: Context, kjv_text: Mapping[str, str]
) -> None:
    document = context["prepared"]["ROM"]
    verses = scripture.verses(document)
    for source, target in [("16:25", "14:24"), ("16:26", "14:25"), ("16:27", "14:26")]:
        assert source not in verses
        # 16:27 is itself edited ("be glory through" -> "through ... to whom be the glory").
        assert (
            scripture.words_of(verses[target].text)[:3]
            == scripture.words_of(kjv_text["ROM " + source])[:3]
        )
    assert verses["14:24"].text == kjv_text["ROM 16:25"]
    assert list(verses).index("14:26") + 1 == list(verses).index("15:1")
    location = [
        note_text(n)
        for a in ("14:24", "14:25", "14:26")
        for _, n in verses[a].notes
        if "has this passage" in note_text(n)
    ]
    assert location == ["14:24  Textus Receptus has this passage at 16:25–27."]
    # Where the passage stood, the chapter keeps a note of where it went.
    assert [(n.get("x-key"), note_text(n)) for _, n in verses["16:24"].notes] == [
        (
            "ROM 16:24 TR",
            "16:24  Textus Receptus has here the verses printed at 14:24–26.",
        )
    ]
    # The moved passage is one paragraph of its own, and none is left empty.
    held = {verses[a].parts[0][0] for a in ("14:24", "14:25", "14:26")}
    assert len(held) == 1
    (block,) = held
    assert [
        item["number"]
        for item in document["content"][block]["content"]
        if usj.is_type(item, "verse")
    ] == ["24", "25", "26"]
    assert all(
        usj.text_of(b["content"]).strip()
        for b in document["content"]
        if b["type"] == "para"
    )


def test_matthew_23_13_and_14_exchange_places_with_a_note_at_each(
    context: Context,
    kjv_text: Mapping[str, str],
    prepared_verses: Mapping[str, Verse],
) -> None:
    moved = context["structure"].moved
    assert moved["MAT 23:13"] == "MAT 23:14" and moved["MAT 23:14"] == "MAT 23:13"
    assert (
        "devour widows" in kjv_text["MAT 23:14"]
        and "shut up the kingdom" in kjv_text["MAT 23:13"]
    )
    assert (
        "devour widows" in prepared_verses["MAT 23:13"].text
        and "shut up the kingdom" in prepared_verses["MAT 23:14"].text
    )
    for target, source in [("23:13", "23:14"), ("23:14", "23:13")]:
        notes = [note_text(n) for _, n in prepared_verses["MAT " + target].notes]
        assert any(
            n == f"{target}  Textus Receptus has this passage at {source}."
            for n in notes
        ), notes


def test_structural_alone_on_the_pinned_kjv(
    context: Context, kjv_text: Mapping[str, str]
) -> None:
    """The structural stage by itself: the inventory and the quoted verses."""
    rows: list[Disposition] = [
        {
            "unit": r["unit"],
            "ref": r["ref"],
            "disposition": r["disposition"],
            "action": r["action"],
            "target_ref": r["target_ref"],
            "flags": r["flags"],
            "tags": r["tags"],
        }
        for r in context["dispositions"]
        if r["disposition"] == "structural"
    ]
    before = copy.deepcopy(context["documents"])
    prepared, result = edit.structural(context["documents"], rows, context["structure"])
    assert context["documents"] == before
    assert all(r["execution"] == "applied" for r in result)
    verses = {
        f"{b} {a}": v
        for b, d in prepared.items()
        for a, v in scripture.verses(d).items()
    }
    assert len(verses) == 7953
    assert not context["structure"].omitted & set(verses)
    for row in result:
        if row["action"] == "omit":
            note = row["note"]
            assert note is not None
            quote = field(note, "fq")
            assert usj.text_of(quote["content"]) == kjv_text[row["ref"]]
    assert sum(r["note"] is not None for r in result if r["action"] == "move") == 3
    assert [r["source_note_ref"] for r in result if "source_note" in r] == ["ROM 16:24"]


def test_the_edition_has_the_full_verse_inventory(
    context: Context, prepared_verses: Mapping[str, Verse]
) -> None:
    assert len(prepared_verses) == 7953
    assert len(context["prepared"]) == 27


# Refusals


def mat_3_8_row(at: int, old: str, new: str) -> Disposition:
    """A reading replacing words at an offset of Matthew 3:8."""
    return {
        "unit": "MAT 3:8#1",
        "ref": "MAT 3:8",
        "disposition": "override",
        "action": "edit",
        "flags": [],
        "ops": [
            {
                "kind": "replace",
                "ref": "MAT 3:8",
                "range": [at, at + 6],
                "old": old,
                "new": new,
                "raw_range": True,
            }
        ],
    }


def test_an_edit_that_changes_nothing_is_refused(context: Context) -> None:
    verse = scripture.verses(context["documents"]["MAT"])["3:8"]
    at = verse.text.index("fruits")
    row = mat_3_8_row(at, "fruits", "fruits")
    prepared, rows = edit.execute(context["documents"], [row], ["MAT"])
    assert rows[0]["execution"] == "refused" and rows[0]["reasons"] == [
        "edit changes nothing"
    ]
    assert rows[0]["action"] == "refused"
    assert prepared["MAT"] == context["documents"]["MAT"]


def test_a_stale_edit_is_refused_by_name(context: Context) -> None:
    verse = scripture.verses(context["documents"]["MAT"])["3:8"]
    at = verse.text.index("fruits")
    row = mat_3_8_row(at, "fruit", "apples")
    _, rows = edit.execute(context["documents"], [row], ["MAT"])
    assert rows[0]["execution"] == "refused" and "stale edit" in rows[0]["reasons"][0]


def test_an_edit_on_an_existing_source_note_is_refused(context: Context) -> None:
    documents = copy.deepcopy(context["documents"])
    verse = scripture.verses(documents["MAT"])["3:8"]
    at = verse.text.index("fruits")
    documents["MAT"] = scripture.edited(
        documents["MAT"],
        [(verse, at, at, [usj.note("f", usj.char("ft", "Source note."), caller="+")])],
    )
    row = mat_3_8_row(at, "fruits", "fruit")
    _, rows = edit.execute(documents, [row], ["MAT"])
    assert rows[0]["reasons"] == ["existing source note on the edited words"]


def test_refused_rows_in_the_build_are_named(context: Context) -> None:
    for row in context["dispositions"]:
        if row.get("execution") == "refused":
            assert row["action"] == "refused" and row["reasons"] and "edits" not in row
            assert any(f.startswith("executor refused: ") for f in row["flags"])


def execution_fixture(text: str = "And he said. Then he went.") -> dict[str, Document]:
    return {"MAT": usj.parse("\\id MAT\n\\c 1\n\\p\n\\v 1 " + text + "\n")}


def execution_row(
    unit: str,
    start: int,
    end: int,
    old: str,
    new: str,
    *,
    ref: str = "MAT 1:1",
    disposition: str = "override",
    override: str | None = None,
    selected: dict[str, Any] | None = None,
) -> Disposition:
    row: Disposition = {
        "unit": unit,
        "ref": ref,
        "disposition": disposition,
        "action": "edit",
        "flags": [],
        "ops": [
            {
                "kind": "replace",
                "ref": ref,
                "range": [start, end],
                "old": old,
                "new": new,
                "raw_range": True,
            }
        ],
    }
    if override is not None:
        row["override"] = override
    if selected is not None:
        row["selected"] = selected
    return row


def test_a_correction_of_shared_greek_keeps_the_former_words_in_a_note(
    context: Context,
) -> None:
    # The note is about the words that change, not the whole replacement.
    for address, old, new, former in (
        ("23:42", "into thy kingdom", "in thy kingdom", "into thy kingdom"),
        ("23:15", "done unto him", "done by him", "unto him"),
    ):
        before = scripture.verses(context["documents"]["LUK"])[address]
        after = scripture.verses(context["prepared"]["LUK"])[address]
        assert after.text == before.text.replace(old, new)
        added = [n for _, n in after.notes if n not in [m for _, m in before.notes]]
        assert len(added) == 1 and added[0]["x-key"] == f"LUK {address} rendering#1"
        text = usj.text_of(added[0]["content"])
        assert (
            "Or, " in text and text.endswith(former) and "Textus Receptus" not in text
        )


def test_a_correction_beside_a_reading_takes_its_own_label() -> None:
    documents = execution_fixture()
    reading = execution_row("MAT 1:1#1", 4, 6, "he", "they")
    correction = execution_row(
        "MAT 1:1", 13, 17, "Then", "Afterward", disposition="shared"
    )
    prepared, rows = edit.execute(documents, [reading, correction], ["MAT"])
    verse = scripture.verses(prepared["MAT"])["1:1"]
    assert verse.text == "And they said. Afterward he went."
    assert rows[0]["edits"][0]["note"]["x-key"] == "MAT 1:1#1 TR#1"
    assert rows[1]["edits"][0]["note"]["x-key"] == "MAT 1:1 rendering#1"
    labels = [
        usj.text_of(n["content"]).split(" ", 1)[1].split(":")[0] for _, n in verse.notes
    ]
    assert labels == ["Textus Receptus", "Or, Then"]


def test_an_edit_of_the_supplied_marking_alone_has_no_note() -> None:
    """Words the Byzantine text now has Greek for, or no longer has, keep
    their place and lose or gain their italics: nothing to note, and the
    unit's notes are numbered without them."""
    documents = execution_fixture()
    row = execution_row("MAT 1:1#1", 4, 6, "he", "[he]")
    row["ops"].append(
        {
            "kind": "replace",
            "ref": "MAT 1:1",
            "range": [18, 20],
            "old": "he",
            "new": "they",
            "raw_range": True,
        }
    )
    prepared, rows = edit.execute(documents, [row], ["MAT"])
    verse = scripture.verses(prepared["MAT"])["1:1"]
    assert verse.text == "And he said. Then they went."
    assert "\\add he\\add*" in usj.serialize(prepared["MAT"])
    first, second = rows[0]["edits"]
    assert "note" not in first and first["old"] == first["new"] == "he"
    assert second["note"]["x-key"] == "MAT 1:1#1 TR#1"
    assert len(verse.notes) == 1


def test_a_correction_overlapping_a_reading_is_refused() -> None:
    documents = execution_fixture()
    reading = execution_row("MAT 1:1#1", 4, 6, "he", "they")
    correction = execution_row(
        "MAT 1:1", 4, 11, "he said", "he spoke", disposition="shared"
    )
    _, rows = edit.execute(documents, [reading, correction], ["MAT"])
    assert rows[1]["execution"] == "refused"
    assert rows[1]["reasons"] == ["overlapping edits"]


def test_a_correction_moves_with_its_verse(context: Context) -> None:
    text = scripture.verses(context["documents"]["ROM"])["16:25"].text
    at = text.index("to stablish you")
    correction = execution_row(
        "ROM 16:25",
        at,
        at + len("to stablish you"),
        "to stablish you",
        "to establish you",
        ref="ROM 16:25",
        disposition="shared",
    )
    move = [
        r
        for r in context["dispositions"]
        if r.get("action") == "move" and r["ref"] == "ROM 16:25"
    ]
    documents, rows = edit.execute(
        context["documents"], [*move, correction], list(context["documents"])
    )
    documents, _ = edit.structural(documents, rows[:1], context["structure"])
    assert "to establish you" in scripture.verses(documents["ROM"])["14:24"].text


@pytest.mark.parametrize("bounds", [[-1, 3], [0, 100], [7, 4]])
def test_invalid_raw_offsets_are_refused(bounds: list[int]) -> None:
    documents = execution_fixture()
    row = execution_row("MAT 1:1#1", bounds[0], bounds[1], "And", "Then")
    prepared, result = edit.execute(documents, [row], ["MAT"])
    assert result[0]["execution"] == "refused"
    assert result[0]["reasons"] == ["invalid source offset"]
    assert prepared == documents


@pytest.mark.parametrize("bounds", [[-1, 1], [0, 100], [3, 2], [100, 100]])
def test_invalid_word_offsets_are_refused(bounds: list[int]) -> None:
    documents = execution_fixture()
    row = execution_row("MAT 1:1#1", 0, 3, "And", "Then")
    row["ops"][0].pop("raw_range")
    row["ops"][0].pop("range")
    row["ops"][0]["word_range"] = bounds
    prepared, result = edit.execute(documents, [row], ["MAT"])
    assert result[0]["execution"] == "refused"
    assert result[0]["reasons"] == ["invalid source offset"]
    assert prepared == documents


def test_a_refused_owner_takes_down_its_witnessed_construction() -> None:
    # Two owner rows execute one witnessed construction; neither half may
    # execute alone when the executor refuses the other.
    documents = execution_fixture()
    joint = {
        "source": "pierpont",
        "entry": 1,
        "joint": [{"source": "pierpont", "entry": 1}],
    }
    first = execution_row(
        "MAT 1:1#1", 0, 3, "And", "Then", disposition="witnessed", selected=joint
    )
    second = execution_row(
        "MAT 1:1#2", 18, 20, "he", "they", disposition="witnessed", selected=joint
    )
    second["ops"][0]["range"] = [0, 100]
    prepared, result = edit.execute(documents, [first, second], ["MAT"])
    assert [row["execution"] for row in result] == ["refused", "refused"]
    assert all(row["reasons"] == ["invalid source offset"] for row in result)
    assert prepared == documents


def test_unsupported_operation_is_refused_before_interpreting_offsets() -> None:
    documents = execution_fixture()
    row = execution_row("MAT 1:1#1", 0, 3, "And", "Then")
    row["ops"] = [{"kind": "unsupported", "ref": "MAT 1:1"}]
    prepared, result = edit.execute(documents, [row], ["MAT"])
    assert result[0]["reasons"] == ["operation not implemented"]
    assert prepared == documents


def test_deleting_a_lowercase_verse_initial_keeps_the_sentence_continuation() -> None:
    documents = execution_fixture("because strait is the gate")
    row = execution_row("MAT 1:1#1", 0, 7, "because", "")
    row["ops"][0]["kind"] = "delete"
    prepared, result = edit.execute(documents, [row], ["MAT"])
    assert result[0]["execution"] == "applied"
    assert scripture.verses(prepared["MAT"])["1:1"].text == "strait is the gate"


@pytest.mark.parametrize("stop", [",", ";", ":", "."])
def test_replacing_a_verse_initial_name_keeps_exact_case_across_boundaries(
    stop: str,
) -> None:
    documents = {
        "MAT": usj.parse(
            "\\id MAT\n\\c 1\n\\p\n\\v 1 During that reign"
            + stop
            + "\n\\v 2 Annas was priest.\n"
        )
    }
    row = execution_row(
        "MAT 1:2#1",
        0,
        len("Annas was priest"),
        "Annas was priest",
        "in the priesthood of Annas",
        ref="MAT 1:2",
    )
    prepared, result = edit.execute(documents, [row], ["MAT"])
    assert result[0]["execution"] == "applied"
    expected = "in"
    verse = scripture.verses(prepared["MAT"])["1:2"]
    assert verse.text == expected + " the priesthood of Annas."
    assert "Annas was priest" in note_text(verse.notes[0][1])


def test_an_override_closing_the_previous_clause_does_not_recase_the_next_verse() -> (
    None
):
    documents = {
        "MAT": usj.parse(
            "\\id MAT\n\\c 1\n\\p\n\\v 1 He said,\n\\v 2 Annas was priest.\n"
        )
    }
    row = execution_row("MAT 1:1#1", 3, 8, "said,", "spake.", override="shared")
    row["ops"].append(
        {
            "kind": "replace",
            "ref": "MAT 1:2",
            "range": [0, len("Annas was priest")],
            "old": "Annas was priest",
            "new": "in the priesthood of Annas",
            "raw_range": True,
        }
    )
    prepared, result = edit.execute(documents, [row], ["MAT"])
    assert result[0]["execution"] == "applied"
    verses = scripture.verses(prepared["MAT"])
    assert verses["1:1"].text == "He spake."
    assert verses["1:2"].text == "in the priesthood of Annas."


def test_disjoint_length_changing_edits_use_the_original_offsets() -> None:
    documents = execution_fixture()
    original = copy.deepcopy(documents)
    first = execution_row("MAT 1:1#1", 0, 3, "And", "Afterward")
    second = execution_row("MAT 1:1#2", 18, 20, "he", "they")
    prepared, result = edit.execute(documents, [first, second], ["MAT"])
    assert all(row["execution"] == "applied" for row in result)
    assert (
        scripture.verses(prepared["MAT"])["1:1"].text
        == "Afterward he said. Then they went."
    )
    assert documents == original


@pytest.mark.parametrize("raw", [False, True])
@pytest.mark.parametrize("bounds", [None, [], [0], [0, "3"], [0, 3.5]])
def test_malformed_offsets_are_refused_without_an_exception(
    raw: bool, bounds: object
) -> None:
    documents = execution_fixture()
    row = execution_row("MAT 1:1#1", 0, 3, "And", "Then", override="shared")
    op = row["ops"][0]
    op["raw_range"] = raw
    op["range" if raw else "word_range"] = bounds
    prepared, result = edit.execute(documents, [row], ["MAT"])
    assert result[0]["reasons"] == ["invalid source offset"]
    assert prepared == documents


def test_deleting_the_initial_of_a_joined_override_keeps_its_continuation() -> None:
    documents = {
        "MAT": usj.parse("\\id MAT\n\\c 1\n\\p\n\\v 1 He said.\n\\v 2 And he went.\n")
    }
    row = execution_row("MAT 1:1#1", 3, 8, "said.", "said,", override="shared")
    row["ops"].append(
        {
            "kind": "delete",
            "ref": "MAT 1:2",
            "range": [0, 3],
            "old": "And",
            "new": "",
            "raw_range": True,
        }
    )
    prepared, result = edit.execute(documents, [row], ["MAT"])
    assert result[0]["execution"] == "applied"
    verses = scripture.verses(prepared["MAT"])
    assert verses["1:1"].text == "He said,"
    assert verses["1:2"].text == "he went."


@pytest.mark.parametrize("original,expected", [("or", "if not"), ("Or", "if not")])
def test_replacing_a_question_continuation_keeps_replacement_case(
    original: str, expected: str
) -> None:
    text = "Do we begin again to commend ourselves? " + original + " need we letters?"
    at = text.index(original + " need")
    documents = {"MAT": usj.parse("\\id MAT\n\\c 1\n\\p\n\\v 1 " + text + "\n")}
    row = execution_row("MAT 1:1#1", at, at + len(original), original, "if not")
    prepared, result = edit.execute(documents, [row], ["MAT"])
    assert result[0]["execution"] == "applied"
    verse = scripture.verses(prepared["MAT"])["1:1"]
    assert verse.text == text[:at] + expected + text[at + len(original) :]
    assert original in note_text(verse.notes[0][1])


def test_deleting_a_lowercase_question_continuation_keeps_following_case() -> None:
    text = "Do we begin again? or need we letters?"
    at = text.index("or need")
    documents = {"MAT": usj.parse("\\id MAT\n\\c 1\n\\p\n\\v 1 " + text + "\n")}
    row = execution_row("MAT 1:1#1", at, at + 2, "or", "")
    prepared, result = edit.execute(documents, [row], ["MAT"])
    assert result[0]["execution"] == "applied"
    assert (
        scripture.verses(prepared["MAT"])["1:1"].text
        == "Do we begin again? need we letters?"
    )


@pytest.mark.parametrize(
    "source, old, new, expected",
    [
        ("And he said.", "And", "then", "then he said."),
        ("He has a pear.", "pear", "apple", "He has a apple."),
        ("Jesus went.", "Jesus", "he", "he went."),
        ("And he went.", "And", "", "he went."),
        ("Jesus went.", "Jesus", "Then Jesus", "Then Jesus went."),
    ],
)
def test_executor_uses_exact_wording_without_case_or_article_inference(
    source: str, old: str, new: str, expected: str
) -> None:
    documents = execution_fixture(source)
    original = copy.deepcopy(documents)
    start = source.index(old)
    row = execution_row("MAT 1:1#1", start, start + len(old), old, new)
    if not new:
        row["ops"][0]["kind"] = "delete"
    prepared, rows = edit.execute(documents, [row], ["MAT"])
    assert rows[0]["execution"] == "applied"
    assert scripture.verses(prepared["MAT"])["1:1"].text == expected
    assert documents == original
    assert all(s["rule"] in {2, 3} for e in rows[0]["edits"] for s in e["seams"])


def test_compiled_adjacent_deletions_preserve_supplied_words_and_lexical_note() -> None:
    from bible.byzantine import decide, verify

    document = usj.parse("\\id MAT\n\\c 1\n\\p\n\\v 1 And then \\add they\\add* spoke.")
    source = scripture.verses(document)["1:1"].text
    instructions: list[InstructionEdit] = [
        {
            "ref": "MAT 1:1",
            "kind": "delete",
            "word_range": [0, 1],
            "old": "And",
            "new": "",
        },
        {
            "ref": "MAT 1:1",
            "kind": "delete",
            "word_range": [1, 2],
            "old": "then",
            "new": "",
        },
    ]
    original = copy.deepcopy((document, instructions))
    ops = decide.operations(instructions, {"MAT 1:1": source}, frozenset())
    rows: list[Disposition] = [
        {"unit": "MAT 1:1#1", "ref": "MAT 1:1", "action": "edit", "ops": ops}
    ]
    prepared, executed = edit.execute({"MAT": document}, rows, ["MAT"])
    assert executed[0]["execution"] == "applied"
    assert scripture.verses(prepared["MAT"])["1:1"].text == "They spoke."
    assert (
        "".join(
            usj.text_of(n["content"])
            for n in usj.walk(prepared["MAT"]["content"])
            if n.get("marker") == "add"
        )
        == "They"
    )
    applied = executed[0]["edits"]
    assert applied[0]["kind"] == "delete" and applied[0]["old"] == "And then"
    assert usj.text_of(field(applied[0]["note"], "fq")["content"]) == "And then"
    assert verify.closure(source, applied) == "They spoke."
    assert (document, instructions) == original


@pytest.mark.parametrize(
    "bounds, old, new", [([4, 6], "th", "Th"), ([5, 6], "h", "H"), ([4, 5], "t", "X")]
)
def test_closure_rejects_case_adjustments_beyond_an_initial(
    bounds: list[int],
    old: str,
    new: str,
) -> None:
    from bible.byzantine import verify

    applied: Edit = {
        "range": [0, 3],
        "applied_range": [0, 4],
        "old": "And",
        "new": "",
        "rendered": "",
        "seams": [
            {"rule": 4, "range": bounds, "from": old, "to": new, "external": True}
        ],
    }
    with pytest.raises(
        ValueError, match="case adjustment changes more than an initial"
    ):
        verify.closure("And they spoke.", [applied])


@pytest.mark.parametrize(
    "before, after", [("[thy] men", "[These] men"), ("[these] men", "[ThesE] men")]
)
def test_closure_checks_a_replacements_compiled_initial_independently(
    before: str,
    after: str,
) -> None:
    from bible.byzantine import verify

    applied: Edit = {
        "range": [0, 3],
        "applied_range": [0, 3],
        "old": "Thy",
        "new": usj.text_of(edit.supplied_content(after)),
        "rendered": after,
        "seams": [{"rule": 4, "range": [0, 3], "from": before, "to": after}],
    }
    with pytest.raises(
        ValueError, match="case adjustment changes more than an initial"
    ):
        verify.closure("Thy people", [applied])


def test_compiled_replacement_cases_supplied_words_and_preserves_the_witness() -> None:
    from bible.byzantine import decide, verify

    documents = execution_fixture("Thy people")
    instruction: InstructionEdit = {
        "kind": "replace",
        "ref": "MAT 1:1",
        "word_range": [0, 1],
        "old": "Thy",
        "new": "[these]",
        "quoted_old": "thy",
    }
    op = decide.operation(instruction, {"MAT 1:1": "Thy people"}, frozenset())
    row: Disposition = {
        "unit": "MAT 1:1#1",
        "ref": "MAT 1:1",
        "action": "edit",
        "ops": [op],
    }
    prepared, executed = edit.execute(documents, [row], ["MAT"])
    assert executed[0]["execution"] == "applied"
    assert "\\add These\\add*" in usj.serialize(prepared["MAT"])
    assert verify.closure("Thy people", executed[0]["edits"]) == "These people"
    assert instruction["new"] == "[these]" and instruction["quoted_old"] == "thy"
