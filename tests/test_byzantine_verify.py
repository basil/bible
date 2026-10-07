"""The independent closure and the six invariants on the Orthodox Liturgical
English Bible (OLEB), read as USJ documents."""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Mapping, Sequence

import pytest

from bible import scripture, usj
from bible.byzantine import decide, stages, tags, verify
from bible.byzantine.greek import Structure
from bible.byzantine.rows import Disposition, Edit, Instruction, Unit
from bible.byzantine.stages import Context
from bible.scripture import Verse
from bible.usj import Content, Document, Node

NO_STRUCTURE = Structure({}, frozenset())


@pytest.fixture(scope="module")
def applied(byzantine: Context) -> dict[str, list[Edit]]:
    """Edits by source verse, from every applied row."""
    found: dict[str, list[Edit]] = {}
    for row in byzantine["dispositions"]:
        if row.get("execution") == "applied":
            for e in row.get("edits", []):
                found.setdefault(e["ref"], []).append(e)
    return found


def _checks(
    context: Context,
    prepared: Mapping[str, Document] | None = None,
    rows: Sequence[Disposition] | None = None,
) -> dict[str, str]:
    return verify.checks(
        context["documents"],
        context["prepared"] if prepared is None else prepared,
        context["units"],
        context["dispositions"] if rows is None else rows,
        context["structure"],
    )


def _i1(context: Context, rows: Sequence[Disposition]) -> str:
    # I1 reads only the declarations, so it is checked without the books.
    return verify.checks(
        context["documents"], {}, context["units"], rows, context["structure"]
    )["I1"]


def _note(lemma: str, alternative: str) -> Node:
    return {
        "type": "note",
        "marker": "f",
        "caller": "-",
        "category": "edition",
        "x-scope": {"kind": "replace"},
        "content": [
            usj.char("fq", lemma + ": "),
            usj.char("ft", "Textus Receptus: "),
            usj.char("fqa", alternative),
        ],
    }


def _with_verse_note(
    document: Document, ref: str, change: dict[str, Content]
) -> Document:
    """The document with the content of fields of the Textus Receptus note
    in a verse changed."""
    verse = scripture.verses(document)[ref]
    (key,) = [
        note["x-key"]
        for _, note in verse.notes
        if "Textus Receptus" in usj.text_of(note["content"])
    ]

    def changed(note: Node) -> Node:
        if note.get("x-key") != key:
            return note
        return {
            **note,
            "content": [
                (
                    {**n, "content": change[n["marker"]]}
                    if isinstance(n, dict) and n.get("marker") in change
                    else n
                )
                for n in note["content"]
            ],
        }

    return scripture.map_notes(document, changed)


def test_closure_reproduces_every_applied_verse(
    byzantine: Context,
    applied: dict[str, list[Edit]],
    kjv_text: Mapping[str, str],
    prepared_verses: dict[str, Verse],
) -> None:
    assert len(applied) > 700
    moved = byzantine["structure"].moved
    for ref, edits in applied.items():
        target = moved.get(ref, ref)
        assert verify.closure(kjv_text[ref], edits) == prepared_verses[target].text, ref


def test_closure_without_edits_is_the_source(kjv_text: Mapping[str, str]) -> None:
    assert verify.closure(kjv_text["MAT 1:1"], []) == kjv_text["MAT 1:1"]


def test_every_invariant_passes(byzantine: Context) -> None:
    assert byzantine["invariants"] == {f"I{i}": "pass" for i in range(1, 5)}


def test_the_books_hold_every_verse_and_every_relocation(
    byzantine: Context,
    kjv_text: Mapping[str, str],
    prepared_verses: dict[str, Verse],
) -> None:
    structure = byzantine["structure"]
    assert len(prepared_verses) == 7953
    assert not structure.omitted & prepared_verses.keys()
    applied = {
        row["ref"]: row["target_ref"]
        for row in byzantine["dispositions"]
        if row.get("action") == "move" and row.get("execution") == "applied"
    }
    assert applied == dict(structure.moved)
    for origin, target in structure.moved.items():
        edits = [
            edit
            for row in byzantine["dispositions"]
            if row.get("execution") == "applied"
            for edit in row.get("edits", [])
            if edit["ref"] == origin
        ]
        assert prepared_verses[target].text == verify.closure(kjv_text[origin], edits)


