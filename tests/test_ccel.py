"""Brenton's notes from CCEL's transcription, set in eBible's verses."""

from __future__ import annotations

import copy
import re
import unicodedata
from typing import Any

import pytest
from conftest import book, changed, verse_lines
from lxml import html

import bible.policy
from bible import ccel, pipeline, review, scripture, usj
from bible.checks import CheckFailed
from bible.sources import Content
from bible.usj import Document

VERSE_1 = (
    "And the heavens and the earth were finished, and the whole world of them. "
    "And God finished on the sixth day his works which he made, and he ceased "
    "on the seventh day from all his works which he made."
)
VERSE_2 = (
    "And God blessed the seventh day and sanctified it, because in it he ceased "
    "from all his works which God began to do. This is the book of the "
    "generation of heaven and earth, when they were made."
)


def caller(number: int) -> str:
    return (
        f'<a class="Note" name="_fnb{number}" href="#_fnf{number}">'
        f'<sup class="Note">{number}</sup></a>'
    )


def footnote(number: int, body: str) -> str:
    return (
        f'<div class="Note" id="_fnf{number}"><p><a class="Note" name="_fnf{number}" '
        f'href="#_fnb{number}"><sup class="Note">{number}</sup></a> {body}</p></div>'
    )


def page(text: str, *bodies: str) -> bytes:
    return (
        '<html><head><meta http-equiv="Content-Type" content="text/html; '
        'charset=utf-8" /><title>Chapter 2. </title></head><body>'
        '<p class="Center"><a href="TOC.htm">Contents</a></p>'
        f'<div type="Chapter" n="2" id="iii.2">{text}</div><hr class="Note">'
        + "".join(bodies)
        + "<center><table><tr><td>CCEL footer</td></tr></table></center>"
        "</body></html>"
    ).encode("utf-8")


def pages(**files: bytes) -> Content:
    return Content({f"{name}.htm": data for name, data in files.items()})


def genesis(verse_1: str = VERSE_1, verse_2: str = VERSE_2) -> Document:
    return book("GEN", f"\\v 1 {verse_1}\n\\v 2 {verse_2}")


def supplemented(
    policy: bible.policy.Policy, docs: dict[str, Document], **files: bytes
) -> tuple[dict[str, Document], ccel.Report]:
    result, report = ccel.supplemented(docs, pages(**files), policy)
    return dict(result), report


def ccel_notes(doc: Document) -> dict[str, str]:
    """Each CCEL note's content as USFM, by its key."""
    return {
        note["x-key"]: usj.serialize(note["content"])
        for note in usj.notes_of(doc["content"])
        if "CCEL" in note.get("x-key", "")
    }


def with_decisions(policy: bible.policy.Policy, **sections: Any) -> bible.policy.Policy:
    return changed(policy, "ccel_notes", lambda data: data.update(sections))


@pytest.fixture
def page_policy(declared: bible.policy.Policy) -> bible.policy.Policy:
    """Synthetic pages have no corpus-specific corrections or placements."""
    return with_decisions(declared, corrections={}, notes={})


def test_a_note_is_set_in_ebibles_verse_before_the_word_its_caller_precedes(
    page_policy: bible.policy.Policy,
) -> None:
    text = (
        "<sup>1</sup>And the heavens and the earth were finished, and the whole "
        f"{caller(1)}world of them. And God finished on the sixth day his works "
        f"which he made, and he {caller(2)}ceased on the seventh day from all his "
        "works which he made.<sup>2</sup> And God blessed the seventh day and "
        "sanctified it, because in it he ceased from all his works which God "
        f"{caller(3)}began to do. This <i>is</i> the book of the generation of "
        f"heaven and earth, when they were made.{caller(4)}"
    )
    docs, report = supplemented(
        page_policy,
        {"GEN": genesis()},
        iii_2=page(
            text,
            footnote(1, "<i>Or</i>, order. See <scripRef>John 1:10</scripRef>."),
            footnote(2, "<i>Gr.</i> rested."),
            footnote(3, "<i>Or,</i> made in the beginning."),
            footnote(
                4, "<scripRef>Heb. 4. 4</scripRef>; <scripRef>Heb. 4:10</scripRef>."
            ),
        ),
    )
    lines = verse_lines(docs["GEN"])
    assert lines["1"] == (
        "And the heavens and the earth were finished, and the whole "
        "\\f + \\fr 99:1 \\fqa Or, \\ft order. See \\xt John 1. 10\\ft .\\f*"
        "world of them. And God finished on the sixth day his works which he "
        "made, and he \\f + \\fr 99:1 \\fqa Gr. \\ft rested.\\f*ceased on the "
        "seventh day from all his works which he made."
    )
    assert lines["2"].endswith(
        "which God \\f + \\fr 99:2 \\fqa Or, \\ft made in the beginning.\\f*began "
        "to do. This is the book of the generation of heaven and earth, when "
        "they were made.\\x + \\xo 99:2 \\xt Heb. 4. 4; Heb. 4. 10.\\x*"
    )
    assert list(ccel_notes(docs["GEN"])) == [
        "GEN 99:1 CCEL",
        "GEN 99:1 CCEL#2",
        "GEN 99:2 CCEL",
        "GEN 99:2 CCEL#2",
    ]
    assert (report.pages, report.bodies, report.inserted, report.duplicates) == (
        1,
        4,
        4,
        0,
    )
    assert report.held == () and report.left_out == ()


def test_a_caller_that_closes_its_verse_stays_in_that_verse(
    page_policy: bible.policy.Policy,
) -> None:
    text = f"<sup>1</sup>{VERSE_1}{caller(1)} <sup>2</sup> {VERSE_2}{caller(2)}"
    docs, _ = supplemented(
        page_policy,
        {"GEN": genesis()},
        iii_2=page(
            text,
            footnote(1, "<i>Gr.</i> rested."),
            footnote(2, "<i>Or,</i> made."),
        ),
    )
    lines = verse_lines(docs["GEN"])
    assert lines["1"].endswith(
        "which he made.\\f + \\fr 99:1 \\fqa Gr. \\ft rested.\\f*"
    )
    assert lines["2"].startswith("And God blessed")
    assert lines["2"].endswith("were made.\\f + \\fr 99:2 \\fqa Or, \\ft made.\\f*")


def test_a_caller_in_repeated_wording_stands_at_its_own_occurrence(
    page_policy: bible.policy.Policy,
) -> None:
    # "his works which he made" stands twice in the verse; the caller is at
    # the second, and the words around it place it there, not at the first.
    text = "<sup>1</sup>" + VERSE_1.replace(
        "from all his works", f"from all his {caller(1)}works"
    )
    docs, _ = supplemented(
        page_policy,
        {"GEN": genesis()},
        iii_2=page(text, footnote(1, "<i>Gr.</i> deeds.")),
    )
    line = verse_lines(docs["GEN"])["1"]
    assert line.count("his works which he made") == 1
    assert "from all his \\f + \\fr 99:1 \\fqa Gr. \\ft deeds.\\f*works" in line


