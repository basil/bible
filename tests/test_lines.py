"""The Old Testament poetry after the Updated Brenton, and the New
Testament paragraphs and poetry preserved from Scrivener."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

import pytest
from conftest import changed

import bible.pipeline
import bible.policy
import bible.sources
from bible import byzantine, lines, scripture, terminology, usj
from bible.checks import CheckFailed
from bible.usj import Document

# A chapter of prose as a source prints it, and the same words as the update
# sets them: a poem that opens mid-verse, a stanza break, prose resuming in
# the same paragraph and in a new one, and a line whose first word is
# respelt.
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
    # break after a respelt word (to-day) is placed by the line's first word.
    assert verses["1:1"].text == (
        "And he said,\nHear my voice, ye wives of Lamech;\nto-day I have slain a man."
    )
    # Prose resumes in the same paragraph, flush left, and the next verse
    # keeps the source's own paragraph.
    assert (
        verses["1:2"].text
        == "Cursed be Canaan,\na slave shall he be:\nand he went away."
    )
    assert verses["1:3"].text == "So they parted."
    # A note standing at a break goes with the line it glosses.
    assert usj.serialize(doc).splitlines()[7:9] == [
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
    assert exported[2:] == [
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
    alignment = lines.Alignment.of(
        ["one", "two", "three", "four"],
        ["one", "two", "extra", "three", "four"],
    )
    with pytest.raises(lines.Unplaced):
        lines.placed(2, alignment, None)


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
        alignment = lines.Alignment({10: 10, **solid}, solid, {})
        assert alignment.anchored(10) == expected


@pytest.mark.parametrize("previous", [2, 3])
def test_a_break_cannot_go_back_to_an_already_begun_line(previous: int) -> None:
    alignment = lines.Alignment.of(
        ["one", "two", "three", "four"], ["one", "two", "three", "four"]
    )
    with pytest.raises(lines.Disordered):
        lines.placed(2, alignment, previous)


def test_new_line_words_cannot_stand_before_the_break() -> None:
    alignment = lines.Alignment({2: 3}, {2: 3}, {1: 3, 3: 2})
    with pytest.raises(lines.Unplaced):
        lines.placed(2, alignment, 0)


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
    # Less the lines of the verses Scrivener sets as prose, and the one line
    # the edition's text lacks by a reading from Codex Alexandrinus, which
    # the decisions give as no line.
    witness = lines.scrivener(read.kjv, edition.policy)
    prose = 0
    for code, doc in read.updated_brenton.items():
        if code not in old_testament:
            continue
        blocks: set[int] = set()
        for label, verse in scripture.verses(doc).items():
            if witness(code, label) is False:
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
    assert wanted == 16781 and printed == wanted - prose - unlined
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
    assert verses["1:2"].text.startswith("Beth. She weepeth sore in the night,\n")
    assert verses["3:21a"].text.startswith("Heth. It is the mercies of the Lord,\n")
    assert verses["4:17"].text == (
        "Phe. While we yet lived our eyes failed,\n"
        "while we looked in vain for our help.\n"
        "Tsade. We looked to a nation that could not save."
    )


def test_prose_resumes_as_the_update_resumes_it(
    edition: bible.pipeline.Edition,
) -> None:
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
    assert genesis["content"][at + 1]["marker"] == "nb"


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
    assert parts(unit(edition, "PRO"), "24:22f") == ["m", "p"]
    ecclesiastes = unit(edition, "ECC")
    assert parts(ecclesiastes, "1:2") == ["p"] and parts(ecclesiastes, "12:13") == ["p"]
    assert parts(ecclesiastes, "3:2") == ["q1", "q1"]
    # A book Scrivener set wholly as prose, and the Apocrypha, which the table
    # does not map to his, follow the update.
    assert parts(unit(edition, "WIS"), "7:7") == ["q1", "q1"]
    assert parts(unit(edition, "SIR"), "2:1") == ["q1", "q1"]
    # His own lines in the prophets do not come in.
    assert all(block.get("marker") != "q1" for block in unit(edition, "ISA")["content"])


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


def test_the_line_stage_preserves_verses_notes_and_new_testament_documents(
    read: bible.pipeline.Read,
    sources: bible.sources.Sources,
    declared: bible.policy.Policy,
) -> None:
    promoted = bible.pipeline.promote(
        read, declared, sources.byzantine, terminology.registry(declared)
    )
    units = bible.pipeline.assemble(promoted, declared, sources)
    policy = bible.pipeline.placed(units, read, declared)
    before = {code: deepcopy(units[code]) for code in byzantine.BOOKS}
    after = bible.pipeline.lined(units, read, policy)
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
            # Compare whole notes, including their ordered content, x-key and x-scope.
            assert [note for _, note in after_verses[label].notes] == [
                note for _, note in verse.notes
            ], (code, label)
        assert usj.notes_of(after[code]["content"]) == usj.notes_of(
            original["content"]
        ), code
    assert len(before) == 27
    for code, doc in before.items():
        assert after[code] is units[code]
        assert after[code] == doc


def test_the_decisions_are_the_few_the_words_do_not_place(
    policy: bible.policy.Policy,
) -> None:
    assert list(policy.lines["breaks"]) == [
        "JOB 2:11",
        "JOB 42:17e",
        "PSA 87:19",
        "PSA 91:10",
        "PSA 94:3",
        "PSA 138:1",
        "PRO 8:32",
        "PRO 9:6",
        "LAM 3:21a",
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


def test_new_testament_line_decisions_are_refused(
    read: bible.pipeline.Read,
    declared: bible.policy.Policy,
) -> None:
    decided = changed(
        declared,
        "lines",
        lambda data: data["breaks"].update(
            {"MAT 4:6": [{"follows": "x", "line": "y", "why": "."}]}
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
