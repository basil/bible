"""Every Textus Receptus footnote of the reconciliation has a unique lemma and
the agreed shape, and putting it back gives the King James words."""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import NamedTuple

import pytest

import bible.pipeline
from bible import lemmas, scripture, usj
from bible.byzantine import edit, notes
from bible.byzantine.edit import NOTE_KINDS, NOTE_LABELS
from bible.byzantine.rows import Disposition, NoteScope
from bible.byzantine.stages import Context
from bible.scripture import Verse
from bible.usj import Content, Document, Node

SHAPES = re.compile(
    r"^(Textus Receptus: |Textus Receptus adds: |Textus Receptus omits: "
    r"|Textus Receptus adds verse \d+: |Textus Receptus has this passage at [0-9:–]+\."
    r"|Textus Receptus has here the verses printed at [0-9:–]+\.)$"
)
# The notes that name where a passage stands, with no lemma.
PLACED = ("has this passage", "has here the verses printed")

type Found = tuple[str, Verse, int, Node]


def fields(note: Node) -> dict[str, str]:
    return {
        n["marker"]: usj.text_of(n["content"])
        for n in note["content"]
        if isinstance(n, dict)
    }


@pytest.fixture(scope="module")
def edition_notes(byzantine: Context) -> list[Found]:
    """(ref, verse, offset, note) for every note the Orthodox Liturgical
    English Bible (OLEB) added."""
    found = []
    for book, doc in byzantine["prepared"].items():
        for address, verse in scripture.verses(doc).items():
            for offset, note in verse.notes:
                if note.get("category") == "edition" or note.get("x-key"):
                    found.append((f"{book} {address}", verse, offset, note))
    return found


def test_the_edition_adds_notes(edition_notes: list[Found]) -> None:
    assert len(edition_notes) > 700
    # A note for each edit and each structural change, the doxology of
    # Romans 16 noted at both ends.
    assert len(edition_notes) == 867


def test_structural_notes_stand_where_the_verses_were(
    edition_notes: list[Found],
) -> None:
    by_key = {note["x-key"]: (ref, fields(note)) for ref, _, _, note in edition_notes}
    # An omitted verse is noted at the verse before it.
    ref, found = by_key["LUK 17:35 TR"]
    assert ref == "LUK 17:35"
    assert found["ft"] == "Textus Receptus adds verse 36: "
    # A passage moved out of its chapter is noted at both ends.
    assert by_key["ROM 14:24 TR"] == (
        "ROM 14:24",
        {"fr": "14:24 ", "ft": "Textus Receptus has this passage at 16:25–27."},
    )
    assert by_key["ROM 16:24 TR"] == (
        "ROM 16:24",
        {
            "fr": "16:24 ",
            "ft": "Textus Receptus has here the verses printed at 14:24–26.",
        },
    )


def test_insertion_before_sentence_stop_keeps_its_short_note(
    edition_notes: list[Found],
) -> None:
    # The restored lemma closes up the space before the stop, as before a
    # comma, so the note need not widen past it.
    _, verse, offset, note = next(row for row in edition_notes if row[0] == "MRK 15:32")
    f = fields(note)
    assert f["fq"] == "believe him: "
    assert f["ft"] == "Textus Receptus omits: "
    assert f["fqa"] == "him"
    assert verse.text[:offset].endswith("believe him")
    assert verse.text[offset:].startswith(". And")


def test_declared_clause_lemma_restores_omission_before_it(
    edition_notes: list[Found],
) -> None:
    _, verse, offset, note = next(row for row in edition_notes if row[0] == "LUK 4:8")
    f = fields(note)
    assert f["fq"] == "it is written: "
    assert f["ft"] == "Textus Receptus: "
    assert f["fqa"] == "for it is written"
    assert verse.text[:offset].endswith("Satan: it is written")
    assert verse.text[offset:].startswith(", Thou shalt worship")


def test_declared_phrase_after_comma_restores_initial_conjunction(
    edition_notes: list[Found],
) -> None:
    f = next(
        fields(note)
        for ref, _, _, note in edition_notes
        if ref == "REV 13:17" and fields(note)["fq"] == "the name of the beast: "
    )
    assert f["ft"] == "Textus Receptus: "
    assert f["fqa"] == "or the name of the beast"