def test_a_run_across_ebibles_chapter_division_sets_each_note_in_its_chapter(
    page_policy: bible.policy.Policy,
) -> None:
    # CCEL runs on where eBible begins chapter 99, so the run is matched
    # against the chapter and its neighbours.
    doc = pipeline.keyed(
        "GEN",
        usj.parse(
            f"\\id GEN\n\\c 98\n\\p\n\\v 1 {VERSE_1}\n\\c 99\n\\p\n\\v 1 {VERSE_2}\n"
        ),
    )
    text = (
        f"<sup>1</sup>{VERSE_1.replace('world', caller(1) + 'world')} "
        f"{VERSE_2.replace('sanctified', caller(2) + 'sanctified')}"
    )
    docs, report = supplemented(
        page_policy,
        {"GEN": doc},
        iii_2=page(
            text, footnote(1, "<i>Or</i>, order."), footnote(2, "<i>Gr.</i> hallowed.")
        ),
    )
    assert list(ccel_notes(docs["GEN"])) == ["GEN 98:1 CCEL", "GEN 99:1 CCEL"]
    assert report.inserted == 2 and report.left_out == ()


def test_a_caller_that_opens_its_paragraph_opens_the_next_verse(
    page_policy: bible.policy.Policy,
) -> None:
    text = f"<p><sup>1</sup>{VERSE_1}</p><p>{caller(1)}<sup>2</sup> {VERSE_2}</p>"
    docs, _ = supplemented(
        page_policy,
        {"GEN": genesis()},
        iii_2=page(text, footnote(1, "<i>Gr.</i> rested.")),
    )
    lines = verse_lines(docs["GEN"])
    assert lines["1"].endswith("which he made.")
    assert lines["2"].startswith("\\f + \\fr 99:2 \\fqa Gr. \\ft rested.\\f*And God")


def test_a_note_ebible_already_has_in_the_verse_is_passed_over(
    page_policy: bible.policy.Policy,
) -> None:
    doc = genesis(
        "And the heavens and the earth were finished, and the whole "
        "\\f + \\fr 99:1 \\fqa Or, \\ft order. See \\xt John 1. 10.\\f*world of "
        "them. And God finished on the sixth day his works which he made, and "
        "he ceased on the seventh day from all his works which he made."
    )
    docs, report = supplemented(
        page_policy,
        {"GEN": doc},
        iii_2=page(
            f"<sup>1</sup>And the heavens and the earth were finished, and the whole "
            f"{caller(1)}world of them. And God finished on the sixth day his works "
            f"which he made, and he {caller(2)}ceased on the seventh day from all "
            "his works which he made.",
            footnote(1, "<i>Or</i>, order. See <scripRef>John 1. 10</scripRef>."),
            footnote(2, "<i>Gr.</i> rested."),
        ),
    )
    assert list(ccel_notes(docs["GEN"])) == ["GEN 99:1 CCEL#2"]
    assert (report.inserted, report.duplicates) == (1, 1)
    # The eBible note keeps its key; the CCEL note's key is its own.
    assert [n["x-key"] for n in usj.notes_of(docs["GEN"]["content"])] == [
        "GEN 99:1",
        "GEN 99:1 CCEL#2",
    ]


@pytest.mark.parametrize(
    "body, reason",
    [
        (
            '<FONT FACE="Unknown">abc</FONT>',
            "unsupported font 'unknown'",
        ),
        ("<sup>β</sup>", "a letter standing for a note set elsewhere"),
        ("", "empty"),
        ("Gr. o�koum�njn.", "undecodable characters"),
        ("<note><i>Gr.</i> be cemented.</note>", "unknown markup <note>"),
        ("See ver. 5. and 7.", "a number with a period within a sentence"),
        ("<i>Fem.</i> gen.", "abbreviation in a form the edition does not print"),
        ("<i>Gr.</i> fut.", "abbreviation in a form the edition does not print"),
        ("See 2 Kings (2 Sam.) 17. 19.", "citation the edition cannot read"),
    ],
)
def test_a_note_the_reader_does_not_understand_is_left_out_and_listed(
    page_policy: bible.policy.Policy, body: str, reason: str
) -> None:
    docs, report = supplemented(
        page_policy,
        {"GEN": genesis()},
        iii_2=page(
            f"<sup>1</sup>And the heavens and the earth were finished, and the whole "
            f"{caller(1)}world of them. And God finished on the sixth day his works.",
            footnote(1, body),
        ),
    )
    assert ccel_notes(docs["GEN"]) == {}
    # The caller's place and ordinal do not depend on whether its body is readable.
    assert [(item.key, item.reason, item.place) for item in report.left_out] == [
        ("iii_2#1", reason, "GEN 99:1 CCEL")
    ]
    assert report.left_out[0].source.startswith("<p>")


def test_a_prose_decision_answers_for_an_abbreviation_the_edition_writes_out(
    page_policy: bible.policy.Policy,
) -> None:
    def written_out(data: dict[str, Any]) -> None:
        group = next(
            g
            for g in data.values()
            if any(c.get("from") == "fut." for c in g["changes"])
        )
        group["changes"].append(
            {"note": "GEN 99:1 CCEL", "from": "fut.", "to": "future"}
        )

    docs, report = supplemented(
        changed(page_policy, "prose", written_out),
        {"GEN": genesis()},
        iii_2=page(
            f"<sup>1</sup>And the heavens and the earth were finished, and the whole "
            f"{caller(1)}world of them. And God finished on the sixth day his works.",
            footnote(1, "<i>Gr.</i> fut."),
        ),
    )
    # The note is set with its source words; the decision writes them out
    # when the notes are finished, and the printed forms are checked then.
    assert ccel_notes(docs["GEN"]) == {"GEN 99:1 CCEL": "\\fr 99:1 \\fqa Gr. \\ft fut."}
    assert not report.left_out


@pytest.mark.parametrize("prose", ["", "<i>Gr.</i> test, pl. "])
def test_a_decided_citation_accounts_only_for_its_own_abbreviations(
    page_policy: bible.policy.Policy, prose: str
) -> None:
    def decided(data: dict[str, Any]) -> None:
        data["decisions"]["GEN 99:1 CCEL"] = {
            "source": "Ps. 2. ult.",
            "passages": "PSA 2:12",
            "print": "{PSA} 2:12",
            "why": "The last verse of Psalm 2 is verse 12.",
        }

    docs, report = supplemented(
        changed(page_policy, "citations", decided),
        {"GEN": genesis()},
        test=page(
            VERSE_1.replace("world", caller(1) + "world"),
            footnote(1, prose + "See <scripref>Ps. 2. ult.</scripref>"),
        ),
    )
    if prose:
        assert report.inserted == 0
        assert [item.reason for item in report.left_out] == [
            "abbreviation in a form the edition does not print"
        ]
    else:
        assert report.inserted == 1 and report.left_out == ()
        verse = scripture.verses(docs["GEN"])["99:1"]
        assert verse.notes[0][0] == verse.text.index("world")
        assert verse.notes[0][1]["marker"] == "x"


