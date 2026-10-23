"""The Old Testament poetry after the Updated Brenton, and the New
Testament paragraphs and poetry preserved from Scrivener."""

from __future__ import annotations

import copy
import re
from typing import Any

import pytest
from conftest import Staged, changed

import bible.pipeline
import bible.policy
from bible import alignment, byzantine, export, lines, scripture, usj
from bible.checks import CheckFailed
from bible.usj import Document

# A chapter of prose as a source prints it, and the same words as the update
# sets them: a poem that opens mid-verse, a stanza break, prose resuming in
# the same paragraph and in a new one, and a line whose first word is
# respelled.
SOURCE = (
    "\\id TST\n\\c 1\n\\p\n"
    "\\v 1 And he said, Hear my voice, ye wives of Lamech; "
    "to-day I have slain a man.\n"
    "\\v 2 Cursed be \\f + \\fr 1:2 \\fqa Gr. \\ft accursed.\\f*Canaan, "
    "a slave shall he be: and he went away.\n"
    "\\p\n\\v 3 So they parted.\n"
)
UPDATE = (
    "\\id TST\n\\c 1\n\\p\n"
    "\\v 1 And he said,\n"
    "\\q1 Hear my voice, ye wives of Lamech;\n"
    "\\q1 Today I have slain a man.\n"
    "\\b\n\\q1\n"
    "\\v 2 Cursed be Canaan,\n"
    "\\q1 A slave shall he be:\n"
    "\\m and he went away.\n"
    "\\p\n\\v 3 So they parted.\n"
)


def lined(source: str, update: str, policy: bible.policy.Policy) -> Document:
    return lines.old_testament(
        {"TST": usj.parse(source)}, {"TST": usj.parse(update)}, policy
    )["TST"]


def markers(doc: Document) -> list[str]:
    """The paragraph markers of a document's chapters, its headings aside."""
    chapters = [
        i for i, block in enumerate(doc["content"]) if block["type"] == "chapter"
    ]
    return [
        block["marker"]
        for block in doc["content"][chapters[0] :]
        if block["type"] == "para" and block["marker"] not in {"ms1", "s2", "s3", "sd2"}
    ]


def test_a_source_paragraph_is_divided_as_the_update_divides_it(
    declared: bible.policy.Policy,
) -> None:
    doc = lined(SOURCE, UPDATE, declared)
    assert markers(doc) == ["p", "q1", "q1", "b", "q1", "q1", "m", "p"]
    verses = scripture.verses(doc)
    # The words that introduce the poem end their paragraph of prose; a
    # break after a respelled word (to-day) is placed by the line's first word.
    assert verses["1:1"].text == (
        "And he said,\nHear my voice, ye wives of Lamech;\nto-day I have slain a man."
    )
    # Prose resumes flush left as the update sets it; the next verse keeps
    # the source's own paragraph.
    assert (
        verses["1:2"].text
        == "Cursed be Canaan,\na slave shall he be:\nand he went away."
    )
    assert verses["1:3"].text == "So they parted."
    # A note standing at a break goes with the line it glosses.
    assert usj.serialize(doc).splitlines()[8:10] == [
        "\\q1",
        "\\v 2 Cursed be \\f + \\fr 1:2 \\fqa Gr. \\ft accursed.\\f*Canaan,",
    ]


def test_a_poem_after_a_dropped_line_opens_without_its_stanza_break(
    declared: bible.policy.Policy,
) -> None:
    # The witness sets the first verse as prose, so its lines go, and the
    # stanza break that followed them, which stood between two lines of
    # verse, does not stand between prose and verse.
    doc = lines.old_testament(
        {"TST": usj.parse(SOURCE)},
        {"TST": usj.parse(UPDATE)},
        declared,
        lambda code, label: label != "1:1",
    )["TST"]
    assert markers(doc) == ["p", "q1", "q1", "m", "p"]


def test_a_prose_exception_preserves_words_notes_and_inputs(
    declared: bible.policy.Policy,
) -> None:
    decided = changed(
        declared, "lines", lambda data: data.update(prose={"TST 1:2": "Prose."})
    )
    lines.check(decided)
    source, update = usj.parse(SOURCE), usj.parse(UPDATE)
    before = copy.deepcopy((source, update))
    result = lines.old_testament({"TST": source}, {"TST": update}, decided)["TST"]
    assert (source, update) == before
    assert parts(result, "1:2") == ["p"]
    assert parts(result, "1:1") == ["p", "q1", "q1"]
    for label, verse in scripture.verses(result).items():
        original = scripture.verses(source)[label]
        assert scripture.plain(verse.text) == scripture.plain(original.text)
        assert [note for _, note in verse.notes] == [note for _, note in original.notes]


@pytest.mark.parametrize("label", ["1:3", "1:4"])
def test_a_prose_exception_must_suppress_poetry(
    declared: bible.policy.Policy, label: str
) -> None:
    decided = changed(
        declared, "lines", lambda data: data.update(prose={f"TST {label}": "Prose."})
    )
    with pytest.raises(CheckFailed, match=f"suppress no poetry: TST {label}"):
        lined(SOURCE, UPDATE, decided)


def test_a_prose_exception_redundant_with_the_witness_is_refused(
    declared: bible.policy.Policy,
) -> None:
    decided = changed(
        declared, "lines", lambda data: data.update(prose={"TST 1:2": "Prose."})
    )
    with pytest.raises(CheckFailed, match="suppress no poetry: TST 1:2"):
        lines.old_testament(
            {"TST": usj.parse(SOURCE)},
            {"TST": usj.parse(UPDATE)},
            decided,
            lambda code, label: False,
        )