def test_disjoint_declared_lemmas_separate_one_owners_edits(
    edition_notes: list[Found],
) -> None:
    found = [fields(note) for ref, _, _, note in edition_notes if ref == "REV 14:8"]
    assert len(found) == 2
    assert found[0]["fq"] == "another, a second angel: "
    assert found[0]["fqa"] == "another angel"
    assert found[1]["fq"].startswith("Babylon the great is fallen: she made")
    assert found[1]["fqa"].startswith(
        "Babylon is fallen, is fallen, that great city, because she made"
    )


def test_declared_lemma_keeps_moved_pronoun_in_one_restoring_note(
    edition_notes: list[Found],
) -> None:
    found = [fields(note) for ref, _, _, note in edition_notes if ref == "MRK 14:30"]
    assert len(found) == 1
    assert found[0]["fq"].startswith("That thou this day,")
    assert found[0]["fqa"].endswith("thou shalt deny me thrice")


def test_every_note_key_is_unique(edition_notes: list[Found]) -> None:
    keys = [note["x-key"] for *_, note in edition_notes]
    assert len(keys) == len(set(keys))


def test_every_lemma_is_unique_in_its_verse(edition_notes: list[Found]) -> None:
    for ref, verse, offset, note in edition_notes:
        f = fields(note)
        if "fq" not in f:
            assert any(placed in f["ft"] for placed in PLACED), ref
            continue
        phrase = f["fq"].removesuffix(": ")
        assert phrase, ref
        hits = lemmas.occurrences(
            scripture.word_spans(verse.text), scripture.words_of(phrase)
        )
        assert len(hits) == 1, (ref, phrase)
        assert note["x-scope"]["lemma"] == phrase


def test_every_note_has_the_agreed_shape(edition_notes: list[Found]) -> None:
    for ref, verse, offset, note in edition_notes:
        f = fields(note)
        # The note at a passage's old place is the edition's own, not a
        # Textus Receptus note on a lemma.
        if "has here the verses printed" not in f["ft"]:
            assert note["caller"] == "-", ref
        assert f["fr"] == ref.split()[1] + " ", ref
        assert SHAPES.match(f["ft"]), (ref, f["ft"])
        markers = [n["marker"] for n in note["content"] if isinstance(n, dict)]
        if any(placed in f["ft"] for placed in PLACED):
            assert markers == ["fr", "ft"]
        else:
            assert markers == ["fr", "fq", "ft", "fqa"], (ref, markers)
            assert f["fqa"].strip(), ref


def noted(byzantine: Context) -> list[Disposition]:
    """The rows whose edits carry TR notes: all but the corrections of
    shared Greek."""
    return [r for r in byzantine["dispositions"] if r["disposition"] != "shared"]


def test_kinds_follow_the_edits(byzantine: Context) -> None:
    def kind(note: Node) -> str:
        found = note["x-scope"]["kind"]
        where = note["x-scope"].get("where")
        assert fields(note)["ft"] == NOTE_LABELS[found].format(where=where)
        return found

    for row in noted(byzantine):
        for e in row.get("edits", []):
            if e["note_scope"].get("combined") or e["note_scope"].get("full"):
                assert kind(e["note"]) == "replace", row["unit"]
            else:
                assert kind(e["note"]) == NOTE_KINDS[e["kind"]], row["unit"]
        note = row.get("note")
        if row.get("action") == "omit":
            assert note
            assert kind(note) == "adds-verse"
            assert note["x-scope"]["where"] == row["ref"].split(":")[1]
        if row.get("action") == "move" and note:
            assert kind(note) == "moved"
        if "source_note" in row:
            assert kind(row["source_note"]) == "moved-out"


def test_the_lemma_contains_the_changed_words(byzantine: Context) -> None:
    for row in noted(byzantine):
        for e in row.get("edits", []):
            f = fields(e["note"])
            glossed = e["note"]["x-scope"]["glossed"]
            lemma = f["fq"].removesuffix(": ")
            if e["kind"] != "delete" and not e["note_scope"].get("combined"):
                assert glossed and lemmas.occurrences(
                    scripture.word_spans(lemma), scripture.words_of(glossed)
                ), (row["unit"], lemma, glossed)