def test_a_body_whose_caller_is_in_skipped_markup_is_left_out_and_listed(
    page_policy: bible.policy.Policy,
) -> None:
    doc = genesis()
    docs, report = supplemented(
        page_policy,
        {"GEN": doc},
        test=page(
            "<h5>" + VERSE_1.replace("world", caller(1) + "world") + "</h5>",
            footnote(1, "<i>Alex.</i> order."),
        ),
    )
    assert docs["GEN"] == doc
    assert report.bodies == 1
    assert report.inserted == report.duplicates == 0
    assert report.held == ()
    assert [(item.key, item.reason, item.place) for item in report.left_out] == [
        ("test#1", "body without a readable caller", "")
    ]
    assert report.left_out[0].text == "Alex. order."
    assert report.left_out[0].source.startswith("<p>")


@pytest.mark.parametrize(
    "body, expected",
    [
        ("<i>Gr.</i>. commit  to.", "\\fqa Gr. \\ft commit to."),
        ("<i>Or</i>, wife .", "\\fqa Or, \\ft wife."),
        ("<i>Gr.</i> found. <i>Hebraism</i>.", "\\fqa Gr. \\ft found. \\fqa Hebraism."),
        (
            "See <scripRef>Rom. 10:5</scripRef>--a parallel ?",
            "\\ft See \\xt Rom. 10. 5\\ft —a parallel?",
        ),
        (
            '<span lang="EL" class="Greek">ἐκ</span> is <i>out of</i>.',
            "\\ft ἐκ is \\fqa out of.",
        ),
        ("i.e. a wife, q.d. his own.", "\\ft i. e. a wife, q. d. his own."),
        (
            "<i>Or</i>, wife, <i>i.e</i>. spouse, <i>q.d</i>. his own.",
            "\\fqa Or, \\ft wife, \\fqa i. e. \\ft spouse, \\fqa q. d. \\ft his own.",
        ),
        (
            "<i>Gr.</i> wise. See <scripRef>Gen. 1:2 </scripRef> .",
            "\\fqa Gr. \\ft wise. See \\xt Gen. 1. 2\\ft .",
        ),
    ],
)
def test_the_transcriptions_spacing_is_mended_and_its_wording_kept(
    page_policy: bible.policy.Policy, body: str, expected: str
) -> None:
    docs, _ = supplemented(
        page_policy,
        {"GEN": genesis()},
        iii_2=page(
            f"<sup>1</sup>And the heavens and the earth were finished, and the whole "
            f"{caller(1)}world of them. And God finished on the sixth day his works.",
            footnote(1, body),
        ),
    )
    assert ccel_notes(docs["GEN"]) == {"GEN 99:1 CCEL": f"\\fr 99:1 {expected}"}


def test_a_correction_mends_a_notes_source_once_and_is_refused_unused(
    page_policy: bible.policy.Policy,
) -> None:
    files = dict(
        iii_2=page(
            f"<sup>1</sup>And the heavens and the earth were finished, and the whole "
            f"{caller(1)}world of them. And God finished on the sixth day his works.",
            footnote(1, "<i>Gr.</i> meetin."),
        )
    )
    correction = {"from": "meetin.", "to": "meeting.", "why": "a dropped letter"}
    policy = with_decisions(page_policy, corrections={"iii_2#1": correction})
    docs, _ = supplemented(policy, {"GEN": genesis()}, **files)
    assert ccel_notes(docs["GEN"]) == {
        "GEN 99:1 CCEL": "\\fr 99:1 \\fqa Gr. \\ft meeting."
    }
    with pytest.raises(CheckFailed, match="Unused CCEL note corrections"):
        supplemented(
            with_decisions(page_policy, corrections={"iii_2#9": correction}),
            {"GEN": genesis()},
            **files,
        )
    with pytest.raises(CheckFailed, match="CCEL note correction does not apply"):
        supplemented(
            with_decisions(
                page_policy, corrections={"iii_2#1": {**correction, "from": "meeting."}}
            ),
            {"GEN": genesis()},
            **files,
        )


def test_a_runs_chapter_is_found_by_its_words_whatever_the_page_says(
    page_policy: bible.policy.Policy,
) -> None:
    # The page says Exodus 3; the words are Genesis. A run of other words
    # belongs to no chapter, and its notes are listed.
    text = (
        '<h2>Exodus 3</h2><div type="Chapter" title="Exodus 3" id="iv.3">'
        f"<sup>1</sup>And the heavens and the earth were finished, and the whole "
        f"{caller(1)}world of them. And God finished on the sixth day his works "
        "which he made, and he ceased on the seventh day.</div>"
        "<h2>Chapter 4</h2><sup>1</sup>Now the serpent was the most crafty of "
        f"all the brutes on the earth, {caller(2)}which the Lord God made."
    )
    docs, report = supplemented(
        page_policy,
        {"GEN": genesis(), "EXO": book("EXO", "\\v 1 In the land of Egypt.")},
        iv_3=page(
            text, footnote(1, "<i>Or</i>, order."), footnote(2, "<i>Gr.</i> wise.")
        ),
    )
    assert list(ccel_notes(docs["GEN"])) == ["GEN 99:1 CCEL"]
    assert [(item.key, item.reason) for item in report.left_out] == [
        ("iv_3#2", "run of no chapter")
    ]


def test_a_runs_chapter_is_the_best_aligned_of_those_sharing_its_words(
    page_policy: bible.policy.Policy,
) -> None:
    # Genesis has every rarer word of the run, in another order; Exodus
    # lacks one, but its words stand in the run's order. (Two books of
    # other words give the words the three share a weight.) The chapter
    # that has most of the vocabulary is not the run's: the one the words
    # align with is.
    scrambled = " ".join(reversed(VERSE_2.split())) + "."
    exodus = VERSE_2.replace("generation", "making")
    text = f"<sup>1</sup>{VERSE_2.replace('sanctified', caller(1) + 'sanctified')}"
    docs, report = supplemented(
        page_policy,
        {
            "GEN": genesis(VERSE_1, scrambled),
            "EXO": book("EXO", f"\\v 1 {exodus}"),
            "LEV": book("LEV", "\\v 1 In the land of Egypt."),
            "NUM": book("NUM", "\\v 1 Moses numbered the tribes."),
        },
        iii_2=page(text, footnote(1, "<i>Gr.</i> hallowed.")),
    )
    assert list(ccel_notes(docs["EXO"])) == ["EXO 99:1 CCEL"]
    assert ccel_notes(docs["GEN"]) == {}
    assert report.inserted == 1 and report.left_out == ()


def test_chapters_that_align_alike_and_place_the_notes_differently_stop_the_build(
    page_policy: bible.policy.Policy,
) -> None:
    # The run's words stand whole in both books, so neither aligns better,
    # and the caller's word stands in a verse of each. The build does not
    # choose. (Two windows of one book that hold the run whole, as where a
    # run crosses eBible's chapter division, place the notes alike.)
    text = f"<sup>1</sup>{VERSE_1.replace('world', caller(1) + 'world')}"
    with pytest.raises(CheckFailed, match="CCEL run's chapter is ambiguous: iii_2"):
        supplemented(
            page_policy,
            {"GEN": genesis(), "EXO": book("EXO", f"\\v 1 {VERSE_1}")},
            iii_2=page(text, footnote(1, "<i>Or</i>, order.")),
        )