def test_every_unit_has_one_complete_declaration(byzantine: Context) -> None:
    rows = byzantine["dispositions"]
    assert len(rows) == len(byzantine["units"]) == 1939
    assert Counter(r["unit"] for r in rows) == Counter(
        u["id"] for u in byzantine["units"]
    )
    assert _i1(byzantine, rows) == "pass"
    for row in rows:
        assert row["tags"] and all(tag in tags.Tag for tag in row["tags"])
        if row["disposition"] == "override":
            assert row["override"] and row["why"] and row["evidence"]
        elif row["disposition"] == "witnessed":
            assert row["basis"]
        elif row["disposition"] == "conflict":
            assert row["reason"] and row["action"] == "nochange"
        elif row["disposition"] == "structural":
            assert row["target_ref"]
        else:
            # Silence and orthographic neutrality are reasons supplied by
            # the general decision rule, not additional editorial state.
            assert row["action"] == "nochange"


def test_joint_witnessed_owner_need_not_have_the_same_first_instruction() -> None:
    ref = "MAT 1:1"
    a, c, b = [f"{ref}#{n}" for n in (1, 2, 3)]
    units: list[Unit] = [
        {"id": uid, "ref": ref, "class": "substitution"} for uid in (a, c, b)
    ]
    instructions: list[Instruction] = []
    for entry, owner, offset, old, new in [
        (1, c, 2, "three", "third"),
        (2, a, 0, "one", "first"),
    ]:
        instructions.append(
            {
                "source": "pierpont",
                "entry": entry,
                "compatibility": "compatible",
                "units": [{"unit": uid} for uid in (owner, b)],
                "edits": [
                    {
                        "kind": "replace",
                        "ref": ref,
                        "word_range": [offset, offset + 1],
                        "old": old,
                        "new": new,
                        "units": [owner, b],
                    }
                ],
            }
        )
    rows = decide.decide(units, instructions, [], [], [], {}, {ref: "one two three"})
    owner_row, _, covered = rows
    assert covered["action"] == "covered" and covered["covered_by"] == a
    assert covered["basis"] == "pierpont:1" and owner_row["basis"] == "pierpont:2"
    assert verify.checks({}, {}, units, rows, NO_STRUCTURE)["I1"] == "pass"
    for bad_selection in (
        {"source": "additional", "joint": owner_row["selected"]["joint"]},
        {"source": "pierpont", "joint": [{"source": "pierpont", "entry": 999}]},
    ):
        bad = copy.deepcopy(rows)
        bad[-1]["selected"] = bad_selection
        assert verify.checks({}, {}, units, bad, NO_STRUCTURE)["I1"] != "pass"


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "duplicate",
        "unknown-disposition",
        "missing-disposition",
        "invalid-action",
        "missing-owner",
        "absent-owner",
        "self-owner",
        "wrong-owner",
        "chained-owner",
        "different-owner-decision",
    ],
)
def test_a_defective_declaration_fails_i1(byzantine: Context, defect: str) -> None:
    rows = copy.deepcopy(byzantine["dispositions"])
    quiet = next(r for r in rows if r["disposition"] == "silent")
    covered = next(r for r in rows if r["action"] == "covered")
    owner = next(r for r in rows if r["unit"] == covered["covered_by"])
    if defect == "missing":
        rows.remove(quiet)
    elif defect == "duplicate":
        rows.append(copy.deepcopy(quiet))
    elif defect == "unknown-disposition":
        quiet["disposition"] = "invented"
    elif defect == "missing-disposition":
        quiet.pop("disposition")
    elif defect == "invalid-action":
        quiet["action"] = "edit"
    elif defect == "missing-owner":
        covered.pop("covered_by")
    elif defect == "absent-owner":
        covered["covered_by"] = "missing unit"
    elif defect == "self-owner":
        covered["covered_by"] = covered["unit"]
    elif defect == "wrong-owner":
        covered["covered_by"] = quiet["unit"]
    elif defect == "chained-owner":
        owner["action"] = "covered"
        owner["covered_by"] = quiet["unit"]
    elif defect == "different-owner-decision":
        assert covered["disposition"] == "override"
        covered["override"] = "another override"
    assert _i1(byzantine, rows) != "pass", defect


def test_corrupting_old_makes_closure_raise(
    applied: dict[str, list[Edit]], kjv_text: Mapping[str, str]
) -> None:
    ref, edits = next(
        (r, e) for r, e in applied.items() if any(x["kind"] == "replace" for x in e)
    )
    stale = copy.deepcopy(edits)
    stale[0]["old"] = stale[0]["old"] + "x"
    with pytest.raises(ValueError, match="stale source offsets"):
        verify.closure(kjv_text[ref], stale)


def test_an_undeclared_change_to_the_new_words_is_caught(
    applied: dict[str, list[Edit]], kjv_text: Mapping[str, str]
) -> None:
    ref, edits = next(
        (r, e)
        for r, e in applied.items()
        if any(x["kind"] == "replace" and not x["seams"] for x in e)
    )
    bad = copy.deepcopy(edits)
    e = next(x for x in bad if x["kind"] == "replace" and not x["seams"])
    e["rendered"] = e["rendered"] + " more"
    with pytest.raises(ValueError, match="undeclared change to new words"):
        verify.closure(kjv_text[ref], bad)