@pytest.mark.parametrize("entries", [{"TST 1": "Prose."}, {"TST 1:2": " "}])
def test_prose_exception_shape_is_checked(
    declared: bible.policy.Policy, entries: dict[str, str]
) -> None:
    decided = changed(declared, "lines", lambda data: data.update(prose=entries))
    with pytest.raises(CheckFailed, match="Prose decision"):
        lines.check(decided)


def test_a_note_at_a_break_stays_with_the_word_it_is_set_against(
    declared: bible.policy.Policy,
) -> None:
    # Set close after the last word of a line, a note stays on that line;
    # set after a space, before the next line's first word, it goes with it.
    source = (
        "\\id TST\n\\c 1\n\\p\n"
        "\\v 1 One two.\\f + \\fr 1:1 \\ft after.\\f* "
        "\\x + \\xo 1:1 \\xt See.\\x* Three four.\n"
    )
    update = "\\id TST\n\\c 1\n\\q1\n\\v 1 One two.\n\\q1 Three four.\n"
    exported = usj.serialize(lined(source, update, declared)).splitlines()
    assert exported[3:] == [
        "\\q1",
        "\\v 1 One two.\\f + \\fr 1:1 \\ft after.\\f*",
        "\\q1 \\x + \\xo 1:1 \\xt See.\\x*Three four.",
    ]


def test_a_break_the_words_do_not_place_stops_the_build_naming_the_line(
    declared: bible.policy.Policy,
) -> None:
    update = UPDATE.replace("he said,\n\\q1 Hear my voice,", "he spake,\n\\q1 Hearken,")
    with pytest.raises(CheckFailed, match=r"TST 1:1: line 'hearken ye wives"):
        lined(SOURCE, update, declared)
    # A decision names the update's line and the source's words.
    decided = changed(
        declared,
        "lines",
        lambda data: data["breaks"].update(
            {
                "TST 1:1": [
                    {
                        "follows": "Hearken, ye wives",
                        "line": "Hear my voice",
                        "why": ".",
                    }
                ]
            }
        ),
    )
    assert scripture.verses(lined(SOURCE, update, decided))["1:1"].lines == (13, 48)


def test_a_line_in_a_prose_verse_needs_no_placing_and_takes_no_decision(
    declared: bible.policy.Policy,
) -> None:
    # The witness drops the first verse's lines wherever they stand, so the
    # words need not place them, and a decision there would change nothing.
    update = UPDATE.replace("he said,\n\\q1 Hear my voice,", "he spake,\n\\q1 Hearken,")
    doc = lines.old_testament(
        {"TST": usj.parse(SOURCE)},
        {"TST": usj.parse(update)},
        declared,
        lambda code, label: label != "1:1",
    )["TST"]
    assert markers(doc) == ["p", "q1", "q1", "m", "p"]
    decided = changed(
        declared,
        "lines",
        lambda data: data["breaks"].update(
            {
                "TST 1:1": [
                    {
                        "follows": "Hearken, ye wives",
                        "line": "Hear my voice",
                        "why": ".",
                    }
                ]
            }
        ),
    )
    with pytest.raises(CheckFailed, match="decision in a verse set as prose: TST 1:1"):
        lines.old_testament(
            {"TST": usj.parse(SOURCE)},
            {"TST": usj.parse(update)},
            decided,
            lambda code, label: label != "1:1",
        )


def test_a_line_the_update_numbers_otherwise_goes_by_the_source_verse(
    declared: bible.policy.Policy,
) -> None:
    # The update begins verse 2, which the witness sets as prose, a line
    # before the source does: the line stands in the source's verse 1, so it
    # is not dropped with verse 2, and a decision may set it there.
    update = UPDATE.replace(
        "Hear my voice, ye wives of Lamech;\n\\q1 Today I have slain a man.",
        "Hear my voice, ye women of Lamek;\n\\q1 \\v 2 This day I slew one.",
    ).replace("\\q1\n\\v 2 Cursed", "\\q1 Cursed")
    with pytest.raises(CheckFailed, match="Line the words do not place"):
        lines.old_testament(
            {"TST": usj.parse(SOURCE)},
            {"TST": usj.parse(update)},
            declared,
            lambda code, label: label != "1:2",
        )
    decided = changed(
        declared,
        "lines",
        lambda data: data["breaks"].update(
            {
                "TST 1:1": [
                    {
                        "follows": "This day I slew one",
                        "line": "to-day I have slain a man",
                        "why": ".",
                    }
                ]
            }
        ),
    )
    doc = lines.old_testament(
        {"TST": usj.parse(SOURCE)},
        {"TST": usj.parse(update)},
        decided,
        lambda code, label: label != "1:2",
    )["TST"]
    assert scripture.verses(doc)["1:1"].text == (
        "And he said,\nHear my voice, ye wives of Lamech;\nto-day I have slain a man."
    )
    # A line in a verse the source lacks is not dropped into the line before.
    lacking = UPDATE.replace("\\m and he went away.", "\\q1 \\v 4 Then departed he.")
    with pytest.raises(CheckFailed, match="Line the words do not place"):
        lines.old_testament(
            {"TST": usj.parse(SOURCE)},
            {"TST": usj.parse(lacking.replace("he be:", "he become."))},
            declared,
            lambda code, label: label != "1:4",
        )