def test_a_note_that_mentions_alexandrinus_is_held_back_until_decided(
    page_policy: bible.policy.Policy,
) -> None:
    files = dict(
        iii_2=page(
            f"<sup>1</sup>And the heavens and the earth were finished, and the whole "
            f"{caller(1)}world of them. And God finished on the sixth day his works.",
            footnote(1, "<i>Alex.</i> + of them all."),
        )
    )
    docs, report = supplemented(page_policy, {"GEN": genesis()}, **files)
    assert ccel_notes(docs["GEN"]) == {}
    assert [(item.key, item.reason, item.place) for item in report.held] == [
        ("iii_2#1", "awaiting an Alexandrine decision", "GEN 99:1 CCEL")
    ]
    decided = changed(
        page_policy,
        "alexandrinus",
        lambda data: data["kept"].update(
            {
                "GEN 99:1 CCEL": {
                    "why": "A test.",
                    "swete": {
                        "volume": 1,
                        "page": 1,
                        "evidence": "silence",
                        "reading": "none",
                        "agrees": None,
                    },
                    "source_note": "\\fqa Alex. \\ft + of them all.",
                }
            }
        ),
    )
    docs, report = supplemented(decided, {"GEN": genesis()}, **files)
    assert list(ccel_notes(docs["GEN"])) == ["GEN 99:1 CCEL"]
    assert report.held == ()


def test_a_decision_leaves_a_note_out_or_places_it_where_the_words_do_not(
    page_policy: bible.policy.Policy,
) -> None:
    files = dict(
        iii_2=page(
            f"<sup>1</sup>And the heavens and the earth were finished, and the whole "
            f"{caller(1)}world of them. And God finished on the sixth day his works.",
            footnote(1, "<i>Gr.</i> order."),
        ),
        # A run of other words: the note's verse is given by decision.
        iii_3=page(
            f"<sup>1</sup>Now the serpent was the most crafty of all the brutes on "
            f"the earth, {caller(1)}which the Lord God made.",
            footnote(1, "<i>Gr.</i> wise."),
        ),
    )
    policy = with_decisions(
        page_policy,
        notes={
            "iii_2#1": {"omitted": True, "why": "A test."},
            "iii_3#1": {"verse": "GEN 99:2", "anchor": "began to do", "why": "A test."},
        },
    )
    docs, report = supplemented(policy, {"GEN": genesis()}, **files)
    assert ccel_notes(docs["GEN"]) == {
        "GEN 99:2 CCEL": "\\fr 99:2 \\fqa Gr. \\ft wise."
    }
    assert (
        "God \\f + \\fr 99:2 \\fqa Gr. \\ft wise.\\f*began to do"
        in verse_lines(docs["GEN"])["2"]
    )
    assert [(item.key, item.reason) for item in report.left_out] == [
        ("iii_2#1", "omitted by decision")
    ]
    with pytest.raises(
        CheckFailed, match="Unused CCEL note decisions: \\['iii_9#1'\\]"
    ):
        supplemented(
            with_decisions(
                page_policy, notes={"iii_9#1": {"omitted": True, "why": "A test."}}
            ),
            {"GEN": genesis()},
            **files,
        )
    with pytest.raises(CheckFailed, match="places the note as the words do"):
        supplemented(
            with_decisions(
                page_policy,
                notes={
                    "iii_2#1": {
                        "verse": "GEN 99:1",
                        "anchor": "world of them",
                        "why": "A test.",
                    }
                },
            ),
            {"GEN": genesis()},
            **files,
        )
    with pytest.raises(CheckFailed, match="anchor not met once"):
        supplemented(
            with_decisions(
                page_policy,
                notes={
                    "iii_2#1": {
                        "verse": "GEN 99:1",
                        "anchor": "his works",
                        "why": "A test.",
                    }
                },
            ),
            {"GEN": genesis()},
            **files,
        )


def test_a_decision_must_omit_or_place_and_say_why(
    page_policy: bible.policy.Policy,
) -> None:
    for decision in (
        {"why": "A test."},
        {"omitted": True, "verse": "GEN 99:1", "anchor": "world", "why": "A test."},
        {"verse": "GEN 99:1", "why": "A test."},
        {"omitted": True, "why": ""},
        {"duplicate": "", "why": "A test."},
        {"duplicate": "GEN 99:1", "omitted": True, "why": "A test."},
    ):
        with pytest.raises(CheckFailed, match="CCEL note decision"):
            with_decisions(page_policy, notes={"iii_2#1": decision})


def test_a_caller_inside_supplied_words_stands_before_them(
    page_policy: bible.policy.Policy,
) -> None:
    doc = genesis(
        "And the heavens and the earth were finished, and \\add the whole "
        "world\\add* of them. And God finished on the sixth day his works."
    )
    docs, _ = supplemented(
        page_policy,
        {"GEN": doc},
        iii_2=page(
            "<sup>1</sup>And the heavens and the earth were finished, and <i>the "
            f"whole {caller(1)}world</i> of them. And God finished on the sixth "
            "day his works.",
            footnote(1, "<i>Or</i>, order."),
        ),
    )
    assert (
        "and \\f + \\fr 99:1 \\fqa Or, \\ft order.\\f*\\add the whole world\\add* of"
        in verse_lines(docs["GEN"])["1"]
    )


def test_a_caller_stands_before_the_quotation_mark_that_opens_its_word(
    page_policy: bible.policy.Policy,
) -> None:
    doc = genesis(
        "And the heavens and the earth were finished, and he called the whole "
        "‘world’ of them. And God finished on the sixth day his works."
    )
    docs, _ = supplemented(
        page_policy,
        {"GEN": doc},
        iii_2=page(
            "<sup>1</sup>And the heavens and the earth were finished, and he "
            f"called the whole ‘{caller(1)}world’ of them. And God finished on "
            "the sixth day his works.",
            footnote(1, "<i>Or</i>, order."),
        ),
    )
    assert (
        "whole \\f + \\fr 99:1 \\fqa Or, \\ft order.\\f*‘world’ of"
        in verse_lines(docs["GEN"])["1"]
    )


