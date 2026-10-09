"""The pipeline whole: its order, what it refuses, and what it sends to be
typeset."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from conftest import changed

import bible.pipeline
import bible.policy
import bible.sources
from bible import (
    annotate,
    assembly,
    paths,
    pipeline,
    places,
    review,
    revision,
    scripture,
    terminology,
    usj,
)
from bible.checks import CheckFailed
from bible.usj import Document


def test_the_edition_prints_every_unit_once_in_the_manifests_order(
    edition: bible.pipeline.Edition,
    policy: bible.policy.Policy,
    exported: dict[str, str],
) -> None:
    order = [entry["id"] for entry in policy.entries]
    assert list(edition.documents) == list(exported) == order
    assert edition.scripture == {unit["id"] for unit in policy.scripture}
    assert edition.authored == {"CNC", "XXA", "XXF", "XXG", "GLO", "XXC"}
    # Each is written under its own id, whatever file it was printed from.
    assert all(text.startswith(f"\\id {code}") for code, text in exported.items())
    assert dict(edition.summary) == {
        "alexandrine_notes": 198,
        "alexandrine_appendix_paragraphs": 26,
        "byzantine_units": 1939,
        "byzantine_edits": 859,
        "kjv_corrections": 75,
        "byzantine_notes": 867,
        "scripture_units": 78,
        "brenton_units": 51,
        "kjv_units": 27,
        "kjv_marginal_notes": 775,
        "printed_notes": 4272,
        # The King James Bible's, less the four verses the Byzantine text
        # lacks and the empty chapter eBible left in Proverbs.
        "verses": 36604,
    }


def test_no_stage_changes_what_an_earlier_stage_made(
    sources: bible.sources.Sources,
    policy: bible.policy.Policy,
    read: bible.pipeline.Read,
) -> None:
    """Documents are shared between stages, so none may be changed in place."""
    before = copy.deepcopy((dict(read.brenton), dict(read.kjv)))
    promoted = pipeline.promote(
        read, policy, sources.byzantine, terminology.registry(policy)
    )
    kept = copy.deepcopy((dict(promoted.brenton), dict(promoted.kjv)))
    units = pipeline.assemble(promoted, policy, sources)
    assembled = copy.deepcopy(dict(units))
    ctx = pipeline.context(units, policy, sources)
    _, introductions, _ = pipeline.front_and_back(read, ctx, sources)
    pipeline.annotated(units, read, introductions, ctx)
    assert (dict(read.brenton), dict(read.kjv)) == before
    assert (dict(promoted.brenton), dict(promoted.kjv)) == kept
    assert dict(units) == assembled


def test_the_policy_is_read_once_and_cannot_be_changed(
    policy: bible.policy.Policy,
) -> None:
    with pytest.raises(TypeError):
        cast(dict[str, Any], policy.manifest)["title"] = "Another"
    with pytest.raises(TypeError):
        cast(dict[str, Any], policy.brenton_notes["notes"]["GEN 1:9#2"])[
            "lemma"
        ] = "other words"
    for entry in policy.entries:
        if "file" in entry:
            with pytest.raises(TypeError):
                cast(dict[str, Any], entry)["id"] = "XYZ"
    # A test declares another policy; the one it started from is as it was.
    other = changed(policy, "sample", lambda data: data.pop("GEN"))
    assert "GEN" in policy.sample and "GEN" not in other.sample


@pytest.mark.parametrize(
    "name, change, refusal",
    [
        (
            "brenton_notes",
            lambda d: d["notes"]["GEN 1:9#2"].update(lema="place"),
            "missing or unknown fields",
        ),
        (
            "kjv_notes",
            lambda d: d["notes"]["MAT 6:1 of"].update(why=""),
            "without a why",
        ),
        (
            "sample",
            lambda d: d.update(XYZ=[1]),
            "Sample names units outside the edition",
        ),
        (
            "manifest",
            lambda d: d["scripture"][0].update(section="middle_testament"),
            "outside both testaments",
        ),
        (
            "prose",
            lambda d: d["numbers"]["changes"].append(
                {"unit": "GEN", "from": "In the beginning", "to": "At first"}
            ),
            "no front or back matter",
        ),
        (
            "manifest",
            lambda d: d["scripture"][0].update(short_titel="Genesis"),
            "Manifest scripture.*GEN.*missing or unknown fields",
        ),
        (
            "manifest",
            lambda d: d["front_matter"][0].update(short_titel="Front matter"),
            "Manifest front_matter.*missing or unknown fields",
        ),
        (
            "citations",
            lambda d: d["names"].update(
                XYZ=[{"from": "Never present", "to": "{GEN}", "why": "x"}]
            ),
            "Unused citation name changes.*XYZ",
        ),
        (
            "citations",
            lambda d: d["names"]["BAK"][0].update(whyy="x"),
            "Citation name change BAK has missing or unknown fields",
        ),
        (
            "prose",
            lambda d: d.update(
                probe={
                    "why": "x",
                    "changes": [
                        {
                            "unit": "XXB",
                            "from": "introduction may be necessary",
                            "to": "introduction may be necessary",
                        }
                    ],
                }
            ),
            "Prose change that changes nothing: probe: XXB",
        ),
        (
            "prose",
            lambda d: d["numbers"]["changes"][0].update(to="5."),
            "Prose change that changes nothing: numbers: MAT 18:28 pence",
        ),
        (
            "prose",
            lambda d: d["numbers"]["changes"].append({"from": "5.", "to": "five"}),
            "neither a note nor a unit",
        ),
    ],
)
def test_a_malformed_decision_is_refused_when_the_policy_is_read(
    policy: bible.policy.Policy,
    name: str,
    change: Callable[[dict[str, Any]], object],
    refusal: str,
) -> None:
    with pytest.raises(CheckFailed, match=refusal):
        changed(policy, name, change)


def test_a_decision_that_nothing_meets_is_refused(
    edition: bible.pipeline.Edition, policy: bible.policy.Policy
) -> None:
    reports = [
        annotate.Report(
            keys={row["key"] for rows in edition.notes.values() for row in rows},
            edited=[
                change["note"]
                for group in policy.prose.values()
                for change in group["changes"]
                if "note" in change
            ],
        )
    ]
    annotate.check_notes(policy, reports)
    pipeline.check_met(policy, edition.met)

    def exception(data: dict[str, Any]) -> None:
        data["notes"]["GEN 1:1"] = {
            "lemma": "beginning",
            "why": "there is no such note",
        }

    with pytest.raises(
        CheckFailed, match=r"Unused Brenton note exceptions: \['GEN 1:1'\]"
    ):
        annotate.check_notes(changed(policy, "brenton_notes", exception), reports)

    def prose(data: dict[str, Any]) -> None:
        data["numbers"]["changes"].append(
            {"note": "GEN 1:4", "from": "5.", "to": "five"}
        )

    with pytest.raises(CheckFailed, match="Prose changes to notes not met once each"):
        annotate.check_notes(changed(policy, "prose", prose), reports)

    def decision(data: dict[str, Any]) -> None:
        data["decisions"]["GEN 1:1"] = {
            "source": "Heb. 1",
            "not_a_citation": True,
            "why": "x",
        }

    with pytest.raises(CheckFailed, match=r"Unused citation decisions: \['GEN 1:1'\]"):
        pipeline.check_met(changed(policy, "citations", decision), edition.met)

    def name(data: dict[str, Any]) -> None:
        data["dialects"]["brenton"]["books"]["Jezek"] = "EZK"

    with pytest.raises(CheckFailed, match="Unused names for books"):
        pipeline.check_met(changed(policy, "citations", name), edition.met)


def test_the_editions_spelling_is_revised_wherever_a_word_is_printed(
    edition: bible.pipeline.Edition, policy: bible.policy.Policy
) -> None:
    words = policy.revisions["words"]
    assert words["Jezekiel"]["to"] == "Ezekiel"
    assert edition.met["revisions"] == (
        set(words)
        | set(policy.revisions["punctuation"])
        | {c["verse"] for c in revision.verse_changes(policy)}
        | {
            (c.get("note", c.get("unit")), c["from"])
            for c in revision.passage_changes(policy)
        }
    )
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, words)) + r")(?!\w)")
    # The editor's own pages name the sources' books, rather than respelling
    # the translations: the introduction explains Brenton's names, and the
    # table names the KJV's.
    source_names = {
        "CNC": ["Nehemiah", "Osee", "Naum"],
        "XXA": ["Nehemiah", "Nehemiah"],
    }
    for code, doc in edition.documents.items():
        assert pattern.findall(usj.serialize(doc)) == source_names.get(code, []), code
    ezekiel = usj.serialize(edition.documents["EZK"])
    assert "the word of the Lord came to Ezekiel the priest" in ezekiel
    assert "And Ezekiel shall be for a sign to you" in ezekiel


NOE = (
    "\\id GEN\n\\mt1 NOE\n\\c 1\n\\p\n\\v 1 Noe’s sons and Noeman "
    "\\f - \\fr 1:1 \\fq went with Noe: \\ft or, \\fqa Noe\\f*went \\add with\\add* Noe.\n"
    "\\v 2 And Noe went.\n"
)


def revisions(
    policy: bible.policy.Policy, **sections: dict[str, Any]
) -> bible.policy.Policy:
    def change(data: dict[str, Any]) -> None:
        data.update(words={}, verses={}, passages={}, punctuation={})
        data.update(sections)

    return changed(policy, "revisions", change)


def test_a_word_is_respelt_whole_in_the_text_and_its_notes(
    policy: bible.policy.Policy,
) -> None:
    words = revisions(policy, words={"Noe": {"to": "Noah", "why": "the English name"}})
    met: revision.MetRevisions = set()
    text = usj.serialize(revision.respelt(usj.parse(NOE), words, met))
    assert (
        "\\v 1 Noah’s sons and Noeman \\f - \\fr 1:1 \\fq went with Noah: \\ft or, "
        "\\fqa Noah\\f*went \\add with\\add* Noah.\n\\v 2 And Noah went.\n"
    ) in text
    assert "\\mt1 NOE" in text and met == {"Noe"}


def test_a_word_is_respelt_whatever_styles_divide_it(
    policy: bible.policy.Policy,
) -> None:
    words = revisions(
        policy,
        words={
            "Noe": {"to": "Noah", "why": "the English name"},
            "Sem": {"to": "Shem", "why": "the English name"},
            "ham": {"to": "Cham", "why": "the Greek name"},
        },
    )
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 N\\add oe\\add* and \\add Se\\add*m "
        "\\f - \\fr 1:1 \\fq N\\+it oe\\+it*: \\ft or, \\fqa S\\+it em\\+it*\\f*begat "
        "Noe\\add man\\add* and \\it Sem\\it*s and \\it thus \\it*ham and Noe\n"
        "\\v 2 begat Sem.\n"
    )
    met: revision.MetRevisions = set()
    text = usj.serialize(revision.respelt(doc, words, met))
    # Each letter keeps the style it stood in, and what is added takes the
    # style of the word it joins.
    assert "\\v 1 N\\add oah\\add* and \\add She\\add*m " in text
    assert "\\fq N\\+it oah\\+it*: \\ft or, \\fqa Sh\\+it em\\+it*\\f*" in text
    assert "and \\it thus \\it*Cham and " in text
    # A word is whole by the letters about it, in whatever style, and a
    # verse's number ends one.
    assert "begat Noe\\add man\\add* and \\it Sem\\it*s and " in text
    assert text.endswith("and Noah\n\\v 2 begat Shem.\n")
    assert met == {"Noe", "Sem", "ham"}


def group(*changes: object, why: str = "the sentence runs on") -> dict[str, Any]:
    return {"pointing": {"why": why, "changes": list(changes)}}


def test_a_verse_is_revised_in_its_own_words_and_the_notes_that_quote_them(
    policy: bible.policy.Policy,
) -> None:
    change = {"verse": "GEN 1:1", "from": "went with Noe.", "to": "went with Noe:"}
    verses = revisions(policy, verses=group(change))
    revision.check(verses)
    met: revision.MetRevisions = set()
    text = usj.serialize(revision.revised("GEN", usj.parse(NOE), verses, met))
    # The words change in the styles they stand in; the other verse is as it was.
    assert "\\fqa Noe\\f*went \\add with\\add* Noe:\n\\v 2 And Noe went.\n" in text
    assert met == {"GEN 1:1"}
    quoted = {
        "verse": "GEN 1:1",
        "from": "with Noe",
        "to": "beside Noe",
        "why": "a note quotes these words",
    }
    both = revisions(
        policy, verses={**group(change), "wording": {"why": "x", "changes": [quoted]}}
    )
    revision.check(both)
    text = usj.serialize(revision.revised("GEN", usj.parse(NOE), both, set()))
    # Two groups revise the one verse, each its own words.
    assert "\\fq went beside Noe: " in text and "went \\add beside\\add* Noe:" in text


def test_a_note_quotes_a_verse_whatever_styles_divide_its_words(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 He went \\add with\\add* Noe \\f - \\fr 1:1 "
        "\\fq went \\+it with\\+it* Noe: \\ft or, \\fqa beside\\f*then.\n"
    )
    change = {"verse": "GEN 1:1", "from": "went with Noe", "to": "went beside Noe"}
    verses = revisions(policy, verses=group(change))
    text = usj.serialize(revision.revised("GEN", doc, verses, set()))
    assert "\\v 1 He went \\add beside\\add* Noe " in text
    assert "\\fq went \\+it beside\\+it* Noe: \\ft or, \\fqa beside\\f*then." in text


def test_a_revision_across_a_style_or_note_is_refused(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 He went,—\\add with\\add* Noe,—"
        "\\f - \\fr 1:1 \\ft Gr. went\\f* then.\n"
    )
    # The supplied word would be set in the plain words before it.
    styled = {"verse": "GEN 1:1", "from": "went,—with Noe,—", "to": "went with Noe "}
    with pytest.raises(CheckFailed, match="across a style or note: GEN 1:1"):
        revision.revised("GEN", doc, revisions(policy, verses=group(styled)), set())
    # The note would stand after the words that followed it.
    noted = {"verse": "GEN 1:1", "from": "Noe,— then", "to": "Noe; Then"}
    with pytest.raises(CheckFailed, match="across a style or note: GEN 1:1"):
        revision.revised("GEN", doc, revisions(policy, verses=group(noted)), set())
    within = {"verse": "GEN 1:1", "from": "went,—", "to": "went "}
    text = usj.serialize(
        revision.revised("GEN", doc, revisions(policy, verses=group(within)), set())
    )
    assert "\\v 1 He went \\add with\\add* Noe,—" in text


def test_a_revision_changes_a_lemma_whole_or_is_refused(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 He went with Noe \\f - \\fr 1:1 "
        "\\fq with Noe: \\ft Gr. went with Noe\\f*then.\n"
    )
    # The lemma holds only part of the words revised, and would go stale.
    partly = {"verse": "GEN 1:1", "from": "went with", "to": "walked beside"}
    with pytest.raises(CheckFailed, match="lemma its verse no longer has: GEN 1:1"):
        revision.revised("GEN", doc, revisions(policy, verses=group(partly)), set())
    # Only the lemma quotes the verse: the note's own words stay.
    within = {"verse": "GEN 1:1", "from": "with Noe", "to": "beside Noe"}
    text = usj.serialize(
        revision.revised("GEN", doc, revisions(policy, verses=group(within)), set())
    )
    assert "\\fq beside Noe: \\ft Gr. went with Noe\\f*then." in text


@pytest.mark.parametrize(
    "sections, refusal",
    [
        (
            {"words": {"Noe": {"to": "Noe", "why": "x"}}},
            "changes nothing, or without a why",
        ),
        ({"words": {"Noe.": {"to": "Noah", "why": "x"}}}, "not a word"),
        (
            {"verses": {"GEN 1:1": [{"from": "Noe", "to": "Noah"}]}},
            "missing or unknown fields",
        ),
        ({"verses": group(why="")}, "without a why, or without a change"),
        ({"verses": group({"from": "Noe", "to": "Noah"})}, "missing or unknown fields"),
        (
            {"verses": group({"verse": "Genesis 1", "from": "Noe", "to": "Noah"})},
            "not a verse",
        ),
        (
            {"verses": group({"verse": "GEN 1:1", "from": "Noe", "to": "Noe"})},
            "changes nothing",
        ),
        (
            {"verses": group({"verse": "MAT 1:1", "from": "Noe", "to": "Noah"})},
            "Revision changes New Testament words",
        ),
    ],
)
def test_a_malformed_revision_is_refused(
    policy: bible.policy.Policy, sections: dict[str, Any], refusal: str
) -> None:
    with pytest.raises(CheckFailed, match=refusal):
        revision.check(revisions(policy, **sections))


def test_a_revision_must_be_met(policy: bible.policy.Policy) -> None:
    doc = usj.parse(NOE)
    twice = {"verse": "GEN 1:1", "from": "Noe", "to": "Noah"}
    with pytest.raises(CheckFailed, match="not met once in its verse: GEN 1:1"):
        revision.revised("GEN", doc, revisions(policy, verses=group(twice)), set())
    absent = {**twice, "verse": "GEN 1:9"}
    with pytest.raises(CheckFailed, match="verse the edition lacks: GEN 1:9"):
        revision.revised("GEN", doc, revisions(policy, verses=group(absent)), set())
    stop = {"verse": "GEN 1:2", "from": "went.", "to": "went;"}
    same = {"verse": "GEN 1:2", "from": "Noe went.", "to": "Noe went:"}
    with pytest.raises(CheckFailed, match="Revisions of the same words: GEN 1:2"):
        revision.revised("GEN", doc, revisions(policy, verses=group(stop, same)), set())
    unprinted = revisions(policy, verses=group({**twice, "verse": "XYZ 1:1"}))
    with pytest.raises(
        CheckFailed, match=r"Revisions that nothing prints: \['XYZ 1:1'\]"
    ):
        revision.check_met(unprinted, set())
    unmet = revisions(
        policy, words={"Jehoshaphat": {"to": "Josaphat", "why": "nowhere"}}
    )
    with pytest.raises(
        CheckFailed, match=r"Revisions that nothing prints: \['Jehoshaphat'\]"
    ):
        revision.check_met(unmet, set())


@pytest.mark.parametrize(
    "old,new",
    [
        ("word.", "word?"),
        ("king's word: 1", "king's word; 1"),
        ("believed: blessed", "believed? Blessed"),
        ("believed? Blessed", "believed: blessed"),
    ],
)
def test_nt_verse_revisions_allow_punctuation(
    policy: bible.policy.Policy, old: str, new: str
) -> None:
    decision = {"verse": "MAT 1:1", "from": old, "to": new}
    revision.check(revisions(policy, verses=group(decision)))


@pytest.mark.parametrize(
    "old,new",
    [
        ("1", "2"),
        ("thy", "thine"),
        ("king's", "kings"),
        ("the apostles’ feet", "the apostles feet"),
        ("market-place", "market place"),
        ("God", "god"),
        ("said: god", "said: God"),
        ("said? God", "said? god"),
        ("said: god", "said? GOD"),
    ],
)
def test_nt_punctuation_decisions_cannot_change_words(
    policy: bible.policy.Policy, old: str, new: str
) -> None:
    decision = {"verse": "MAT 1:1", "from": old, "to": new}
    with pytest.raises(CheckFailed, match="Revision changes New Testament words"):
        revision.check(revisions(policy, verses=group(decision)))


def test_a_revision_may_end_a_paragraph_or_leave_a_style_without_words(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 In \\add the\\add* beginning\n"
        "\\v 2 God made\n\\p\n\\v 3 the earth\n"
    )
    changes = group(
        {"verse": "GEN 1:1", "from": "In the beginning", "to": "In beginning"},
        {"verse": "GEN 1:2", "from": "God made", "to": "God made:"},
    )
    revised = revision.revised("GEN", doc, revisions(policy, verses=changes), set())
    # The style that lost its words is gone, and the verse after it in the
    # paragraph is still found; words added at a paragraph's end stand there.
    assert usj.serialize(revised).endswith(
        "\\p\n\\v 1 In beginning\n\\v 2 God made:\n\\p\n\\v 3 the earth\n"
    )


def test_the_sample_prints_selected_chapters_as_the_full_edition_has_them(
    edition: bible.pipeline.Edition, policy: bible.policy.Policy
) -> None:
    full = dict(pipeline.view(edition, "pdf"))
    sample = dict(pipeline.view(edition, "sample"))
    assert set(sample) == set(full) - (edition.scripture - set(policy.sample))
    for code, chapters in policy.sample.items():
        _, wanted = assembly.chapters_of(sample[code])
        assert [int(blocks[0]["number"]) for blocks in wanted] == sorted(chapters)
        whole = {
            blocks[0]["number"]: blocks
            for blocks in assembly.chapters_of(full[code])[1]
        }
        for blocks in wanted:
            # A chapter that followed an omitted one may open a paragraph of its own.
            first = [
                b if b.get("marker") != "p" else {**b, "marker": "nb"}
                for b in blocks[:2]
            ]
            assert blocks[2:] == whole[blocks[0]["number"]][2:], code
            assert blocks[:2] == whole[blocks[0]["number"]][:2] or first == [
                b if b.get("marker") != "p" else {**b, "marker": "nb"}
                for b in whole[blocks[0]["number"]][:2]
            ], code
    # A heading set before a chapter is kept with it.
    daniel = usj.serialize(sample["DAG"])
    assert daniel.count("\\s1 Susanna\n\\c 0\n\\cp ​\n") == 1
    # A chapter's own closing paragraph stays with it: Psalm 71 ends in a \d
    # that holds its last verse.
    close = "\\d\n\\v 20 The hymns of David the son of Jessæ are ended.\n"
    psalms = edition.documents["PSA"]
    assert usj.serialize(pipeline.sample_chapters("PSA", psalms, [71])).endswith(close)
    assert close not in usj.serialize(pipeline.sample_chapters("PSA", psalms, [72]))


def test_what_is_typeset_carries_no_callers_and_prints_notes_by_their_verses(
    exported: dict[str, str], edition: bible.pipeline.Edition
) -> None:
    for code in edition.scripture:
        text = exported[code]
        # Any caller, "*" as well as "+"; only "-" sets none.
        assert not re.search(r"\\(?:ef|[fx]) (?!- )", text), code
        # The chapter is the page's to supply: an origin is its verse alone.
        assert not re.search(r"\\(?:fr|xo) \d+:", text), code
    # Front matter's notes keep their callers, and print under them alone.
    assert "\\f + \\ft See Preface to Lambert Bos’s edition" in exported["XXB"]
    # Greek and Hebrew are tagged for their fonts, single letters too: within
    # a note's words, and among a paragraph's.
    assert "\\+wg εἰς ὁμοιότητα\\+wg*" in exported["GEN"]
    assert "\\wh רפאים\\wh*" in exported["BAK"]
    # The edition's own pages are sent as the editor wrote them.
    assert not re.search(r"\\\+?w[gh] ", exported["CNC"])


def test_greek_and_hebrew_are_set_in_the_styles_of_their_fonts() -> None:
    content = usj.parse("Gr. ἀλλʼ ἐγώ, \\it Heb.\\it* א, \\it or β\\it*", fragment=True)
    assert usj.serialize(pipeline.font_runs(content)) == (
        "Gr. \\wg ἀλλ’ ἐγώ\\wg*, \\it Heb.\\it* \\wh א\\wh*, "
        "\\it or \\+wg β\\+wg*\\it*"
    )
    # Only the form of what prints changes.
    assert usj.text_of(pipeline.font_runs(content)) == "Gr. ἀλλ’ ἐγώ, Heb. א, or β"


def test_the_review_is_written_once_and_shows_what_changed(
    edition: bible.pipeline.Edition,
    policy: bible.policy.Policy,
    sources: bible.sources.Sources,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(paths, "BUILD_DIR", tmp_path)
    review.review(sources, policy, edition)
    base = tmp_path / "review"
    assert {p.name for p in base.iterdir()} == {
        "notes.md",
        "alexandrinus.md",
        "numbering.md",
        "byzantine.md",
        "byzantine",
        "text",
        "changes.diff",
    }
    assert len(list((base / "text").iterdir())) == len(edition.documents)
    assert len(list((base / "byzantine").iterdir())) == 27
    notes = (base / "notes.md").read_text(encoding="utf-8")
    assert (
        "- `GEN 1:9` [length; rendering]" in notes and "→ place: Gr. _meeting_" in notes
    )
    decision = (base / "alexandrinus.md").read_text(encoding="utf-8")
    assert (
        "## GEN 3:22 — readings" in decision
        and "Swete 1 p. 5 (text; agrees=True)" in decision
    )
    # Every run with what it rests on; one that rests on the words alone
    # with the words of both translations, to be read.
    numbering = (base / "numbering.md").read_text(encoding="utf-8")
    assert "- JOL 3:1-5 = JOL 2:28-32 (table)\n" in numbering
    assert "- nothing = JER 33:14-26 (missing)\n" in numbering
    assert "- GEN 31:47-48 = GEN 31:47-48 (reading: The King James" in numbering
    assert (
        "- GEN 8:3 = GEN 8:3-4 (words)\n  - Brenton 8:3: And the water" in numbering
        and "  - King James 8:4: And the ark rested" in numbering
    )
    # The next review shows what differs from the last, and nothing else.
    ezekiel = base / "text" / "EZK.usfm"
    ezekiel.write_text(
        ezekiel.read_text(encoding="utf-8").replace(
            "And Ezekiel shall", "And Jezekiel shall"
        ),
        encoding="utf-8",
    )
    review.review(sources, policy, edition)
    diff = (base / "changes.diff").read_text(encoding="utf-8")
    assert [line for line in diff.splitlines() if line.startswith("+++ ")] == [
        "+++ current/text/EZK.usfm"
    ]
    assert (
        "-\\v 24 And Jezekiel shall be" in diff
        and "+\\v 24 And Ezekiel shall be" in diff
    )
    assert "1 files changed" in capsys.readouterr().out


@pytest.mark.parametrize(
    "marks", [",", ";", ":", ".", "?", "!", ",;:", ",;:.?!", ".,;:", "?,:", "!,;:"]
)
def test_punctuation_before_a_dash_across_styles(
    policy: bible.policy.Policy, marks: str
) -> None:
    doc = usj.parse(f"\\id GEN\n\\c 1\n\\p\n\\v 1 Word{marks}\\it —more\\it*.")
    before = copy.deepcopy(doc)
    met: revision.MetRevisions = set()
    result = revision.punctuated(doc, policy, met)
    expected = re.sub(r"[,;:]+$", "", marks)
    assert scripture_text(result) == f"Word{expected}—more."
    assert "\\it —more\\it*" in usj.serialize(result)
    assert doc == before
    assert revision.punctuated(result, policy, set()) == result
    assert met == ({"before-em-dash"} if expected != marks else set())


def scripture_text(doc: usj.Document) -> str:
    return usj.text_of(doc["content"][2]["content"])


def test_punctuation_in_notes_and_matter(policy: bible.policy.Policy) -> None:
    doc = usj.parse(
        "\\id GEN\n\\ip Preface:—words.\n\\c 1\n\\p\n\\v 1 Word,\\f - \\fr 1:1 \\fq Word,—more: \\ft Gr. Witness;—reading.\\f*—more."
    )
    note = usj.notes_of(doc["content"])[0]
    note.update({"x-key": "GEN 1:1#1"})
    before = copy.deepcopy(doc)
    result = revision.punctuated(doc, policy, set())
    assert "Preface—words." in usj.serialize(result)
    new_note = usj.notes_of(result["content"])[0]
    assert new_note["x-key"] == note["x-key"]
    assert usj.text_of(new_note["content"]) == "1:1 Word—more: Gr. Witness—reading."
    assert doc == before


def test_dash_rule_respects_boundaries_and_foreign_words(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 End,\n\\v 2 —start, —spaced;–en.—?! after,‘—quote [,—bracket] λόγος\\it ,—\\it* שָׁלוֹם.— λόγος.,— שָׁלוֹם?.:— \\wg λόγος,—\\wg* \\it \\+wh שָׁלוֹם.—\\+wh*\\it*.\n\\p —paragraph.\n\\tr \\tc1 Cell, \\tc2 —next"
    )
    before = copy.deepcopy(doc)
    result = revision.punctuated(doc, policy, set())
    assert "—?! after,‘—quote [—bracket]" in usj.serialize(result)
    assert "λόγος\\it ,—\\it* שָׁלוֹם.—" in usj.serialize(result)
    assert "\\wg λόγος,—\\wg*" in usj.serialize(result)
    assert "\\+wh שָׁלוֹם.—\\+wh*" in usj.serialize(result)
    assert "λόγος.,— שָׁלוֹם?.:—" in usj.serialize(result)
    assert "End," in usj.serialize(result)
    assert "Cell," in usj.serialize(result)
    assert ", —spaced;–en.—" in usj.serialize(result)
    assert doc == before


@pytest.mark.parametrize(
    "verse",
    ["\\wg λόγος\\wg*,—and", "\\it \\+wg λόγος\\+wg*,—and\\it*"],
)
def test_punctuation_after_a_tagged_foreign_word_is_refused(
    policy: bible.policy.Policy, verse: str
) -> None:
    doc = usj.parse(f"\\id GEN\n\\c 1\n\\p\n\\v 1 The word {verse} more.")
    with pytest.raises(CheckFailed, match="tagged foreign word: GEN: ,—and"):
        revision.punctuated(doc, policy, set())


def test_punctuation_that_leaves_a_lemma_is_refused(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 O king,\\f + \\fq O king, \\ft Or, lord.\\f*—the eyes."
    )
    with pytest.raises(CheckFailed, match="lemma .* GEN 1:1: O king,"):
        revision.punctuated(doc, policy, set())


@pytest.mark.parametrize(
    "rule",
    [
        {"unknown": {"why": "x"}},
        {"before-em-dash": {"why": ""}},
        {"before-em-dash": {"why": "x", "from": ","}},
    ],
)
def test_bad_punctuation_rules_are_refused(
    policy: bible.policy.Policy, rule: dict[str, Any]
) -> None:
    with pytest.raises(CheckFailed):
        revision.check(revisions(policy, punctuation=rule))


def test_unused_punctuation_rule_is_refused(policy: bible.policy.Policy) -> None:
    policy = revisions(policy, punctuation={"before-em-dash": {"why": "x"}})
    met: revision.MetRevisions = set()
    revision.punctuated(usj.parse("\\id GEN\n\\ip Nothing, —adjacent."), policy, met)
    with pytest.raises(CheckFailed, match="before-em-dash"):
        revision.check_met(policy, met)


def passage_group(*changes: dict[str, str]) -> dict[str, Any]:
    return {
        "dashes": {
            "why": "The explanation continues after the dash.",
            "changes": changes,
        }
    }


def test_passage_revisions_keep_styles_metadata_and_inputs(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 Text.\\f - \\fr 1:1 \\ft a \\it note.\\it*—The words.\\f*"
    )
    note = usj.notes_of(doc["content"])[0]
    note.update(
        {"x-key": "GEN 1:1#1", "x-scope": {"lemma": "Text"}, "category": "edition"}
    )
    before = copy.deepcopy(doc)
    change = {"note": "GEN 1:1#1", "from": "note.—The words", "to": "note—The words"}
    initial = {"note": "GEN 1:1#1", "from": "a ", "to": "A "}
    rules = revisions(policy, passages=passage_group(change, initial))
    revision.check(rules)
    met: revision.MetRevisions = set()
    result = revision.passages("GEN", doc, rules, met)
    after = usj.notes_of(result["content"])[0]
    assert {k: v for k, v in after.items() if k != "content"} == {
        k: v for k, v in note.items() if k != "content"
    }
    assert "\\it note\\it*—The words" in usj.serialize(result)
    assert doc == before
    assert usj.text_of(after["content"]).startswith("1:1 A note")
    assert met == {("GEN 1:1#1", "note.—The words"), ("GEN 1:1#1", "a ")}
    revision.check_met(rules, met)


def test_passage_revisions_in_matter_and_capitalization(
    policy: bible.policy.Policy,
) -> None:
    doc = usj.parse(
        "\\id XXB\n\\ip Word. \\it more\\it*;—and another.\n\\ip Word.—Elsewhere."
    )
    before = copy.deepcopy(doc)
    change = {"unit": "XXB", "from": "more;—and", "to": "more. And"}
    rules = revisions(policy, passages=passage_group(change))
    revision.check(rules)
    result = revision.passages("XXB", doc, rules, set())
    assert "\\it more\\it*. And another." in usj.serialize(result)
    assert "Word.—Elsewhere." in usj.serialize(result)
    assert doc == before
    invalid = revisions(
        policy,
        passages=passage_group({"unit": "XXB", "from": "another", "to": "Another"}),
    )
    revision.check(invalid)
    with pytest.raises(CheckFailed, match="noninitial capitalization"):
        revision.passages("XXB", doc, invalid, set())


@pytest.mark.parametrize(
    "change",
    [
        {"from": "Word.—", "to": "Word—"},
        {"unit": "GEN", "from": "Word.—", "to": "Word—"},
        {"unit": "XXB", "note": "GEN 1:1", "from": "Word.—", "to": "Word—"},
        {"note": "invalid", "from": "Word.—", "to": "Word—"},
        {"unit": "XXB", "from": "Word.—", "to": "Word.—"},
        {"unit": "XXB", "from": "Word.—", "to": "Other—"},
        {"unit": "XXB", "from": "two words", "to": "twowords"},
        {"unit": "XXB", "from": "door-post", "to": "door post"},
        {"unit": "XXB", "from": "word and", "to": "word And"},
        {"unit": "XXB", "from": "Word.—", "to": "Word—", "why": ""},
        {"unit": "XXB", "from": "Word.—", "to": "\\it Word\\it*—"},
    ],
)
def test_invalid_passage_revisions_are_refused(
    policy: bible.policy.Policy, change: dict[str, str]
) -> None:
    with pytest.raises(CheckFailed):
        revision.check(revisions(policy, passages=passage_group(change)))


@pytest.mark.parametrize("text", ["Absent.", "Word.—Word.—", "Word.—\n\\ip Word.—"])
def test_passage_revisions_must_match_once(
    policy: bible.policy.Policy, text: str
) -> None:
    rules = revisions(
        policy, passages=passage_group({"unit": "XXB", "from": "Word.—", "to": "Word—"})
    )
    with pytest.raises(CheckFailed, match="not met once"):
        revision.passages("XXB", usj.parse("\\id XXB\n\\ip " + text), rules, set())


def test_overlapping_and_unused_passage_revisions_are_refused(
    policy: bible.policy.Policy,
) -> None:
    first = {"unit": "XXB", "from": "Word.—more", "to": "Word—more"}
    second = {"unit": "XXB", "from": ".—more", "to": "—more"}
    rules = revisions(policy, passages=passage_group(first, second))
    doc = usj.parse("\\id XXB\n\\ip Word.—more")
    with pytest.raises(CheckFailed, match="Overlapping"):
        revision.passages("XXB", doc, rules, set())
    with pytest.raises(CheckFailed, match="nothing prints"):
        revision.check_met(rules, {("XXB", first["from"])})
    with pytest.raises(CheckFailed, match="Overlapping"):
        revision.passages(
            "XXB", doc, revisions(policy, passages=passage_group(first, first)), set()
        )


def test_prepared_contextual_dashes_and_derived_quotations(
    edition: bible.pipeline.Edition,
    policy: bible.policy.Policy,
    read: bible.pipeline.Read,
) -> None:
    for change in revision.verse_changes(policy):
        code, reference = change["verse"].split()
        words = scripture.verses(edition.documents[code])[reference].text
        assert change["to"] in words
        assert change["from"] not in words
    for passage_change in revision.passage_changes(policy):
        if "note" in passage_change:
            code = passage_change["note"].split()[0]
            note = next(
                n
                for n in usj.notes_of(edition.documents[code]["content"])
                if n.get("x-key") == passage_change["note"]
            )
            words = usj.text_of(note["content"])
        else:
            words = usj.text_of(edition.documents[passage_change["unit"]]["content"])
        assert passage_change["to"] in words
        assert passage_change["from"] not in words
    assert (
        "expressly were appointed"
        in scripture.verses(edition.documents["2CH"])["31:19"].text
    )
    assert "dead?—" in scripture.verses(edition.documents["2SA"])["12:18"].text
    note = next(
        n
        for n in usj.notes_of(edition.documents["DEU"]["content"])
        if n.get("x-key") == "DEU 17:20"
    )
    assert "Heb.—" in usj.text_of(note["content"])
    quoted = places.report(policy.versification["kjv"], edition.documents, read.kjv)
    assert "Artaxerxes (this Artaxerxes" in quoted
    assert "save Israel.—" not in quoted


def test_passage_note_keys_must_select_once(policy: bible.policy.Policy) -> None:
    doc = usj.parse(
        "\\id GEN\n\\c 1\n\\p\n\\v 1 Text.\\f - \\ft Word.—more\\f*\\f - \\ft Other.\\f*"
    )
    for note in usj.notes_of(doc["content"]):
        note["x-key"] = "GEN 1:1#1"
    rules = revisions(
        policy,
        passages=passage_group(
            {"note": "GEN 1:1#1", "from": "Word.—more", "to": "Word—more"}
        ),
    )
    with pytest.raises(CheckFailed, match="not met once"):
        revision.passages("GEN", doc, rules, set())