def test_a_line_is_not_dropped_after_where_it_can_begin(
    declared: bible.policy.Policy,
) -> None:
    # The update begins verse 3 inside the source's verse 2, both set as
    # prose: at the source's verse 3, the line would leave the whole of
    # verse 2 in the last line of verse 1's poem.
    update = (
        "\\id TST\n\\c 1\n\\p\n"
        "\\v 1 And he said,\n"
        "\\q1 Hear my voice, ye wives of Lamech;\n"
        "\\q1 Today I have slain a man. \\v 2 Cursed be Kenaan,\n"
        "\\q1 \\v 3 Bondman becomes he: and he went away.\n"
        "\\p So they parted.\n"
    )
    with pytest.raises(CheckFailed, match="Line the words do not place"):
        lines.old_testament(
            {"TST": usj.parse(SOURCE)},
            {"TST": usj.parse(update)},
            declared,
            lambda code, label: label == "1:1",
        )


def test_a_decision_may_set_a_line_in_a_prose_verse_the_words_leave_open(
    declared: bible.policy.Policy,
) -> None:
    # The words leave the line anywhere from the end of verse 1, which the
    # witness sets as verse, to verse 2, which it sets as prose: it is not
    # dropped unplaced, and a decision there changes something.
    update = UPDATE.replace("slain a man.", "slain a lad.").replace(
        "Cursed be Canaan,", "Damned is Kenaan,"
    )

    def set_in_lines(policy: bible.policy.Policy) -> Document:
        return lines.old_testament(
            {"TST": usj.parse(SOURCE)},
            {"TST": usj.parse(update)},
            policy,
            lambda code, label: label != "1:2",
        )["TST"]

    with pytest.raises(CheckFailed, match="Line the words do not place"):
        set_in_lines(declared)
    decided = changed(
        declared,
        "lines",
        lambda data: data["breaks"].update(
            {
                "TST 1:2": [
                    {"follows": "Damned is Kenaan", "line": "Cursed be", "why": "."}
                ]
            }
        ),
    )
    verses = scripture.verses(set_in_lines(decided))
    assert verses["1:1"].text == (
        "And he said,\nHear my voice, ye wives of Lamech;\nto-day I have slain a man."
    )
    assert (
        verses["1:2"].text == "Cursed be Canaan, a slave shall he be: and he went away."
    )


def test_a_decision_the_words_place_alike_or_that_no_line_takes_is_refused(
    declared: bible.policy.Policy,
) -> None:
    alike = changed(
        declared,
        "lines",
        lambda data: data["breaks"].update(
            {
                "TST 1:1": [
                    {"follows": "Hear my voice", "line": "Hear my voice", "why": "."}
                ]
            }
        ),
    )
    with pytest.raises(CheckFailed, match="place alike"):
        lined(SOURCE, UPDATE, alike)
    untaken = changed(
        declared,
        "lines",
        lambda data: data["breaks"].update(
            {"TST 1:3": [{"follows": "Nothing here", "line": "So they", "why": "."}]}
        ),
    )
    with pytest.raises(CheckFailed, match="no line takes"):
        lined(SOURCE, UPDATE, untaken)


def test_a_decision_may_move_a_line_or_say_the_source_has_none(
    declared: bible.policy.Policy,
) -> None:
    moved = changed(
        declared,
        "lines",
        lambda data: data["breaks"].update(
            {
                "TST 1:1": [
                    {"follows": "Today I have", "line": "I have slain", "why": "."}
                ]
            }
        ),
    )
    assert scripture.verses(lined(SOURCE, UPDATE, moved))["1:1"].lines == (13, 55)
    none = changed(
        declared,
        "lines",
        lambda data: data["breaks"].update(
            {"TST 1:1": [{"follows": "Today I have", "line": None, "why": "."}]}
        ),
    )
    assert scripture.verses(lined(SOURCE, UPDATE, none))["1:1"].lines == (13,)


def test_a_source_paragraph_inside_a_poem_must_begin_at_a_line(
    declared: bible.policy.Policy,
) -> None:
    source = SOURCE.replace("Lamech; to-day", "Lamech;\n\\p to-day")
    assert markers(lined(source, UPDATE, declared))[:3] == ["p", "q1", "q1"]
    source = SOURCE.replace("ye wives", "\n\\p ye wives")
    with pytest.raises(CheckFailed, match="divides the poem"):
        lined(source, UPDATE, declared)


@pytest.mark.parametrize("destination", [None, "I have slain"])
def test_unused_decisions_sharing_a_destination_are_refused(
    declared: bible.policy.Policy, destination: str | None
) -> None:
    decided = changed(
        declared,
        "lines",
        lambda data: data["breaks"].update(
            {
                "TST 1:1": [
                    {"follows": follows, "line": destination, "why": "."}
                    for follows in ("Today I have", "Nothing here")
                ]
            }
        ),
    )
    with pytest.raises(CheckFailed, match="no line takes.*nothing here"):
        lined(SOURCE, UPDATE, decided)


def test_a_decision_cannot_be_taken_twice() -> None:
    chapter = lines.chapters(usj.parse(SOURCE))["1"]
    decision = lines.Decision("TST 1:1", ("today",), None)
    decisions = lines.Decisions([decision])
    assert decisions.take(decision, chapter) is None
    with pytest.raises(CheckFailed, match="taken more than once"):
        decisions.take(decision, chapter)