def test_the_alternative_restores_the_source_words(
    byzantine: Context,
    kjv_text: Mapping[str, str],
    prepared_verses: dict[str, Verse],
) -> None:
    """Substituting fqa for the lemma gives the KJV words at a replacement."""
    rows = byzantine["dispositions"]
    shared = {row["ref"] for row in rows if row["disposition"] == "shared"}
    checked = 0
    for row in rows:
        edits = row.get("edits", [])
        if (
            len(edits) != 1
            or edits[0]["ref"] in shared
            or edits[0]["kind"] != "replace"
            or edits[0]["note_scope"].get("combined")
        ):
            continue
        e = edits[0]
        scope = e["note_scope"]
        if (
            scope["ref"] != e["ref"]
            or len(
                [x for r in rows for x in r.get("edits", []) if x["ref"] == e["ref"]]
            )
            != 1
        ):
            continue
        verse = prepared_verses[scope["ref"]]
        span = scope["range"]
        assert span is not None
        a, b = span
        restored = (
            verse.text[:a]
            + fields(e["note"])["fqa"]
            + scope.get("terminal_stop", "")
            + verse.text[b:]
        )
        assert scripture.words_of(restored) == scripture.words_of(kjv_text[e["ref"]]), (
            row["unit"],
            restored,
        )
        checked += 1
    assert checked > 300


def test_the_lemma_decisions_apply(
    byzantine: Context, dispositions: dict[str, Disposition]
) -> None:
    entries = byzantine["note_lemmas"]
    assert entries
    for d in entries:
        e = dispositions[d["id"]]["edits"][d["edit"] - 1]
        lemma = fields(e["note"])["fq"].removesuffix(": ")
        assert lemmas.occurrences(
            scripture.word_spans(lemma), scripture.words_of(d["lemma"])
        ), (d["id"], lemma)


def test_a_stale_lemma_decision_is_refused(byzantine: Context) -> None:
    row = next(r for r in byzantine["dispositions"] if r.get("edits"))
    rows: list[Disposition] = [{**row, "edits": [e.copy() for e in row["edits"]]}]
    stale = {"id": "MAT 0:0#1", "edit": 1, "lemma": "nothing", "why": "Test."}
    with pytest.raises(ValueError, match="Stale TR note lemma decisions"):
        notes.apply(byzantine["documents"], byzantine["prepared"], rows, [stale])


def test_readable_span_widens_to_a_unique_phrase(byzantine: Context) -> None:
    verse = scripture.verses(byzantine["documents"]["JHN"])["1:1"]
    words = scripture.word_spans(verse.text)
    assert [w for w, *_ in words].count("word") == 3
    at = [i for i, (w, *_) in enumerate(words) if w == "word"][1]
    first, last = notes.readable_span(verse.text, words, at, at)
    assert first <= at <= last and (first, last) != (at, at)
    phrase = scripture.words_of(verse.text)[first : last + 1]
    assert len(lemmas.occurrences(words, phrase)) == 1


def test_readable_span_prefers_a_surviving_reading(byzantine: Context) -> None:
    verse = scripture.verses(byzantine["prepared"]["MAT"])["3:8"]
    words = scripture.word_spans(verse.text)
    at = next(i for i, (w, *_) in enumerate(words) if w == "fruit")
    assert notes.readable_span(verse.text, words, at, at, ["therefore fruit meet"]) == (
        at - 1,
        at + 1,
    )