def test_a_capital_seam_that_changes_wording_is_caught(
    applied: dict[str, list[Edit]], kjv_text: Mapping[str, str]
) -> None:
    ref, edits = next(
        (r, e)
        for r, e in applied.items()
        if any(
            s["rule"] == 1 and s["range"][0] == s["range"][1]
            for x in e
            for s in x["seams"]
        )
    )
    bad = copy.deepcopy(edits)
    seam = next(
        s
        for x in bad
        for s in x["seams"]
        if s["rule"] == 1 and s["range"][0] == s["range"][1]
    )
    seam["to"] = "Other words"
    with pytest.raises(ValueError, match="capital seam changes wording"):
        verify.closure(kjv_text[ref], bad)


def test_an_external_punctuation_seam_may_not_add_words() -> None:
    # The executor declares an instruction's added stop (Pierpont's
    # "(Period) + And") as an external seam beside the splice.
    def declared(to: str) -> Edit:
        return {
            "range": [0, 1],
            "applied_range": [0, 1],
            "old": "A",
            "new": "B",
            "rendered": "B",
            "seams": [
                {"range": [1, 1], "rule": 2, "external": True, "from": "", "to": to}
            ],
        }

    assert verify.closure("A and", [declared(".")]) == "B. and"
    with pytest.raises(ValueError, match="punctuation seam changes words"):
        verify.closure("A and", [declared("word")])


def test_an_unlicensed_character_in_the_books_fails_i2(byzantine: Context) -> None:
    document = byzantine["prepared"]["MAT"]
    verse = scripture.verses(document)["3:8"]
    at = verse.text.index("Bring forth therefore fruit") + len("Bring forth therefore ")
    assert verse.text[at : at + len("fruit ")] == "fruit "
    changed = scripture.rewritten(document, [(verse, at, at + 5, "fruits")])
    assert changed != document
    results = _checks(byzantine, {**byzantine["prepared"], "MAT": changed})
    assert results["I2"].startswith("MAT 3:8: unaccounted")


def test_a_changed_note_fails_i3(byzantine: Context) -> None:
    document = byzantine["prepared"]["MAT"]
    verse = scripture.verses(document)["3:8"]
    (note,) = [
        n for _, n in verse.notes if "Textus Receptus" in usj.text_of(n["content"])
    ]
    quote = usj.text_of(
        next(
            n["content"]
            for n in note["content"]
            if isinstance(n, dict) and n.get("marker") == "fqa"
        )
    )
    assert quote.startswith("fruits")
    changed = _with_verse_note(
        document, "3:8", {"fqa": [quote.replace("fruits", "fruit", 1)]}
    )
    assert changed != document
    results = _checks(byzantine, {**byzantine["prepared"], "MAT": changed})
    assert results["I3"].startswith("MAT 3:8:")
    assert results["I2"] == "pass"


def test_a_changed_omitted_verse_quotation_fails_i3(byzantine: Context) -> None:
    rows = copy.deepcopy(byzantine["dispositions"])
    row = next(r for r in rows if r.get("action") == "omit")
    row["old"] += "!"
    assert "omitted quotation differs" in _checks(byzantine, rows=rows)["I3"]


def test_a_stop_outside_the_quotation_cannot_complete_an_omitted_verse(
    byzantine: Context,
) -> None:
    rows = copy.deepcopy(byzantine["dispositions"])
    row = next(r for r in rows if r.get("action") == "omit")
    note = row.get("note")
    assert note
    quote = next(
        n for n in note["content"] if isinstance(n, dict) and n.get("marker") == "fqa"
    )
    text = usj.text_of(quote["content"])
    assert text[-1] in verify.STOPS
    quote["content"] = usj.substituted(
        quote["content"], [(len(text) - 1, len(text), "")]
    )
    row["note_scope"]["terminal_stop"] = text[-1]
    assert "omitted quotation differs" in _checks(byzantine, rows=rows)["I3"]


def test_missing_dispositions_and_books_are_named(byzantine: Context) -> None:
    results = verify.checks(
        byzantine["documents"],
        {},
        [*byzantine["units"], {"id": "extra"}],
        byzantine["dispositions"],
        byzantine["structure"],
    )
    assert results["I1"] == "unit coverage differs"
    assert results["I4"] == "prepared book inventory differs"
    assert set(results) == {f"I{i}" for i in range(1, 5)}


def test_a_missing_omission_fails_i4(byzantine: Context) -> None:
    rows = [r for r in byzantine["dispositions"] if r["unit"] != "LUK 17:36#1"]
    units = [u for u in byzantine["units"] if u["id"] != "LUK 17:36#1"]
    results = verify.checks(
        byzantine["documents"],
        byzantine["prepared"],
        units,
        rows,
        byzantine["structure"],
    )
    assert results["I4"].startswith("LUK:")