@pytest.mark.parametrize(
    "font, encoded, expected",
    [
        ("SIL Galatia", b"e\xb8v", "εἰς"),
        ("SIL Galatia", b"l\xe7gos", "λόγος"),
        ("SIL Galatia", b"tequjk\xe7twn", "τεθυηκότων"),
        ("SIL Galatia", b"traumati\xf2n", "τραυματιῶν"),
        ("SIL Galatia", b"a\xc7t\xd0n.", "αὐτήν."),
        ("SIL Galatia", b"h'aliov; H'Anqrwpov", "ἅλιος· Ἄνθρωπος"),
        ("SIL Galatia", b"e&#184;v", "εἰς"),
        ("SIL Galatia", "Ὄ Θεος".encode(), "Ὄ Θεος"),
        ("SIL Galatia", "ε\u0313κ".encode(), "ἐκ"),
        ("SIL Ezra", b"\xa3wqm", "מקום"),
        ("SIL Ezra", b"(ynml&#39; ynlp).", "(פלני אלמני)."),
        ("SIL Ezra", b"hlk ySv", "עשי כלה"),
        ("SIL Ezra", b"hrwS. . . \xa3lwcm", "מצולם... שורה"),
        ("SIL Ezra", b"k m n p c", "ץ ף ן ם ך"),
        ("SIL Ezra", b"\xa2 \xa3 \xa4 \xa5 \xa6", "ץ ף ן ם ך"),
        ("SIL Ezra", "שָׁלוֹם עולם".encode(), "שָׁלוֹם עולם"),
    ],
)
def test_legacy_font_bytes_and_entities_are_decoded_before_utf8_loss(
    font: str,
    encoded: bytes,
    expected: str,
) -> None:
    data = page("", footnote(1, f'<FONT FACE="{font}">PLACEHOLDER</FONT>'))
    data = data.replace(b"PLACEHOLDER", encoded)
    original = pages(test=data)
    _, bodies, _ = ccel.read_pages(original, {})
    body = bodies["test#1"]
    assert body.problem is None
    assert body.text == expected
    assert unicodedata.is_normalized("NFC", body.text)
    assert f'face="{font}"' in body.source
    if encoded == b"e\xb8v":
        assert "e\xb8v" in body.source and "εἰς" not in body.source
    assert data == next(iter(original.glob("*.htm"))).read_bytes()


@pytest.mark.parametrize(
    "body, reason",
    [
        (
            b'<font face="SIL Galatia">\xff\x01V</font>',
            "undecodable SIL Galatia characters",
        ),
        (b'<font face="SIL Ezra">\x80</font>', "undecodable SIL Ezra characters"),
        (b'<font face="SIL Galatia">\xef\xbf\xbd</font>', "undecodable characters"),
        (b"Greek outside a font: \xb8", "undecodable characters"),
    ],
)
def test_damaged_input_is_still_listed(body: bytes, reason: str) -> None:
    data = page("", footnote(1, "PLACEHOLDER")).replace(b"PLACEHOLDER", body)
    _, bodies, _ = ccel.read_pages(pages(test=data), {})
    assert bodies["test#1"].problem == reason


def test_decoded_notes_are_inserted_without_changing_supplied_documents(
    page_policy: bible.policy.Policy,
) -> None:
    doc = genesis()
    before = copy.deepcopy(doc)
    data = (
        page(
            f"<sup>1</sup>And the heavens and the earth were finished, and the whole "
            f"{caller(1)}world of them. And God finished on the sixth day his works.",
            footnote(
                1,
                '<i>Gr.</i> <span><font face="SIL Galatia">GREEK</font></span>'
                ' means <i>of the wounded</i>; Heb. <font face="SIL Ezra">HEBREW</font>.',
            ),
        )
        .replace(b"GREEK", b"traumati\xf2n")
        .replace(b"HEBREW", b"\xa3wqm")
    )
    docs, report = supplemented(page_policy, {"GEN": doc}, test=data)
    assert doc == before
    assert (
        scripture.verses(docs["GEN"])["99:1"].text == scripture.verses(doc)["99:1"].text
    )
    assert report.inserted == 1 and report.left_out == ()
    note = ccel_notes(docs["GEN"])["GEN 99:1 CCEL"]
    assert "τραυματιῶν" in note and "מקום" in note and "of the wounded" in note


def test_the_real_pages_supply_the_notes_ebible_lacks(
    read: bible.pipeline.Read,
    sources: bible.sources.Sources,
    declared: bible.policy.Policy,
) -> None:
    # Decoding retains the pinned transcription's slips; corrections are separate.
    _, bodies, _ = ccel.read_pages(sources.ccel, {})
    recovered = [body for body in bodies.values() if "<font" in body.source]
    assert len(recovered) == 47
    assert all(body.problem is None for body in recovered)
    assert "τεθυηκότων and τραυματιῶν" in bodies["1#7"].text
    assert "τεθνηκότων" not in bodies["1#7"].text
    assert "פלני אלמני" in bodies["1.xxi#2"].text
    assert "Ό Θεος" in bodies["iii.49#1"].text
    assert [
        (item.key, item.place, item.text)
        for item in read.ccel.held
        if "<font" in item.source
    ] == []
    assert any(
        item.key == "iii#6" and item.reason == "omitted by decision"
        for item in read.ccel.left_out
    )
    report = read.ccel
    assert (report.pages, report.bodies) == (708, 4116)
    assert report.inserted == 1827
    assert report.duplicates == 2214
    assert len(report.held) == 0
    assert len(report.left_out) == 69
    assert {
        item.key: item.retained
        for item in report.matched
        if item.key in {"1.xvii#8", "1.xvii#12"}
    } == {"1.xvii#8": "1SA 17:40", "1.xvii#12": "1SA 17:49"}
    # A note that a decision sets in another verse is the same note there.
    assert [
        (item.place, item.retained) for item in report.matched if item.key == "2.xi#5"
    ] == [("2KI 11:7 CCEL", "2KI 11:9")]
    # The Alexandrine note that was once unreadable is decided, not left out.
    assert "JER 52:32 CCEL" in declared.alexandrinus["readings"]
    assert not any(item.key == "13.lii#10" for item in report.left_out)
    reasons = sorted({item.reason for item in report.left_out})
    assert reasons == [
        "a letter standing for a note set elsewhere",
        "abbreviation in a form the edition does not print",
        "caller the words do not place",
        "caller without a body",
        "empty",
        "omitted by decision",
        "undecodable characters",
    ]
    # The Appendix's notes on supplied verses wait for promotion to supply them.
    assert len(report.deferred) == 8
    assert report.bodies == (
        report.inserted
        + report.duplicates
        + len(report.held)
        + len(report.deferred)
        + len(report.left_out)
        - sum(item.reason == "caller without a body" for item in report.left_out)
    )
    # eBible's own notes keep their keys and words.
    keys = [
        note["x-key"]
        for doc in read.brenton.values()
        for note in usj.notes_of(doc["content"])
        if "x-key" in note
    ]
    assert len(keys) == len(set(keys))
    assert sum("CCEL" in k for k in keys) == report.inserted
    # A note of Leviticus, which eBible has no notes in.
    lev = scripture.verses(read.brenton["LEV"])["4:2"]
    assert [(at, usj.serialize(n["content"])) for at, n in lev.notes] == [
        (lev.text.index("in any of"), "\\fr 4:2 \\fqa Gr. \\ft from.")
    ]
    assert not any(
        re.search(r"\\(it|add)", usj.serialize(n["content"]))
        for doc in read.brenton.values()
        for n in usj.notes_of(doc["content"])
        if "CCEL" in n.get("x-key", "")
    )


def test_the_review_counts_the_notes_set_after_promotion(
    read: bible.pipeline.Read, edition: bible.pipeline.Edition
) -> None:
    # The notes waiting at Read are set once promotion supplies their verses,
    # and the review reports the edition's count, not Read's.
    report = edition.ccel
    assert report.deferred == ()
    assert len(report.supplied) == len(read.ccel.deferred) == 8
    assert {key for key, _ in report.supplied} == {
        body.key for body in read.ccel.deferred
    }
    assert report.inserted == read.ccel.inserted + 8
    printed = {
        note["x-key"]
        for rows in edition.documents.values()
        for note in usj.notes_of(rows["content"])
        if "x-key" in note
    }
    assert all(key in printed for _, key in report.supplied)
    text = review.ccel_report(report)
    assert f"Notes set in Brenton's verses: {report.inserted}, 8 of them" in text
    assert all(f"`{key}` as `{printed}`" in text for key, printed in report.supplied)