def restored_verse(verse: Verse) -> str:
    """Read only the note fields and positions, without execution metadata."""
    text = verse.text
    changes: list[tuple[int, int, str]] = []
    for offset, note in verse.notes:
        f = fields(note)
        label = f.get("ft", "")
        if (
            not label.startswith("Textus Receptus")
            or " verse " in label
            or any(placed in label for placed in PLACED)
        ):
            continue
        lemma = f["fq"].removesuffix(": ")
        end = offset
        start = end - len(lemma)
        # A supplied span can close after its last word's stop.
        while text[start:end] != lemma and end and text[end - 1] in notes.STOPS:
            end -= 1
            start = end - len(lemma)
        assert text[start:end] == lemma, (lemma, offset)
        alternative = f["fqa"]
        if label.endswith("adds: "):
            changes.append((end, end, " " + alternative))
        elif label.endswith("omits: "):
            matches = list(
                re.finditer(
                    r"(?<![A-Za-z])" + re.escape(alternative) + r"(?![A-Za-z])",
                    lemma,
                )
            )
            assert matches, (lemma, alternative)
            match = matches[-1]
            changes.append((start + match.start(), start + match.end(), ""))
        else:
            changes.append((start, end, alternative))
    for start, end, alternative in sorted(changes, reverse=True):
        text = text[:start] + alternative + text[end:]
    return text


def normalized_note_restoration(text: str) -> str:
    """Ignore whitespace and apostrophe encoding, retain case and every stop."""
    text = " ".join(text.replace("'", "’").split())
    return re.sub(r"\s+([,;:.!?])", r"\1", text)


def test_notes_restore_every_ordinary_edited_verse(byzantine: Context) -> None:
    edited = (
        {e["ref"] for row in byzantine["dispositions"] for e in row.get("edits", [])}
        - set(byzantine["structure"].moved)
        - {r["ref"] for r in byzantine["dispositions"] if r["disposition"] == "shared"}
    )
    checked = set()
    for book, document in byzantine["prepared"].items():
        for address, verse in scripture.verses(document).items():
            ref = f"{book} {address}"
            if ref not in edited:
                continue
            restored = restored_verse(verse)
            assert normalized_note_restoration(restored) == normalized_note_restoration(
                byzantine["kjv"][ref]
            ), (ref, restored, byzantine["kjv"][ref])
            checked.add(ref)
    assert checked == edited
    assert len(checked) > 700


@pytest.mark.parametrize(
    "mutation", ["lemma", "alternative", "position", "terminal_stop"]
)
def test_restoration_detects_mutations(byzantine: Context, mutation: str) -> None:
    verse = scripture.verses(byzantine["prepared"]["MAT"])["3:8"]
    original = normalized_note_restoration(byzantine["kjv"]["MAT 3:8"])
    assert normalized_note_restoration(restored_verse(verse)) == original
    edited_notes = list(copy.deepcopy(verse.notes))
    offset, note = next(
        (at, note)
        for at, note in edited_notes
        if fields(note).get("ft", "").startswith("Textus Receptus")
    )
    if mutation in {"lemma", "alternative"}:
        marker = "fq" if mutation == "lemma" else "fqa"
        field = next(
            n
            for n in note["content"]
            if isinstance(n, dict) and n.get("marker") == marker
        )
        value = usj.text_of(field["content"])
        field["content"] = [value[0].swapcase() + value[1:]]
    elif mutation == "position":
        edited_notes = [(at + 1 if n is note else at, n) for at, n in edited_notes]
    altered = replace(verse, notes=tuple(edited_notes))
    if mutation == "terminal_stop":
        altered = replace(altered, text=verse.text.rstrip()[:-1] + ";")
    if mutation in {"lemma", "position"}:
        with pytest.raises(AssertionError):
            restored_verse(altered)
    else:
        assert normalized_note_restoration(restored_verse(altered)) != original


@pytest.mark.parametrize(
    "ref,finished_stop,original_stop",
    [
        ("ACT 24:6", ":", "."),
        ("ROM 12:1", ":", "."),
        ("2CO 1:6", ";", "."),
        ("COL 1:23", ".", ";"),
        ("1JN 5:7", ",", "."),
    ],
)
def test_changed_terminal_stop_belongs_to_lemma(
    byzantine: Context, ref: str, finished_stop: str, original_stop: str
) -> None:
    book, address = ref.split()
    verse = scripture.verses(byzantine["prepared"][book])[address]
    note = next(
        note
        for _, note in reversed(verse.notes)
        if fields(note).get("ft", "").startswith("Textus Receptus")
    )
    f = fields(note)
    assert f["fq"].removesuffix(": ").endswith(finished_stop)
    assert f["fqa"].endswith(original_stop)
    assert normalized_note_restoration(restored_verse(verse)) == (
        normalized_note_restoration(byzantine["kjv"][ref])
    )