def test_a_null_destination_still_requires_a_source_verse(
    declared: bible.policy.Policy,
) -> None:
    decided = changed(
        declared,
        "lines",
        lambda data: data["breaks"].update(
            {"TST 1:99": [{"follows": "Today I have", "line": None, "why": "."}]}
        ),
    )
    with pytest.raises(CheckFailed, match="verse the source lacks: TST 1:99"):
        lined(SOURCE, UPDATE, decided)


@pytest.mark.parametrize("field", ["follows", "line"])
def test_punctuation_is_not_a_line_selector(
    declared: bible.policy.Policy, field: str
) -> None:
    entry = {"follows": "Today I have", "line": "I have slain", "why": "."}
    entry[field] = "—?!"
    decided = changed(
        declared,
        "lines",
        lambda data: data["breaks"].update({"TST 1:1": [entry]}),
    )
    with pytest.raises(CheckFailed, match="without words"):
        lines.check(decided)


def test_conflicting_anchors_do_not_place_a_break() -> None:
    aligned = alignment.Alignment.of(
        ["one", "two", "three", "four"],
        ["one", "two", "extra", "three", "four"],
    )
    with pytest.raises(lines.Unplaced):
        lines.placed(2, aligned, None)


@pytest.mark.parametrize(
    "distance, source_distance, expected",
    [(1, 3, 10), (5, 7, 10), (5, 8, None), (6, 6, None)],
)
def test_isolated_matches_need_a_nearby_run(
    distance: int, source_distance: int, expected: int | None
) -> None:
    # Test both sides of a run at the existing five-word and two-word allowances.
    for direction in (-1, 1):
        near = 10 + direction * distance
        position = 10 + direction * source_distance
        solid = {near: position, near + direction: position + direction}
        aligned = alignment.Alignment({10: 10, **solid}, solid, {})
        assert aligned.anchored(10) == expected


@pytest.mark.parametrize("previous", [2, 3])
def test_a_break_cannot_go_back_to_an_already_begun_line(previous: int) -> None:
    aligned = alignment.Alignment.of(
        ["one", "two", "three", "four"], ["one", "two", "three", "four"]
    )
    with pytest.raises(lines.Disordered):
        lines.placed(2, aligned, previous)


def test_a_line_in_a_prose_verse_may_stand_out_of_order() -> None:
    # The words place the line at or before the line already begun: in a
    # verse set as prose it goes with that line, if it lies in the verse.
    doc = usj.parse("\\id TST\n\\c 1\n\\p\n\\v 1 one two three four\n\\v 2 five six\n")
    chapter = lines.chapters(doc)["1"]
    aligned = alignment.Alignment.of(chapter.texts, chapter.texts)

    def place(previous: int, prose: bool) -> int | None:
        return lines.place_break(
            2,
            chapter,
            chapter,
            aligned,
            previous,
            "TST",
            lines.Decisions([]),
            lambda label: prose,
        )

    assert place(3, prose=True) == 3
    with pytest.raises(lines.Disordered):
        place(3, prose=False)
    with pytest.raises(lines.Disordered):
        place(4, prose=True)


def test_new_line_words_cannot_stand_before_the_break() -> None:
    aligned = alignment.Alignment({2: 3}, {2: 3}, {1: 3, 3: 2})
    with pytest.raises(lines.Unplaced):
        lines.placed(2, aligned, 0)


def test_a_chapter_opening_inside_a_poem_opens_with_its_line(
    declared: bible.policy.Policy,
) -> None:
    source = "\\id TST\n\\c 1\n\\p\n\\v 1 One two three.\n\\c 2\n\\nb\n\\v 1 four five six.\n"
    update = "\\id TST\n\\c 1\n\\q1\n\\v 1 One two three.\n\\c 2\n\\q1\n\\v 1 Four five six.\n"
    assert markers(lined(source, update, declared)) == ["q1", "q1"]
    # A chapter the update opens in prose keeps the continued paragraph.
    prose = update.replace("\\c 2\n\\q1", "\\c 2\n\\nb")
    assert markers(lined(source, prose, declared)) == ["q1", "nb"]


def test_a_title_is_never_a_line(declared: bible.policy.Policy) -> None:
    source = (
        "\\id TST\n\\c 1\n\\d\n\\v 1 A Psalm.\n\\p The Lord said, and said again.\n"
    )
    update = "\\id TST\n\\c 1\n\\d\n\\v 1 A Psalm.\n\\q1 The Lord said,\n\\q1 And said again.\n"
    doc = lined(source, update, declared)
    assert markers(doc) == ["d", "q1", "q1"]
    assert (
        scripture.verses(doc)["1:1"].text == "A Psalm.\nThe Lord said,\nand said again."
    )


# The edition.


def unit(edition: bible.pipeline.Edition, code: str) -> Document:
    return edition.documents[code]