@pytest.mark.parametrize(
    "key, reference, lemma, note",
    [
        ("2SA 19:43 CCEL", "19:42", "all the men", "Gr. _every man_"),
        ("LEV 6:14 CCEL#2", "6:14", "in rolls", "Gr. _rolled_, plural"),
        (
            "JER 11:15 CCEL",
            "11:15",
            "holy offerings",
            "Gr. _holy flesh_, plural",
        ),
        (
            "JER 8:2 CCEL",
            "8:2",
            "spread",
            "lit. _cool_ or _refresh_. See 2 Kgdms. 17:19.",
        ),
        (
            "MIC 7:18 CCEL",
            "7:18",
            "for a testimony",
            "vide supra, Prov. 29:14; Amos 1:11",
        ),
        (
            "EZK 3:20 CCEL",
            "3:20",
            "punishment",
            "lit. _torment_. Βάσανος in Old Testament seems to signify _punishment_, "
            "as κόλασις in New Testament does _torment_, 1 John 4:18.",
        ),
        ("ZEP 3:7 CCEL", "3:7", "receive instruction", "see Ps. 2:12"),
    ],
)
def test_recovered_notes_keep_their_callers_renderings_and_commentary(
    edition: bible.pipeline.Edition,
    key: str,
    reference: str,
    lemma: str,
    note: str,
) -> None:
    rows = [
        row for group in edition.notes.values() for row in group if row["key"] == key
    ]
    assert len(rows) == 1
    row = rows[0]
    assert (row["reference"], row["lemma"], row["note"]) == (reference, lemma, note)


def test_a_spelling_note_made_inapplicable_by_normalization_is_omitted(
    edition: bible.pipeline.Edition,
) -> None:
    assert any(
        item.key == "4.xxvii#1" and item.reason == "omitted by decision"
        for item in edition.ccel.left_out
    )
    assert not any(row["key"] == "2CH 27:1 CCEL" for row in edition.notes["2CH"])
    assert "Joatham" in scripture.verses(edition.documents["2CH"])["26:21"].text


def test_recovered_lexical_quotations_are_not_whole_lemma_alternatives(
    edition: bible.pipeline.Edition,
) -> None:
    verses = scripture.verses(edition.documents["JER"])
    note = next(
        note for _, note in verses["8:2"].notes if note.get("x-key") == "JER 8:2 CCEL"
    )
    assert not any(usj.is_type(node, "char", "fqa") for node in note["content"])
    assert "cool" in usj.serialize(note["content"])


@pytest.mark.parametrize(
    "existing, supplemental",
    [
        ("Gr. seed of men.", "<i>Gr.</i> before."),
        ("Gr. cut.", "<i>Gr.</i> eat."),
        ("Gr. νυμφαγωγός.", "<i>Gr.</i> νυμφαγωγός. See John 1. 10."),
        ("Gr. τεθνηκότων.", "<i>Gr.</i> τεθυηκότων."),
        # An accent is not punctuation.
        ("Gr. ἀπάντημα.", "<i>Gr.</i> ἀπαντῆμα."),
        ("Heb. תחתו.", "<i>Heb.</i> החהי."),
        ("Gr. a covenant.", "<i>Gr.</i> a covenant. Heb. and Alex. omit."),
    ],
)
def test_different_words_are_never_automatic_duplicates(
    page_policy: bible.policy.Policy, existing: str, supplemental: str
) -> None:
    doc = genesis(VERSE_1.replace("world", f"\\f + \\fr 99:1 \\ft {existing}\\f*world"))
    docs, report = supplemented(
        page_policy,
        {"GEN": doc},
        test=page(
            VERSE_1.replace("world", caller(1) + "world"), footnote(1, supplemental)
        ),
    )
    assert report.duplicates == 0
    assert report.inserted + len(report.held) + len(report.left_out) == 1
    assert not report.matched


def test_identical_text_at_another_word_is_a_separate_note(
    page_policy: bible.policy.Policy,
) -> None:
    doc = genesis(
        VERSE_1.replace("heavens", "\\f + \\fr 99:1 \\ft Gr. order.\\f*heavens")
    )
    docs, report = supplemented(
        page_policy,
        {"GEN": doc},
        test=page(
            VERSE_1.replace("world", caller(1) + "world"),
            footnote(1, "<i>Gr.</i> order."),
        ),
    )
    assert report.duplicates == 0
    assert report.inserted == 1


def test_distinct_callers_within_one_style_are_not_duplicates(
    page_policy: bible.policy.Policy,
) -> None:
    doc = genesis(
        VERSE_1.replace(
            "the whole world",
            "\\add the \\f + \\fr 99:1 \\ft Gr. order.\\f*whole world\\add*",
        )
    )
    _, report = supplemented(
        page_policy,
        {"GEN": doc},
        test=page(
            VERSE_1.replace("world", caller(1) + "world"),
            footnote(1, "<i>Gr.</i> order."),
        ),
    )
    assert report.duplicates == 0
    assert report.inserted == 1


def test_nfc_and_typographic_quotes_preserve_the_same_note(
    page_policy: bible.policy.Policy,
) -> None:
    doc = genesis(VERSE_1.replace("world", "\\f + \\fr 99:1 \\ft Gr. “ἐκ”.\\f*world"))
    docs, report = supplemented(
        page_policy,
        {"GEN": doc},
        test=page(
            VERSE_1.replace("world", caller(1) + "world"),
            footnote(1, 'Gr. "ε\u0313κ".'),
        ),
    )
    assert report.duplicates == 1
    assert report.matched[0].retained == "GEN 99:1"
    assert report.inserted == 0


@pytest.mark.parametrize(
    "existing, supplemental",
    [
        ("Gr. order.", "<i>Gr.</i> order"),
        ("Gr. Lit. them (sc. bloods) meet.", "<i>Gr. lit.</i> them, sc. bloods, meet."),
        ("Gr. bruise. 1 Pet. 2. 24.", "<i>Gr.</i> bruise. 1 Pe. 2. 24."),
        ("See Isa. 34. 13.", "See Is. 34. 13."),
    ],
)
def test_a_difference_of_punctuation_capitals_or_citation_form_is_the_same_note(
    page_policy: bible.policy.Policy, existing: str, supplemental: str
) -> None:
    doc = genesis(VERSE_1.replace("world", f"\\f + \\fr 99:1 \\ft {existing}\\f*world"))
    _, report = supplemented(
        page_policy,
        {"GEN": doc},
        test=page(
            VERSE_1.replace("world", caller(1) + "world"), footnote(1, supplemental)
        ),
    )
    assert report.duplicates == 1 and report.inserted == 0
    assert report.matched[0].reason.startswith("Same words at the same caller word")