def omitted_quotation(byzantine: Context, ref: str) -> str:
    row = next(
        r
        for r in byzantine["dispositions"]
        if r.get("action") == "omit" and r["ref"] == ref
    )
    book, address = row["note_scope"]["ref"].split()
    verse = scripture.verses(byzantine["prepared"][book])[address]
    label = f"Textus Receptus adds verse {ref.split(':')[1]}: "
    return next(
        fields(n)["fqa"] for _, n in verse.notes if fields(n).get("ft") == label
    )


@pytest.mark.parametrize("ref", ["LUK 17:36", "ACT 8:37", "ACT 15:34", "ACT 24:7"])
def test_omitted_verse_quotes_complete_kjv(byzantine: Context, ref: str) -> None:
    assert normalized_note_restoration(omitted_quotation(byzantine, ref)) == (
        normalized_note_restoration(byzantine["kjv"][ref])
    )


def test_omitted_verse_quotation_check_detects_changed_final_stop(
    byzantine: Context,
) -> None:
    ref = "ACT 8:37"
    quote = omitted_quotation(byzantine, ref)
    original = normalized_note_restoration(byzantine["kjv"][ref])
    assert normalized_note_restoration(quote) == original
    assert normalized_note_restoration(quote.rstrip()[:-1] + ";") != original


def styled(
    content: Iterable[str | Node], italic: bool = False
) -> list[tuple[str, bool]]:
    """(letter, italic) pairs of a USJ tree, skipping notes; add and it are italic."""
    result: list[tuple[str, bool]] = []
    for node in content:
        if isinstance(node, str):
            result.extend((letter, italic) for letter in node)
        elif node["type"] != "note" and "content" in node:
            result.extend(
                styled(node["content"], italic or node.get("marker") in {"add", "it"})
            )
    return result


def verse_style(document: Document, verse: Verse) -> list[tuple[str, bool]]:
    result: list[tuple[str, bool]] = []
    for block, lo, hi, _ in verse.parts:
        if result:
            result.append(("\n", False))
        result.extend(styled(document["content"][block]["content"][lo:hi]))
    assert "".join(c for c, _ in result) == verse.text
    return result


def field_nodes(note: Node) -> dict[str, Content]:
    """A note's fields as their USJ content, keeping character styles."""
    return {
        node["marker"]: node["content"]
        for node in note["content"]
        if isinstance(node, dict)
    }


def assert_lemma_ends_at_note(
    document: Document, verse: Verse, offset: int, note: Node
) -> None:
    """The lemma occurs once, ends at the note and keeps the verse's italics."""
    body = field_nodes(note)
    if "fq" not in body:
        return
    quote = styled(body["fq"])
    assert "".join(c for c, _ in quote[-2:]) == ": "
    quote = quote[:-2]
    text = "".join(c for c, _ in quote)
    hits = list(re.finditer(r"(?<!\w)" + re.escape(text) + r"(?!\w)", verse.text))
    assert len(hits) == 1, (verse.reference, text, len(hits))
    match = hits[0]
    assert match.end() <= offset, (verse.reference, text, offset)
    # A closing stop inside an italic span stays before the note.
    assert all(c in ",;:.!?—" for c in verse.text[match.end() : offset]), (
        verse.reference,
        text,
        offset,
    )
    assert quote == verse_style(document, verse)[match.start() : match.end()], (
        verse.reference,
        text,
    )


def test_lemmas_end_at_the_note_with_the_verse_italics(byzantine: Context) -> None:
    checked = 0
    supplied = 0
    for document in byzantine["prepared"].values():
        for verse in scripture.verses(document).values():
            for offset, note in verse.notes:
                if "Textus Receptus" not in usj.text_of(note["content"]):
                    continue
                assert_lemma_ends_at_note(document, verse, offset, note)
                body = field_nodes(note)
                if "fq" in body:
                    checked += 1
                    supplied += any(italic for _, italic in styled(body["fq"]))
    assert checked > 700
    assert supplied > 0