def test_every_line_of_the_update_is_a_line_of_the_edition(
    edition: bible.pipeline.Edition, read: bible.pipeline.Read
) -> None:
    wanted = sum(
        1
        for doc in read.updated_brenton.values()
        for block in doc["content"]
        if block.get("marker") == "q1"
    )
    old_testament = [
        e["id"] for e in edition.policy.scripture if e.get("source") == "brenton"
    ]
    printed = sum(
        1
        for code in old_testament
        for block in unit(edition, code)["content"]
        if block.get("marker") == "q1"
    )
    # Less the lines of the verses Scrivener or a decision sets as prose,
    # and the one line the edition lacks by a reading from Codex Alexandrinus,
    # which the decisions give as no line.
    witness = lines.scrivener(read.kjv, edition.policy)
    prose = 0
    for code, doc in read.updated_brenton.items():
        if code not in old_testament:
            continue
        blocks: set[int] = set()
        for label, verse in scripture.verses(doc).items():
            key = f"{code} {label}"
            if witness(code, label) is False or key in edition.policy.lines.get(
                "prose", {}
            ):
                blocks |= {
                    block
                    for block, _, _, _ in verse.parts
                    if doc["content"][block]["marker"] == "q1"
                }
        prose += len(blocks)
    unlined = sum(
        1
        for key, entries in edition.policy.lines["breaks"].items()
        if key[:3] in old_testament
        for entry in entries
        if entry["line"] is None
    )
    # Psalm 71:20 is also a poetic line: the source marked the collection's
    # closing verse as a descriptive title, which assembly corrects.
    assert wanted == 16781 and printed == wanted - prose - unlined + 1
    assert 13000 < printed < 16000


def test_the_psalter_is_set_in_the_updates_lines(
    edition: bible.pipeline.Edition,
) -> None:
    psalms = scripture.verses(unit(edition, "PSA"))
    assert psalms["1:1"].text == (
        "Blessed is the man who hath not walked in the counsel of the ungodly,\n"
        "and hath not stood in the way of sinners,\n"
        "and hath not sat in the seat of evil men."
    )
    assert markers(unit(edition, "PSA"))[:11] == ["q1"] * 9 + ["b", "q1"]
    # The update numbers Psalm 12 otherwise; the chapter's words place its lines.
    assert psalms["12:2"].text == (
        "How long, O Lord, wilt thou forget me? for ever?\n"
        "how long wilt thou turn away thy face from me?"
    )
    # A title is not a line, and a psalm's first line follows it.
    assert psalms["109:1"].text.startswith(
        "A Psalm of David.\nThe Lord said to my Lord"
    )


def test_the_hebrew_letters_of_lamentations_head_their_lines(
    edition: bible.pipeline.Edition,
) -> None:
    doc = unit(edition, "LAM")
    verses = scripture.verses(doc)
    assert verses["1:2"].text.startswith("Beth\nShe weepeth sore in the night,\n")
    assert verses["3:22"].text.startswith("Heth\nIt is the mercies of the Lord,\n")
    assert verses["4:17"].text == (
        "Phe\nWhile we yet lived our eyes failed,\n"
        "while we looked in vain for our help.\n"
        "Tsade\nWe looked to a nation that could not save."
    )


def test_prose_resumes_under_its_declared_marker(
    edition: bible.pipeline.Edition,
) -> None:
    # Prose resumes flush left where Boyd does, within a verse too.
    judges = unit(edition, "JDG")
    verse = scripture.verses(judges)["14:18"]
    assert [judges["content"][block]["marker"] for block, *_ in verse.parts] == [
        "p",
        "q1",
        "q1",
        "m",
        "q1",
        "q1",
    ]
    exodus = scripture.verses(unit(edition, "EXO"))
    assert exodus["15:19"].text.startswith("For the horse of Pharaoh")
    assert [
        unit(edition, "EXO")["content"][block]["marker"]
        for block, *_ in exodus["15:19"].parts
    ] == ["m"]


def test_chapters_the_source_continued_open_with_their_lines(
    edition: bible.pipeline.Edition,
) -> None:
    for code, number, opening in (
        ("SIR", "39", "will seek out the wisdom of all the ancients,"),
        ("PRO", "16", "All the works of the humble"),
    ):
        doc = unit(edition, code)
        at = next(
            i
            for i, block in enumerate(doc["content"])
            if block["type"] == "chapter" and block["number"] == number
        )
        first = doc["content"][at + 1]
        assert first["marker"] == "q1"
        assert usj.text_of(first["content"]).startswith(opening)
    genesis = unit(edition, "GEN")
    at = next(
        i
        for i, block in enumerate(genesis["content"])
        if block["type"] == "chapter" and block["number"] == "2"
    )
    assert genesis["content"][at + 1]["marker"] == "p"


def test_scrivener_says_which_verses_are_verse(
    edition: bible.pipeline.Edition,
) -> None:
    job = unit(edition, "JOB")
    assert parts(job, "1:1") == ["p"] and parts(job, "2:13") == ["p"]
    assert parts(job, "1:21") == ["p", "q1", "q1", "q1", "q1", "q1"]
    assert parts(job, "3:3") == ["q1", "q1"] and parts(job, "42:6") == ["q1", "q1"]
    assert parts(job, "42:7") == ["p"]
    # A Septuagint addition lettered to a verse goes as that verse goes.
    assert parts(job, "42:17b") == ["p"] and parts(job, "2:9a") == ["p"]
    assert parts(unit(edition, "PRO"), "24:22g") == ["q1", "q1"]
    # A lettered verse with a counterpart of its own goes as that goes:
    # Proverbs 24:22f is the Hebrew's 30:1, which Scrivener sets as prose.
    assert parts(unit(edition, "PRO"), "24:22f") == ["p", "p"]
    ecclesiastes = unit(edition, "ECC")
    assert parts(ecclesiastes, "1:2") == ["p"] and parts(ecclesiastes, "12:13") == ["p"]
    assert parts(ecclesiastes, "3:2") == ["q1", "q1"]
    # A book Scrivener set wholly as prose, and the Apocrypha, which the table
    # does not map to his, follow the update.
    assert parts(unit(edition, "WIS"), "7:7") == ["q1", "q1"]
    assert parts(unit(edition, "SIR"), "2:1") == ["q1", "q1"]
    # The author's colophon is an explicit exception following Scrivener.
    sirach = unit(edition, "SIR")
    assert parts(sirach, "50:27") == ["p"]
    assert parts(sirach, "50:26") == ["q1", "q1", "q1"]
    assert parts(sirach, "50:28") == ["q1", "q1"]
    # His own lines in the prophets do not come in.
    assert all(block.get("marker") != "q1" for block in unit(edition, "ISA")["content"])