def test_declared_duplicate_names_its_existing_note_and_cannot_go_stale(
    page_policy: bible.policy.Policy,
) -> None:
    doc = genesis(VERSE_1.replace("world", "\\f + \\fr 99:1 \\ft Gr. order.\\f*world"))
    files = {
        "test": page(
            VERSE_1.replace("world", caller(1) + "world"),
            footnote(1, "<i>Gr.</i> ordr."),
        )
    }
    declared = with_decisions(
        page_policy,
        notes={
            "test#1": {
                "duplicate": "GEN 99:1",
                "why": "Same printed note; CCEL drops a letter.",
            }
        },
    )
    docs, report = supplemented(declared, {"GEN": doc}, **files)
    assert report.duplicates == 1
    assert report.matched[0].reason == declared.ccel_notes["notes"]["test#1"]["why"]
    with pytest.raises(CheckFailed, match="target not met once"):
        supplemented(
            with_decisions(
                page_policy,
                notes={"test#1": {"duplicate": "GEN 99:2", "why": "A test."}},
            ),
            {"GEN": doc},
            **files,
        )
    files["test"] = page(
        VERSE_1.replace("world", caller(1) + "world"), footnote(1, "<i>Gr.</i> order.")
    )
    with pytest.raises(CheckFailed, match="matches automatically"):
        supplemented(declared, {"GEN": doc}, **files)


def test_dispositions_do_not_renumber_later_candidates(
    page_policy: bible.policy.Policy,
) -> None:
    files = {
        "test": page(
            VERSE_1.replace("world", caller(1) + "world").replace(
                "ceased", caller(2) + "ceased"
            ),
            footnote(1, "<i>Gr.</i> order."),
            footnote(2, "<i>Gr.</i> rested."),
        )
    }
    original = genesis()
    docs, _ = supplemented(page_policy, {"GEN": original}, **files)
    assert "GEN 99:1 CCEL#2" in ccel_notes(docs["GEN"])
    duplicate = genesis(
        VERSE_1.replace("world", "\\f + \\fr 99:1 \\ft Gr. order.\\f*world")
    )
    docs, _ = supplemented(page_policy, {"GEN": duplicate}, **files)
    assert list(ccel_notes(docs["GEN"])) == ["GEN 99:1 CCEL#2"]
    omitted = with_decisions(
        page_policy, notes={"test#1": {"omitted": True, "why": "A test."}}
    )
    docs, _ = supplemented(omitted, {"GEN": original}, **files)
    assert list(ccel_notes(docs["GEN"])) == ["GEN 99:1 CCEL#2"]


def test_recovering_an_unreadable_body_does_not_renumber_later_notes(
    page_policy: bible.policy.Policy,
) -> None:
    files = {
        "test": page(
            VERSE_1.replace("world", caller(1) + "world").replace(
                "ceased", caller(2) + "ceased"
            ),
            footnote(1, '<font face="Unknown">abc</font>'),
            footnote(2, "<i>Gr.</i> rested."),
        )
    }
    docs, report = supplemented(page_policy, {"GEN": genesis()}, **files)
    assert list(ccel_notes(docs["GEN"])) == ["GEN 99:1 CCEL#2"]
    assert report.left_out[0].place == "GEN 99:1 CCEL"
    corrected = with_decisions(
        page_policy,
        corrections={
            "test#1": {
                "from": '<font face="Unknown">abc</font>',
                "to": "Gr. order.",
                "uncategorized": True,
                "why": "A test.",
            }
        },
    )
    docs, _ = supplemented(corrected, {"GEN": genesis()}, **files)
    assert list(ccel_notes(docs["GEN"])) == ["GEN 99:1 CCEL", "GEN 99:1 CCEL#2"]


def test_an_excluded_duplicate_book_cannot_receive_recovered_notes(
    page_policy: bible.policy.Policy,
) -> None:
    # The manifest assembles Nehemias from EZR, and excludes the duplicate NEH.
    docs, report = supplemented(
        page_policy,
        {"NEH": book("NEH", f"\\v 1 {VERSE_1}"), "GEN": genesis()},
        test=page(
            VERSE_1.replace("world", caller(1) + "world"),
            footnote(1, "<i>Gr.</i> order."),
        ),
    )
    assert report.inserted == 1
    assert not ccel_notes(docs["NEH"])
    assert list(ccel_notes(docs["GEN"])) == ["GEN 99:1 CCEL"]


def test_unclosed_heading_and_center_preserve_scripture_callers(
    page_policy: bible.policy.Policy,
) -> None:
    text = (
        "<h5>Printed heading<center>Printed gloss band"
        f'<p><sup>1</sup>{VERSE_1.replace("sixth", caller(1) + "sixth")}</p>'
        f"<p><sup>2</sup>{VERSE_2}</p>"
        "</center></h5>"
    )
    docs, report = supplemented(
        page_policy, {"GEN": genesis()}, test=page(text, footnote(1, "Or, seventh."))
    )
    assert report.inserted == 1
    assert report.left_out == ()
    assert "Printed" not in " ".join(
        word
        for run in ccel.read_pages(pages(test=page(text)), {})[0]
        for word in run.words
    )
    assert "GEN 99:1 CCEL" in ccel_notes(docs["GEN"])


@pytest.mark.parametrize("orphan", [False, True])
@pytest.mark.parametrize("label", ["Alex", "Appendix"])
def test_unreadable_alexandrinus_body_requires_correction(
    page_policy: bible.policy.Policy, orphan: bool, label: str
) -> None:
    text = (
        f"<p><sup>1</sup>{VERSE_1}</p>"
        if orphan
        else (f'<p><sup>1</sup>{VERSE_1.replace("sixth", caller(1) + "sixth")}</p>')
    )
    data = page(text, footnote(1, f"<i>{label}</i>. + �the thrones of.�"))
    with pytest.raises(
        CheckFailed, match=r"Unreadable Alexandrinus/Appendix CCEL note test#1"
    ):
        supplemented(page_policy, {"GEN": genesis()}, test=data)


def deferred_note(
    page_policy: bible.policy.Policy,
) -> tuple[bible.policy.Policy, dict[str, Document], ccel.Report]:
    declared = with_decisions(
        page_policy,
        notes={
            "test#1": {
                "verse": "GEN 99:3",
                "anchor": "sixth",
                "supplied": True,
                "why": "The printed note belongs to the supplied third verse.",
            }
        },
    )
    data = page("", footnote(1, "Or, seventh."))
    docs, report = supplemented(declared, {"GEN": genesis()}, test=data)
    return declared, docs, report


def test_ccel_note_waits_for_its_supplied_verse(
    page_policy: bible.policy.Policy,
) -> None:
    declared, docs, report = deferred_note(page_policy)
    assert len(report.deferred) == 1
    assert report.inserted == 0 and not report.left_out
    before = copy.deepcopy(docs)
    promoted = {
        "GEN": book("GEN", f"\\v 1 {VERSE_1}\n\\v 2 {VERSE_2}\n\\v 3 {VERSE_1}")
    }
    result, finished = ccel.supplied(promoted, report, declared)
    assert list(ccel_notes(result["GEN"])) == ["GEN 99:3 CCEL"]
    assert finished.inserted == 1 and not finished.deferred
    assert finished.supplied == (("test#1", "GEN 99:3 CCEL"),)
    assert docs == before and not ccel_notes(promoted["GEN"])