class Owned(NamedTuple):
    """A note's owner: the King James verse it quotes, the kind of its edit,
    whether it is an omitted verse's, and its scope, note and source range."""

    ref: str
    kind: str | None
    omitted: bool
    scope: NoteScope
    note: Node
    range: list[int] | None


def test_alternatives_preserve_the_pinned_kjv_styles(byzantine: Context) -> None:
    """Each alternative has the styles of its source range, short and
    structural notes included."""
    owners: dict[str, Owned] = {}
    for row in noted(byzantine):
        for edit in row.get("edits", []):
            if edit.get("note_owner", True):
                owners[edit["note"]["x-key"]] = Owned(
                    edit["ref"],
                    edit["kind"],
                    False,
                    edit["note_scope"],
                    edit["note"],
                    edit["range"],
                )
        note = row.get("note")
        if row.get("action") == "omit" and note:
            owners[note["x-key"]] = Owned(
                row["ref"], row.get("kind"), True, row["note_scope"], note, None
            )
    by_ref: dict[str, list[Owned]] = {}
    for item in owners.values():
        by_ref.setdefault(item.scope["ref"], []).append(item)
    originals = {
        book: scripture.verses(doc) for book, doc in byzantine["documents"].items()
    }
    checked = supplied = 0
    for book, document in byzantine["prepared"].items():
        # Match each note by its recorded verse and offset, then compare
        # against the pinned source.
        for address, verse in scripture.verses(document).items():
            by_offset: dict[int, list[Node]] = {}
            for offset, note in verse.notes:
                if "Textus Receptus" in usj.text_of(note["content"]):
                    by_offset.setdefault(offset, []).append(note)
            for item in by_ref.get(f"{book} {address}", []):
                scope = item.scope
                declared = field_nodes(item.note)
                candidates = [
                    n
                    for n in by_offset[scope["offset"]]
                    if all(
                        usj.text_of(field_nodes(n).get(f, []))
                        == usj.text_of(declared.get(f, []))
                        for f in ("fq", "ft")
                    )
                ]
                assert len(candidates) == 1, (item.ref, scope["offset"])
                body = field_nodes(candidates[0])
                if "fqa" not in body:
                    continue
                if (
                    item.kind == "insert"
                    and not scope.get("full")
                    and not scope.get("combined")
                ):
                    continue  # Quotes added RP words; no KJV alternative exists.
                source_book, source_ref = item.ref.split()
                source = originals[source_book][source_ref]
                if item.omitted:
                    a, b = 0, len(source.text)
                else:
                    span = scope.get("source_range", item.range)
                    assert span is not None
                    a, b = span
                expected = verse_style(byzantine["documents"][source_book], source)[a:b]
                if scope.get("terminal_stop"):
                    assert expected[-1][0] == scope["terminal_stop"]
                    expected = expected[:-1]
                actual = styled(body["fqa"])
                assert actual == expected, (item.ref, item.kind, actual, expected)
                checked += 1
                supplied += any(italic for _, italic in actual)
    assert checked > 700
    assert supplied > 0


def test_lemma_style_check_detects_plain_text_preserving_italic_corruption(
    byzantine: Context,
) -> None:
    for document in byzantine["prepared"].values():
        for verse in scripture.verses(document).values():
            for offset, original in verse.notes:
                if "Textus Receptus" not in usj.text_of(original["content"]):
                    continue
                body = field_nodes(original)
                if "fq" not in body or not any(i for _, i in styled(body["fq"])):
                    continue
                note = copy.deepcopy(original)
                fq = next(
                    n
                    for n in note["content"]
                    if isinstance(n, dict) and n["marker"] == "fq"
                )
                fq["content"] = [usj.text_of(fq["content"])]
                assert usj.text_of(note["content"]) == usj.text_of(original["content"])
                with pytest.raises(AssertionError):
                    assert_lemma_ends_at_note(document, verse, offset, note)
                return
    raise AssertionError("No supplied-word lemma exercised")