def test_ecclesiastes_times_poem_ends_before_verse_nine(
    edition: bible.pipeline.Edition, prepared: list[tuple[str, Document]]
) -> None:
    doc = unit(edition, "ECC")
    assert parts(doc, "3:8") == ["q1", "q1"]
    assert parts(doc, "3:9") == ["p"]
    assert parts(doc, "3:10") == ["p"]
    printed = dict(prepared)["ECC"]
    verses = scripture.verses(printed)
    blocks = printed["content"]
    for label, previous in (("3:9", ["q2", "b"]), ("3:10", ["p"])):
        at, start, _, _ = verses[label].parts[0]
        assert start == 1
        assert blocks[at]["marker"] == "p"
        assert [b["marker"] for b in blocks[at - len(previous) : at]] == previous


@pytest.mark.parametrize("label", ["1:1", "1:2", "1:3", "1:4"])
def test_unspaced_decisions_must_name_a_prose_paragraph_after_poetry(
    label: str,
) -> None:
    with pytest.raises(CheckFailed, match="Unspaced decision"):
        lines.unspaced(usj.parse(SOURCE), {f"TST {label}": "No extra blank."})


def test_an_unspaced_decision_drops_the_blank_before_its_paragraph() -> None:
    doc = usj.parse(
        "\\id TST\n\\c 1\n\\q1\n\\v 1 Sing.\n\\q2 Again.\n\\p\n\\v 2 Prose.\n"
    )
    unspaced = lines.unspaced(doc, {"TST 1:2": "No extra blank."})
    assert markers(export.spaced(doc)) == ["q1", "q2", "b", "p"]
    assert markers(export.spaced(doc, unspaced)) == ["q1", "q2", "p"]


def test_an_excerpt_passes_over_the_unspaced_verses_it_leaves_out() -> None:
    decisions = {"TST 1:4": "No extra blank."}
    assert lines.unspaced(usj.parse(SOURCE), decisions, excerpt=True) == set()


def test_the_song_of_the_three_children_stays_in_lines(
    edition: bible.pipeline.Edition,
) -> None:
    daniel = unit(edition, "DAG")
    verse = scripture.verses(daniel)["3:26"]
    assert [daniel["content"][block]["marker"] for block, *_ in verse.parts] == [
        "q1",
        "q1",
    ]


def parts(doc: Document, label: str) -> list[str]:
    verse = scripture.verses(doc)[label]
    return [doc["content"][block]["marker"] for block, *_ in verse.parts]


def test_the_line_stage_preserves_verses_notes_and_new_testament_paragraphs_within_chapters(
    staged: Staged,
) -> None:
    units, after = staged.units, staged.lined
    before = {code: staged.assembled[code] for code in byzantine.BOOKS}
    assert list(after) == list(units)
    for code, original in units.items():
        before_verses = scripture.verses(original)
        after_verses = scripture.verses(after[code])
        assert list(after_verses) == list(before_verses), code
        for label, verse in before_verses.items():
            text = after_verses[label].text
            assert scripture.words_of(text) == scripture.words_of(verse.text), (
                code,
                label,
            )
            # A line boundary may replace a space or stand beside punctuation
            # without one (GEN 49:26, mother—it). All other characters stay.
            pattern = r"\s*".join(
                re.escape(scripture.plain(part)) for part in text.splitlines()
            )
            assert re.fullmatch(pattern, scripture.plain(verse.text)), (code, label)
            # Compare whole notes, including their ordered content, x-key, and x-scope.
            assert [note for _, note in after_verses[label].notes] == [
                note for _, note in verse.notes
            ], (code, label)
        assert usj.notes_of(after[code]["content"]) == usj.notes_of(
            original["content"]
        ), code
    assert len(before) == 27
    for code, doc in before.items():
        assert after[code] == lines.opened(doc)


def test_the_decisions_are_the_few_the_words_do_not_place(
    policy: bible.policy.Policy,
) -> None:
    assert list(policy.lines["breaks"]) == [
        "PSA 41:9",
        "PSA 87:19",
        "PSA 91:10",
        "PSA 94:3",
        "PSA 138:1",
        "PRO 8:32",
        "PRO 9:6",
        "LAM 3:45",
        "LAM 4:17",
        "LAM 4:18",
    ]


def test_the_lines_file_is_checked(declared: bible.policy.Policy) -> None:
    def malformed(data: dict[str, Any]) -> None:
        data["breaks"]["GEN 1"] = [{"follows": "x", "line": "y", "why": "."}]

    with pytest.raises(CheckFailed, match="not a verse"):
        lines.check(changed(declared, "lines", malformed))

    def wordless(data: dict[str, Any]) -> None:
        data["breaks"]["GEN 1:1"] = [{"follows": "", "line": "y", "why": "."}]

    with pytest.raises(CheckFailed, match="without words"):
        lines.check(changed(declared, "lines", wordless))