def test_supplied_ccel_note_rejects_a_key_another_note_has(
    page_policy: bible.policy.Policy,
) -> None:
    declared, _, report = deferred_note(page_policy)
    promoted = book(
        "GEN", f"\\v 1 {VERSE_1}\\f + \\fr 99:1 \\ft Or, other.\\f*\n\\v 3 {VERSE_1}"
    )
    # A note promotion moved, keyed at the verse the supplied note takes.
    (moved,) = usj.notes_of(promoted["content"])
    moved["x-key"] = "GEN 99:3 CCEL"
    with pytest.raises(
        CheckFailed, match="takes a key another note has: GEN 99:3 CCEL"
    ):
        ccel.supplied({"GEN": promoted}, report, declared)


@pytest.mark.parametrize("target", ["", VERSE_1 + " " + VERSE_1])
def test_supplied_ccel_note_rejects_missing_or_ambiguous_target(
    page_policy: bible.policy.Policy, target: str
) -> None:
    declared, _, report = deferred_note(page_policy)
    doc = book("GEN", f"\\v 1 {VERSE_1}" + (f"\n\\v 3 {target}" if target else ""))
    with pytest.raises(
        CheckFailed, match="CCEL note (decision names no verse|anchor not met once)"
    ):
        ccel.supplied({"GEN": doc}, report, declared)


def test_supplied_ccel_note_rejects_words_present_before_promotion(
    page_policy: bible.policy.Policy,
) -> None:
    declared, _, _ = deferred_note(page_policy)
    doc = book("GEN", f"\\v 1 {VERSE_1}\n\\v 3 {VERSE_1}")
    with pytest.raises(CheckFailed, match="already has its words before promotion"):
        supplemented(declared, {"GEN": doc}, test=page("", footnote(1, "Or, seventh.")))


def test_supplied_ccel_note_waits_for_words_added_to_an_existing_verse(
    page_policy: bible.policy.Policy,
) -> None:
    declared = with_decisions(
        page_policy,
        notes={
            "test#1": {
                "verse": "GEN 99:2",
                "anchor": "sixth",
                "supplied": True,
                "why": "The printed note belongs to words promotion adds to the verse.",
            }
        },
    )
    docs, report = supplemented(
        declared, {"GEN": genesis()}, test=page("", footnote(1, "Or, seventh."))
    )
    assert len(report.deferred) == 1 and report.inserted == 0
    promoted = {"GEN": genesis(verse_2=f"{VERSE_2} {VERSE_1}")}
    result, finished = ccel.supplied(promoted, report, declared)
    assert list(ccel_notes(result["GEN"])) == ["GEN 99:2 CCEL"]
    assert finished.inserted == 1 and not finished.deferred


def test_a_supplied_note_is_numbered_after_every_note_placed_in_its_verse(
    page_policy: bible.policy.Policy,
) -> None:
    declared = with_decisions(
        page_policy,
        notes={
            "test#1": {"omitted": True, "why": "The edition leaves it out."},
            "test#2": {
                "verse": "GEN 99:2",
                "anchor": "sixth",
                "supplied": True,
                "why": "The printed note belongs to words promotion adds to the verse.",
            },
        },
    )
    text = f"<sup>1</sup>{VERSE_1}<sup>2</sup> " + VERSE_2.replace(
        "generation", caller(1) + "generation"
    )
    _, report = supplemented(
        declared,
        {"GEN": genesis()},
        test=page(text, footnote(1, "<i>Gr.</i> births."), footnote(2, "Or, seventh.")),
    )
    assert [(item.key, item.place) for item in report.left_out] == [
        ("test#1", "GEN 99:2 CCEL")
    ]
    # The key the left-out note took is not given to another.
    promoted = {"GEN": genesis(verse_2=f"{VERSE_2} {VERSE_1}")}
    result, finished = ccel.supplied(promoted, report, declared)
    assert list(ccel_notes(result["GEN"])) == ["GEN 99:2 CCEL#2"]
    assert finished.supplied == (("test#2", "GEN 99:2 CCEL#2"),)


def test_corrected_alexandrinus_note_is_held_for_a_decision(
    page_policy: bible.policy.Policy,
) -> None:
    declared = with_decisions(
        page_policy,
        corrections={
            "test#1": {
                "from": "�the thrones of.�",
                "to": "“the thrones of.”",
                "why": "Restore the quotation marks verified in print.",
                "uncategorized": True,
            }
        },
    )
    text = f'<p><sup>1</sup>{VERSE_1.replace("sixth", caller(1) + "sixth")}</p>'
    _, report = supplemented(
        declared,
        {"GEN": genesis()},
        test=page(text, footnote(1, "<i>Alex</i>. + �the thrones of.�")),
    )
    assert [(item.key, item.place) for item in report.held] == [
        ("test#1", "GEN 99:1 CCEL")
    ]
    assert not report.left_out and report.inserted == 0


@pytest.mark.parametrize("supplied", [False, "true"])
def test_supplied_ccel_policy_requires_explicit_true(
    page_policy: bible.policy.Policy,
    supplied: object,
) -> None:
    with pytest.raises(CheckFailed, match="neither omits, duplicates nor places"):
        with_decisions(
            page_policy,
            notes={
                "test#1": {
                    "verse": "GEN 99:3",
                    "anchor": "sixth",
                    "supplied": supplied,
                    "why": "The target verse is supplied during promotion.",
                }
            },
        )


def test_a_last_verse_citation_is_readable_before_alexandrine_disposition() -> None:
    body = ccel.read_body(
        "test#1",
        html.fragment_fromstring(
            "<p>So <i>Vat. i. e.</i> Ναζίρ, but <i>Alex.</i> nearer to reading in "
            '<scripref passage="Matthew 2:23">Matt. 2. ult.</scripref> Ναζειραῖον.</p>'
        ),
        "Printed note with a last-verse citation",
    )
    assert body.problem is None
    assert "Matt. 2. ult." in body.text


def test_a_verified_placement_can_name_a_duplicate_in_its_destination(
    page_policy: bible.policy.Policy,
) -> None:
    doc = genesis(VERSE_1.replace("world", r"\f + \fr 99:1 \ft Gr. order.\f*world"))
    decision = {
        "verse": "GEN 99:1",
        "anchor": "world",
        "duplicate": "GEN 99:1",
        "why": "The source caller is displaced; the verified destination already has this note.",
    }
    docs, report = supplemented(
        with_decisions(page_policy, notes={"test#1": decision}),
        {"GEN": doc},
        test=page(
            VERSE_2.replace("generation", caller(1) + "generation"),
            footnote(1, "<i>Gr.</i> ordr."),
        ),
    )
    assert report.inserted == 0 and report.duplicates == 1
    assert report.matched[0].retained == "GEN 99:1"
    assert not ccel_notes(docs["GEN"])
    assert docs["GEN"] == doc


def test_a_number_stop_across_style_boundaries_remains_unreadable() -> None:
    source = "<p>After 4. <i>in</i> this verse.</p>"
    body = ccel.read_body("test#1", html.fragment_fromstring(source), source)
    assert body.problem == "a number with a period within a sentence"