def test_a_missing_book_fails_i4(byzantine: Context) -> None:
    prepared = {b: doc for b, doc in byzantine["prepared"].items() if b != "JUD"}
    assert _checks(byzantine, prepared)["I4"] == "prepared book inventory differs"


def test_a_refused_relocation_fails_i4(byzantine: Context) -> None:
    rows = copy.deepcopy(byzantine["dispositions"])
    for row in rows:
        if row["ref"] == "MAT 23:13" and row.get("action") == "move":
            row["execution"] = "refused"
    assert "required relocations" in _checks(byzantine, rows=rows)["I4"]


def test_source_ranges_cannot_escape_the_verse() -> None:
    edit: Edit = {
        "range": [0, 1],
        "applied_range": [-1, 1],
        "old": "A",
        "new": "B",
        "rendered": "B",
        "seams": [],
    }
    with pytest.raises(ValueError, match="stale source offsets"):
        verify.closure("A.", [edit])
    edit["applied_range"] = [0, 3]
    with pytest.raises(ValueError, match="stale source offsets"):
        verify.closure("A.", [edit])


def test_external_seams_cannot_escape_the_verse() -> None:
    edit: Edit = {
        "range": [0, 1],
        "applied_range": [0, 1],
        "old": "A",
        "new": "B",
        "rendered": "B",
        "seams": [
            {"range": [2, 3], "rule": 2, "external": True, "from": "", "to": "."}
        ],
    }
    with pytest.raises(ValueError, match="stale seam offsets"):
        verify.closure("A.", [edit])


def test_note_lemma_italics_are_checked_independently() -> None:
    document = usj.document(
        [
            {"type": "book", "marker": "id", "code": "TST", "content": []},
            {"type": "chapter", "marker": "c", "number": "1"},
            usj.para(
                "p",
                {"type": "verse", "marker": "v", "number": "1"},
                usj.char("add", "the"),
                " word.",
            ),
        ]
    )
    note: Node = {
        "type": "note",
        "marker": "f",
        "caller": "-",
        "content": [
            usj.char("fq", "the: "),
            usj.char("ft", "Textus Receptus: "),
            usj.char("fqa", "a"),
        ],
    }
    prepared = scripture.edited(
        document, [(scripture.verses(document)["1:1"], 3, 3, [note])]
    )
    row: Disposition = {
        "unit": "TST 1:1#1",
        "ref": "TST 1:1",
        "disposition": "override",
        "action": "edit",
        "execution": "applied",
        "note": note,
        "note_ref": "TST 1:1",
        "note_scope": {"ref": "TST 1:1", "range": [0, 3], "offset": 3},
    }
    results = verify.checks(
        {"TST": document},
        {"TST": prepared},
        [{"id": row["unit"]}],
        [row],
        NO_STRUCTURE,
    )
    assert results["I2"] == "pass"
    assert results["I3"] == "TST 1:1: TR lemma italics differ from its span"


def test_restore_keeps_terminal_punctuation() -> None:
    note = _note("fruit", "fruits")
    assert verify.restores("Bring fruit.", "Bring fruits.", [(11, note)]) is None
    assert verify.restores("Bring fruit!", "Bring fruits.", [(11, note)]) is not None
    assert verify.restores("Bring fruit..", "Bring fruits.", [(11, note)]) is not None


def test_finished_verses_are_checked_under_their_source_ref_with_offsets_kept(
    byzantine: Context,
) -> None:
    def doc(text: str, note: Node | None = None, address: str = "16:25") -> Document:
        chapter, verse = address.split(":")
        contents: Content = [text] if note is None else [text[:-1], note, text[-1]]
        return usj.document(
            [
                {"type": "chapter", "marker": "c", "number": chapter},
                usj.para(
                    "p", {"type": "verse", "marker": "v", "number": verse}, *contents
                ),
            ]
        )

    structure = byzantine["structure"]
    assert structure.rp_ref("ROM 16:25") == "ROM 14:24"
    original = {"ROM": doc("Bring   fruits.")}
    rows: list[Disposition] = [{"edits": [{"ref": "ROM 16:25"}]}]
    prepared = {"ROM": doc("Bring   fruit.", _note("fruit", "fruits"), "14:24")}
    assert verify.finished_verses(original, prepared, rows, set(), structure) == {}
    prepared = {"ROM": doc("Bring   fruit!", _note("fruit", "fruits"), "14:24")}
    problems = verify.finished_verses(original, prepared, rows, set(), structure)
    assert "ROM 16:25" in problems
    assert any("restore" in p for p in problems["ROM 16:25"])