@pytest.mark.parametrize("kind", ["breaks", "prose", "unspaced"])
def test_new_testament_line_decisions_are_refused(
    read: bible.pipeline.Read,
    declared: bible.policy.Policy,
    kind: str,
) -> None:
    decided = changed(
        declared,
        "lines",
        lambda data: data.setdefault(kind, {}).update(
            {
                "MAT 4:6": (
                    [{"follows": "x", "line": "y", "why": "."}]
                    if kind == "breaks"
                    else "."
                )
            }
        ),
    )
    with pytest.raises(CheckFailed, match="no Old Testament book.*MAT 4:6"):
        bible.pipeline.lined({"MAT": read.kjv["MAT"]}, read, decided)


def test_quotation_extent_decisions_are_refused(
    declared: bible.policy.Policy,
) -> None:
    decided = changed(declared, "lines", lambda data: data.update(extents={}))
    with pytest.raises(CheckFailed, match="Lines file has missing or unknown fields"):
        lines.check(decided)


@pytest.mark.parametrize(
    "body,expected",
    [
        ("\\q1 \\v 1 Sing. Pause.", ["q1", "qr"]),
        ("\\q1 \\v 1 Pause.", ["qr"]),
        ("\\q1 \\v 1 Sing. A song of Pause.", ["q1"]),
        ("\\q1 \\v 1 A song of Pause.", ["q1"]),
    ],
)
def test_pause_instructions(body: str, expected: list[str]) -> None:
    source = usj.parse("\\id PSA\n\\c 1\n" + body)
    before = copy.deepcopy(source)
    result = lines.pauses(source)
    assert markers(result) == expected
    assert source == before and lines.pauses(result) == result
    assert {
        key: scripture.plain(verse.text)
        for key, verse in scripture.verses(result).items()
    } == {
        key: scripture.plain(verse.text)
        for key, verse in scripture.verses(source).items()
    }


@pytest.mark.parametrize(
    "body",
    [
        "\\p \\v 1 Sing. Pause.",
        "\\q1 \\v 1 Sing Pause.",
        "\\q1 \\v 1 Pause. Sing.",
        "\\q1 \\v 1 Sing; Pause: words.",
    ],
)
def test_an_unexpected_pause_is_refused(body: str) -> None:
    source = usj.parse("\\id PSA\n\\c 2\n" + body)
    with pytest.raises(CheckFailed, match="Unexpected Pause instruction: PSA 2:1"):
        lines.pauses(source)


def test_an_inline_pause_is_declared_and_met() -> None:
    kept = usj.parse("\\id PSA\n\\c 67\n\\q1 \\v 7 Sing.\n\\q1 \\v 8 Go; Pause: on.")
    before = copy.deepcopy(kept)
    result = lines.pauses(kept)
    assert kept == before
    assert scripture.verses(result)["67:8"].text == "Go; Pause: on."
    assert [
        usj.text_of(node["content"])
        for node in usj.walk(result["content"])
        if usj.is_type(node, "char", "qs")
    ] == ["Pause:"]
    assert lines.pauses(result) == result
    moved = usj.parse("\\id PSA\n\\c 67\n\\q1 \\v 8 Go. Pause.")
    with pytest.raises(CheckFailed, match="no Pause meets: \\['PSA 67:8'\\]"):
        lines.pauses(moved)


def test_pause_keeps_its_explanation_and_styles() -> None:
    source = usj.parse(
        "\\id PSA\n\\c 3\n\\q1 \\v 3 Sing. "
        "\\f + \\fr 3:3 \\ft Pause explained.\\f*\\it Pause.\\it*\n"
        "\\q1 \\v 4 Words.\\f + \\ft Pause.\\f*"
    )
    result = lines.pauses(source)
    assert markers(result) == ["q1", "qr", "q1"]
    instruction = next(b for b in result["content"] if b.get("marker") == "qr")
    assert instruction["content"] == [
        usj.char("qs", *source["content"][2]["content"][2:])
    ]
    assert (
        scripture.verses(result)["3:3"].notes[0][1]
        == scripture.verses(source)["3:3"].notes[0][1]
    )


# The names Brenton sets inside their verses, as the line decisions give them.
WITHIN_VERSE = frozenset(
    {("3", "45", "Ain."), ("4", "17", "Tsade."), ("4", "18", "Koph.")}
)


def test_the_names_within_their_verses_come_from_the_line_decisions(
    declared: bible.policy.Policy,
) -> None:
    assert lines.within_verse(declared) == WITHIN_VERSE


def acrostic_source(chapter: str) -> Document:
    """All source labels, with opening and mid-verse placements exercised."""
    content = ""
    previous = ""
    for verse, name in lines.acrostic_inventory(chapter):
        if verse != previous:
            content += f"\n\\q1 \\v {verse} "
        if (chapter, verse, name) in {("3", "45", "Ain."), ("4", "18", "Koph.")}:
            content += "Before. "
        content += f"\\sc {name}\\sc* Words. "
        previous = verse
    return usj.parse(f"\\id LAM\n\\c {chapter}\n" + content)