def test_lemma_position_check_detects_a_note_moved_before_its_lemma(
    byzantine: Context,
) -> None:
    for document in byzantine["prepared"].values():
        for verse in scripture.verses(document).values():
            for offset, note in verse.notes:
                if "Textus Receptus" not in usj.text_of(
                    note["content"]
                ) or "fq" not in field_nodes(note):
                    continue
                with pytest.raises(AssertionError):
                    assert_lemma_ends_at_note(document, verse, 0, note)
                return
    raise AssertionError("No lemma exercised")


def test_alternative_style_comparison_detects_plain_text_preserving_corruption(
    byzantine: Context,
) -> None:
    for document in byzantine["prepared"].values():
        for verse in scripture.verses(document).values():
            for _, note in verse.notes:
                if "Textus Receptus" not in usj.text_of(note["content"]):
                    continue
                quote = field_nodes(note).get("fqa", [])
                expected = styled(quote)
                if not any(italic for _, italic in expected):
                    continue
                corrupted: Content = [usj.text_of(quote)]
                assert usj.text_of(corrupted) == usj.text_of(quote)
                with pytest.raises(AssertionError):
                    assert styled(corrupted) == expected
                return
    raise AssertionError("No supplied-word alternative exercised")


def kingdom() -> dict[str, usj.Document]:
    return {
        "MAT": usj.parse("\\id MAT\n\\c 1\n\\p\n\\v 1 And he came into the kingdom.\n")
    }


def replacing(unit: str, disposition: str, at: int, old: str, new: str) -> Disposition:
    op = {"kind": "replace", "ref": "MAT 1:1", "old": old, "new": new}
    return {
        "unit": unit,
        "ref": "MAT 1:1",
        "disposition": disposition,
        "action": "edit",
        "ops": [{**op, "range": [at, at + len(old)], "raw_range": True}],
    }


def test_a_tr_note_cannot_quote_a_correction_of_shared_greek() -> None:
    documents = kingdom()
    rows = [
        replacing("MAT 1:1#1", "override", 7, "came", "went"),
        replacing("MAT 1:1", "shared", 12, "into", "within"),
    ]
    prepared, rows = edit.execute(documents, rows, ["MAT"])
    lemma = {"id": "MAT 1:1#1", "edit": 1, "lemma": "went within", "why": "Test."}
    with pytest.raises(ValueError, match="is quoted by TR note"):
        notes.apply(documents, prepared, rows, [lemma])


def test_a_refused_correction_of_shared_greek_is_left_to_be_named() -> None:
    """The notes are finished without it; the build then names the refusal."""
    documents = kingdom()
    rows = [
        replacing("MAT 1:1#1", "override", 7, "came", "went"),
        replacing("MAT 1:1", "shared", 7, "came into", "went within"),
    ]
    prepared, rows = edit.execute(documents, rows, ["MAT"])
    assert rows[1]["execution"] == "refused"
    _, rows = notes.apply(documents, prepared, rows)
    assert [r["execution"] for r in rows] == ["applied", "refused"]


def test_corrections_of_shared_greek_leave_the_tr_notes_their_own_words(
    edition: bible.pipeline.Edition,
) -> None:
    # 2 John 1:3: the reading changes the pronoun alone; "shall" is shared.
    assert scripture.verses(edition.documents["2JN"])["1:3"].text.startswith(
        "Grace shall be with us, mercy"
    )
    assert "\\fq us: \\ft TR \\fqa you" in usj.serialize(edition.documents["2JN"])
    # 3 John 1:2 keeps its supplied word and its 1611 note on "wish".
    serialized = usj.serialize(edition.documents["3JN"])
    assert scripture.verses(edition.documents["3JN"])["1:2"].text.startswith(
        "Beloved, I wish that in all things thou mayest prosper"
    )
    assert "\\fq wish: \\ft or, \\fqa pray" in serialized
    assert "\\add things\\add*" in serialized
    # 1 Thessalonians 4:6: reverse the margin to quote the former KJV words.
    verse = scripture.verses(edition.documents["1TH"])["4:6"]
    assert "defraud his brother in the matter" in verse.text
    assert any(n["x-key"] == "1TH 4:6 in any matter" for _, n in verse.notes)
    assert r"\fq in the matter: \ft or, \fqa in any matter" in usj.serialize(
        edition.documents["1TH"]
    )