def test_descriptive_titles_keep_fragments_and_verse_continuations() -> None:
    source = usj.parse(
        "\\id JER\n\\c 30\n"
        "\\p \\v 1 \\sc Concerning Idumea,\\sc* thus saith the Lord.\n"
        "\\p \\v 29 \\sc Concerning Damascus.\\sc* "
        "\\f - \\ft A note.\\f*Emath is brought to shame.\n"
        "\\p \\v 30 More words.\n"
        "\\p \\v 31 \\sc A complete title.\\sc*\n"
        "\\p \\v 32 \\sc The Word that came, saying,\\sc*\n"
        "\\p \\v 33 Thus saith the Lord."
    )
    before = copy.deepcopy(source)
    result = lines.descriptive_titles(source)
    assert [b["marker"] for b in result["content"] if b["type"] == "para"] == [
        "p",
        "d",
        "p",
        "p",
        "d",
        "p",
        "p",
    ]
    assert {
        k: (scripture.plain(v.text), v.notes)
        for k, v in scripture.verses(result).items()
    } == {
        k: (scripture.plain(v.text), v.notes)
        for k, v in scripture.verses(source).items()
    }
    assert source == before and lines.descriptive_titles(result) == result


@pytest.mark.parametrize("chapter,count", [("1", 22), ("2", 22), ("3", 23), ("4", 22)])
def test_acrostic_headings_preserve_content(chapter: str, count: int) -> None:
    source = acrostic_source(chapter)
    before = copy.deepcopy(source)
    result = lines.acrostics(source, WITHIN_VERSE)
    headings = [b for b in result["content"] if b.get("marker") == "qa"]
    assert len(headings) == count
    assert all(
        not any(usj.is_type(i, "char", "sc") for i in b["content"]) for b in headings
    )
    assert source == before and lines.acrostics(result, WITHIN_VERSE) == result
    assert {
        key: scripture.plain(verse.text)
        for key, verse in scripture.verses(result).items()
    } == {
        key: scripture.plain(verse.text)
        for key, verse in scripture.verses(source).items()
    }
    assert [
        i
        for b in result["content"]
        for i in b.get("content", [])
        if usj.is_type(i, "verse")
    ] == [
        i
        for b in source["content"]
        for i in b.get("content", [])
        if usj.is_type(i, "verse")
    ]


@pytest.mark.parametrize(
    "old,new,match",
    [
        ("Aleph.", "Alef.", "label: LAM 1:1"),
        ("\\sc Aleph.", "Before. \\sc Aleph.", "placement: LAM 1:1"),
        ("\\sc Beth.\\sc*", "", "inventory: LAM 1:22"),
        ("\\v 2", "\\v 23", "label: LAM 1:23"),
    ],
)
def test_changed_acrostic_source_is_refused(old: str, new: str, match: str) -> None:
    source = usj.parse(usj.serialize(acrostic_source("1")).replace(old, new, 1))
    with pytest.raises(CheckFailed, match=match):
        lines.acrostics(source, WITHIN_VERSE)


def test_a_name_declared_within_its_verse_that_opens_it_is_refused() -> None:
    # The declaration would go stale unnoticed.
    text = usj.serialize(acrostic_source("3"))
    assert "Before. \\sc Ain." in text
    source = usj.parse(text.replace("Before. \\sc Ain.", "\\sc Ain.", 1))
    with pytest.raises(CheckFailed, match="placement: LAM 3:45"):
        lines.acrostics(source, WITHIN_VERSE)


def test_source_instructions_across_the_corpus(
    staged: Staged, read: bible.pipeline.Read, edition: bible.pipeline.Edition
) -> None:
    aligned = lines.old_testament(
        {code: staged.assembled[code] for code in ("PSA", "HAB", "LAM")},
        read.updated_brenton,
        edition.policy,
        lines.scrivener(read.kjv, edition.policy),
    )
    for code, transform, marker, count in (
        ("PSA", lines.pauses, "qr", 70),
        ("HAB", lines.pauses, "qr", 3),
        (
            "LAM",
            lambda doc: lines.acrostics(doc, lines.within_verse(edition.policy)),
            "qa",
            89,
        ),
    ):
        before = aligned[code]
        # Isolate the two rules from alignment, which may split styled spans.
        source = staged.line_documents[code]
        assert sum(b.get("marker") == marker for b in source["content"]) == count
        assert transform(source) == source
        originals = scripture.verses(before)
        for key, verse in scripture.verses(source).items():
            original = originals[key]
            assert [note for _, note in verse.notes] == [
                note for _, note in original.notes
            ]
        names = {*lines.ACROSTIC_NAMES, "Rechs."}

        def without_selah(content: usj.Content) -> usj.Content:
            return usj.mapped(
                content,
                lambda node: (
                    node["content"]
                    if usj.is_type(node, "char", "qs")
                    or (
                        code == "LAM"
                        and usj.is_type(node, "char", "sc")
                        and usj.text_of(node["content"]) in names
                    )
                    else node
                ),
            )

        # Selah supplies semantic markup and qa replaces inline small caps;
        # all other verse/style nodes survive intact.
        unwrapped = usj.with_content(source, without_selah)
        before = usj.with_content(before, without_selah)
        assert [
            item
            for block in unwrapped["content"]
            for item in block.get("content", [])
            if usj.is_type(item, "char") or usj.is_type(item, "verse")
        ] == [
            item
            for block in before["content"]
            for item in block.get("content", [])
            if usj.is_type(item, "char") or usj.is_type(item, "verse")
        ]
        assert {
            k: scripture.plain(v.text) for k, v in scripture.verses(source).items()
        } == {k: scripture.plain(v.text) for k, v in scripture.verses(before).items()}
