"""The edition's numbering beside Brenton's, Turpie's, and the King James
Bible's: each run that the build works out checked against the table, the
words of both translations, and the verses both Bibles have."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from conftest import changed

import bible.pipeline
import bible.places
import bible.policy
import bible.references
import bible.sources
from bible import (
    alignment,
    assembly,
    crossrefs,
    pipeline,
    places,
    quotations,
    usfm,
    usj,
    versification,
)
from bible.checks import CheckFailed
from bible.policy import thaw
from bible.references import Verse, parse_passage, parse_verse
from bible.usj import Document
from bible.versification import lxx_to_edition

# How far a run's words may be outscored by the same run a few verses off.
MARGIN = 0.1
SHIFTS = (-3, -2, -1, 1, 2, 3)


@pytest.fixture(scope="module")
def scripture(edition: bible.pipeline.Edition) -> dict[str, Document]:
    """Each book of scripture as the edition prints it, by its code."""
    return {code: edition.documents[code] for code in edition.scripture}


@pytest.fixture(scope="module")
def texts(
    scripture: dict[str, Document],
    read: bible.pipeline.Read,
    policy: bible.policy.Policy,
) -> bible.places.Texts:
    """The words of both translations' Old Testaments, verse by verse."""
    return places.Texts(scripture, read.kjv, policy=policy)


@pytest.fixture(scope="module")
def table(texts: bible.places.Texts, scripture: dict[str, Document]) -> places.Table:
    """STEPBible's account of where each of the edition's verses stands."""
    return places.tabled(texts, scripture)


def printed(verse: bible.references.Verse, edition: bible.pipeline.Edition) -> bool:
    labels = edition.inventory[verse.book].get(str(verse.chapter), ())
    return f"{verse.number}{verse.letter}" in labels


def excepting(
    policy: bible.policy.Policy, source: str, **exception: str
) -> bible.policy.Policy:
    """The policy with one more exception to Turpie's numbering, or with one
    of its own given otherwise."""
    return changed(
        policy,
        "quotations",
        lambda data: data["lxx_to_edition"].update({source: {"why": "x", **exception}}),
    )


@pytest.mark.parametrize(
    "source,target",
    [("JOL 2:28", "JOL 3:1"), ("HOS 1:10", "HOS 2:1"), ("PRO 22:8", "PRO 22:8a")],
)
def test_source_numbering_exceptions_name_printed_verses(
    policy: bible.policy.Policy,
    edition: bible.pipeline.Edition,
    source: str,
    target: str,
) -> None:
    assert lxx_to_edition(parse_verse(source), policy=policy) == parse_verse(target)
    assert printed(parse_verse(target), edition)


def test_relabelled_verse_needs_no_exception_to_be_caught(
    policy: bible.policy.Policy, edition: bible.pipeline.Edition
) -> None:
    # The edition prints Brenton's Malachias 3:23 as 4:5, so a quotation of
    # "MAL 3:23" has no printed verse to link and fails preparation.
    def quote(data: dict[str, Any]) -> None:
        head = next(h for h in data["rows"] if h["lxx"].get("normalized") == "MAL 3:1")
        head["lxx"]["normalized"] = "MAL 3:23"

    with pytest.raises(CheckFailed, match="Quotation verse missing.*MAL 3:23"):
        pipeline.quotation_links(changed(policy, "turpie", quote), edition.inventory)


@pytest.mark.parametrize(
    "source,target",
    [
        ("MAL 3:19-24", "MAL 4:1-6"),
        # Q095 links Exodus 32:1 and keeps Turpie's "or 23" as an alternative,
        # which the edition doesn't link.
        ("EXO 32:23", "EXO 32:22"),
    ],
)
def test_every_exception_is_used(
    policy: bible.policy.Policy, source: str, target: str
) -> None:
    with pytest.raises(CheckFailed, match=rf"no quotation uses: \['{source}'\]"):
        quotations.reviewed_rows(policy=excepting(policy, source, target=target))


@pytest.mark.parametrize(
    "source,exception,refusal",
    [
        ("JOL 2:28-32", {"target": "JOL 3:1-4"}, "misaligned mapping: JOL 2:28-32"),
        # One that numbers as the King James Bible does takes its printed
        # verses from the runs.
        (
            "JOL 2:28-32",
            {"numbering": "kjv", "target": "JOL 3:1-5"},
            "Mapping given twice: JOL 2:28-32",
        ),
        ("GEN 1:1", {"numbering": "kjv"}, "Mapping that changes nothing: GEN 1:1"),
        ("JOL 2:32", {"target": "JOL 3:5"}, "Overlapping mappings of JOL 2:32"),
    ],
)
def test_the_exceptions_are_checked_whole(
    policy: bible.policy.Policy, source: str, exception: dict[str, Any], refusal: str
) -> None:
    # Even for a reference no exception reaches.
    with pytest.raises(CheckFailed, match=refusal):
        lxx_to_edition(
            parse_verse("GEN 1:2"), policy=excepting(policy, source, **exception)
        )


def test_a_lettered_verse_never_joins_a_range(
    policy: bible.policy.Policy,
    edition: bible.pipeline.Edition,
    sources: bible.sources.Sources,
) -> None:
    mapped = versification.mapped_passages(parse_passage("PRO 22:7-9"), policy=policy)
    assert list(map(str, mapped)) == ["PRO 22:7", "PRO 22:8a", "PRO 22:9"]
    # The link that stands at it prints its label.
    links = pipeline.quotation_links(policy, edition.inventory)
    [link] = [link for link in links["PRO"] if "Q216" in link.row_ids]
    assert link.origin == parse_verse("PRO 22:8a")
    note = crossrefs.link_note(
        link.origin, link.targets, link.agreement, assembly.books(policy, sources)
    )
    assert usj.serialize([note]) == r"\x - \xo 22:8a \xt 2 Cor. 9:7\x*"


def unplaced(
    texts: bible.places.Texts, policy: bible.policy.Policy
) -> tuple[list[str], ...]:
    """What the runs leave without a place: the King James verses that no
    verse of the edition reaches and no run lists as missing, and the
    edition's verses whose counterparts the King James Bible lacks."""
    missing, lost = [], []
    for code, kjv in texts.books.items():
        reached = {
            counterpart
            for verse in texts.edition.order[code]
            for counterpart in versification.to_kjv(verse, policy=policy)
        }
        lost += sorted(map(str, reached - set(texts.kjv.words)))
        listed = {
            verse
            for run in policy.versification["kjv"].get(code, [])
            if not run["edition"] and run["kjv"]
            for verse in versification.verses(run["kjv"])
        }
        assert not listed & reached, f"Listed as missing and reached: {code}"
        missing += [
            str(verse)
            for verse in texts.kjv.order[kjv]
            if verse.number != versification.TITLE
            and verse not in reached
            and verse not in listed
        ]
    return missing, lost


def test_every_verse_of_both_bibles_has_its_place(
    texts: bible.places.Texts, policy: bible.policy.Policy
) -> None:
    assert unplaced(texts, policy) == ([], [])


def test_a_verse_faces_the_verses_that_face_it(
    texts: bible.places.Texts, policy: bible.policy.Policy
) -> None:
    for code in texts.books:
        for verse in texts.edition.order[code]:
            for counterpart in versification.to_kjv(verse, policy=policy):
                assert verse in versification.from_kjv(counterpart, policy=policy)


def test_a_verse_the_edition_lacks_is_listed(
    texts: bible.places.Texts, policy: bible.policy.Policy
) -> None:
    # The Greek lacks the promise of the Branch, Jeremiah 33:14-26.
    branch = {"edition": None, "kjv": "JER 33:14-26"}
    unlisted = changed(
        policy, "versification", lambda data: data["kjv"]["JER"].remove(branch)
    )
    missing, _ = unplaced(texts, unlisted)
    assert missing == [f"JER 33:{verse}" for verse in range(14, 27)]


def joel(**change: str) -> Callable[[dict[str, Any]], object]:
    """A change to the run that gives Joel 3:1-5 the King James Bible's
    2:28-32, or the run's removal."""

    def edit(data: dict[str, Any]) -> None:
        runs = data["kjv"]["JOL"]
        [run] = [run for run in runs if run["edition"] == "JOL 3:1-5"]
        if change:
            run.update(change)
        else:
            runs.remove(run)

    return edit


def added(code: str, **run: str) -> Callable[[dict[str, Any]], object]:
    return lambda data: data["kjv"][code].append(run)


def paired(*kjv: str) -> Callable[[dict[str, Any]], object]:
    """Other pairs for Proverbs 8:28 and 8:29, whose verses overlap."""

    def edit(data: dict[str, Any]) -> None:
        run = next(run for run in data["kjv"]["PRO"] if "pairs" in run)
        run["pairs"] = dict(zip(("PRO 8:28", "PRO 8:29"), kjv))

    return edit


@pytest.mark.parametrize(
    "change,verse",
    [
        # Unlisted, Joel 3:1 would keep its number, which Joel 4:1 has.
        (joel(), "JOL 3:1"),
        # A verse off, the run reaches the King James verse that Joel 2:27 is.
        (joel(kjv="JOL 2:27-31"), "JOL 2:27"),
    ],
)
def test_a_verse_cannot_take_the_place_of_another(
    policy: bible.policy.Policy, change: Callable[[dict[str, Any]], object], verse: str
) -> None:
    with pytest.raises(CheckFailed, match=f"Another verse has the place of {verse}"):
        versification.to_kjv(
            parse_verse(verse), policy=changed(policy, "versification", change)
        )


@pytest.mark.parametrize(
    "change,refusal",
    [
        (joel(by="guess"), "without its witness"),
        (joel(by="reading"), "A reading gives its reason"),
        (joel(why="x"), "A reading gives its reason"),
        (joel(kjv="HOS 2:28-32"), "outside its book"),
        (joel(edition="HOS 1:1-5"), "outside its book"),
        (
            added("JOL", edition="JOL 1:1", kjv="JOL 2:28", by="words"),
            "Two runs reach JOL 2:28",
        ),
        (
            added("DAG", edition="DAG 3:24-28", kjv="DAN 3:24-28", by="words"),
            "within the Apocrypha: DAG 3:24-28",
        ),
        # Explicit pairs cover the run they are declared for, and no more.
        (paired("PRO 8:28-29"), "Invalid verse pairs"),
        (paired("PRO 8:28-29", ""), "Invalid verse pairs"),
        (paired("PRO 8:28", "PRO 8:30"), "Verse pairs do not cover"),
        (paired("PRO 8:28", "PRO 8:28"), "Verse pairs do not cover"),
    ],
)
def test_a_malformed_run_is_refused(
    policy: bible.policy.Policy,
    change: Callable[[dict[str, Any]], object],
    refusal: str,
) -> None:
    # Whatever verse is asked for: the runs are checked whole.
    with pytest.raises(CheckFailed, match=refusal):
        versification.to_kjv(
            parse_verse("GEN 1:1"), policy=changed(policy, "versification", change)
        )


@pytest.mark.parametrize(
    "way,passage,mapped",
    [
        # Never by its ends: Jeremias 25:13-16 stands in two places.
        ("kjv", "JER 25:13-16", "JER 25:13; JER 49:34-36"),
        ("edition", "JER 25:13-16", "JER 25:13; JER 32:15-16"),
        ("edition", "JER 31:31-34", "JER 38:31-34"),
        # A psalm's title is counted, and the psalm numbered one lower.
        ("kjv", "PSA 33:13-17", "PSA 34:12-16"),
        # An addition has no counterpart.
        ("kjv", "PRO 22:8a", ""),
        ("kjv", "DAG 3:24", ""),
        ("kjv", "PSA 151:1", ""),
        # Brenton has Elias before the law of Moses; the King James Bible after.
        ("kjv", "MAL 4:1-6", "MAL 4:1-3; MAL 4:5-6; MAL 4:4"),
        # The sea's bound in Proverbs 8:28 opens the King James Bible's 8:29.
        ("kjv", "PRO 8:28", "PRO 8:28-29"),
        ("kjv", "PRO 8:29", "PRO 8:29"),
        ("edition", "PRO 8:28", "PRO 8:28"),
        ("edition", "PRO 8:29", "PRO 8:28-29"),
    ],
)
def test_a_passage_is_mapped_verse_by_verse(
    policy: bible.policy.Policy, way: str, passage: str, mapped: str
) -> None:
    passages = getattr(versification, f"{way}_passages")
    found = passages(parse_passage(passage), policy=policy)
    assert "; ".join(map(str, found)) == mapped


def test_a_book_of_the_apocrypha_has_no_counterpart_to_ask_for(
    policy: bible.policy.Policy,
) -> None:
    with pytest.raises(CheckFailed, match="No King James counterpart: TOB"):
        versification.to_kjv(parse_verse("TOB 1:1"), policy=policy)


def test_a_run_rests_on_the_witness_it_names(
    texts: bible.places.Texts, table: places.Table, policy: bible.policy.Policy
) -> None:
    """A run by the table is the table's account of the verse, and any other
    run departs from it; so does no verse that the file leaves unlisted."""
    departs: dict[str, list[bool]] = {}
    for code in texts.books:
        listed = {
            verse: run
            for run in policy.versification["kjv"].get(code, [])
            if run["edition"]
            for verse in versification.verses(run["edition"])
        }
        for verse in texts.edition.order[code]:
            ours = sorted(map(str, versification.to_kjv(verse, policy=policy)))
            said = table[verse]
            tabled = None if said is None else sorted(map(str, said))
            if verse not in listed and verse.letter:
                # An addition has no counterpart, whatever the table makes of it.
                assert ours == []
            elif verse not in listed or listed[verse]["by"] == "table":
                assert ours == tabled, f"{verse} isn't as the table has it"
            elif listed[verse]["by"] != "reading":
                # What the editor has read stands on its reason, with the table
                # or against it.
                edition_run = listed[verse]["edition"]
                assert edition_run is not None
                departs.setdefault(edition_run, []).append(ours != tabled)
    # A run departs from the table if any of its verses does: of two verses
    # that face one, the table may give one of them the same.
    assert [run for run, verses in departs.items() if not any(verses)] == []


def test_the_file_holds_only_what_the_editor_has_read(
    declared: bible.policy.Policy, policy: bible.policy.Policy
) -> None:
    # The build works out the rest, and the readings stand among it as given.
    assert "kjv" not in declared.versification
    with pytest.raises(CheckFailed, match="not yet placed"):
        versification.to_kjv(parse_verse("GEN 1:1"), policy=declared)
    for code, readings in declared.versification["readings"].items():
        stood = [
            {key: value for key, value in run.items() if key != "by"}
            for run in thaw(policy.versification["kjv"][code])
            if run.get("by") == "reading"
        ]
        assert stood == thaw(readings), code


def outscored(
    texts: bible.places.Texts,
    ours: list[bible.references.Verse],
    theirs: list[bible.references.Verse],
) -> bool:
    """Whether the same run a few verses off shares more words than the run.

    Verse for verse, where the run pairs its verses: a long run and the same
    run a verse off have nearly the same words between them.
    """

    def score(facing: list[bible.references.Verse]) -> float:
        if len(facing) != len(ours):
            return alignment.similarity(
                texts.weight, texts.edition.bag(ours), texts.kjv.bag(facing)
            )
        return sum(map(texts.similarity, ours, facing)) / len(ours)

    rivals = [
        score(shifted) for k in SHIFTS if (shifted := texts.kjv.shifted(theirs, k))
    ]
    return max(rivals, default=0) > score(theirs) + MARGIN


def runs_to_compare(
    texts: bible.places.Texts, policy: bible.policy.Policy
) -> list[tuple[str, list[Verse], list[Verse]]]:
    """The runs whose words can be compared: those the table or the words
    give, and each chapter's verses that keep their numbers."""
    found = []
    for code in texts.books:
        named: set[Verse] = set()
        chapters: dict[int, list[Verse]] = {}
        for run in policy.versification["kjv"].get(code, []):
            if not run["edition"]:
                continue
            ours = versification.verses(run["edition"])
            theirs = versification.verses(run["kjv"]) if run["kjv"] else []
            named.update(ours)
            titled = any(verse.number == versification.TITLE for verse in theirs)
            if theirs and run["by"] in {"table", "words"} and not titled:
                found.append((run["edition"], ours, theirs))
        for verse in texts.edition.order[code]:
            if verse not in named and versification.to_kjv(verse, policy=policy):
                chapters.setdefault(verse.chapter, []).append(verse)
        for chapter, ours in chapters.items():
            theirs = [versification.to_kjv(verse, policy=policy)[0] for verse in ours]
            found.append((f"{code} {chapter}", ours, theirs))
    return found


def test_the_words_bear_out_every_run(
    texts: bible.places.Texts, policy: bible.policy.Policy
) -> None:
    runs = runs_to_compare(texts, policy)
    flagged = {name for name, ours, theirs in runs if outscored(texts, ours, theirs)}
    assert flagged == set()
    # The check must still tell a run from its neighbour: most runs, moved a
    # verse, share fewer words than where they stand.
    moved = [
        (ours, there)
        for _, ours, theirs in runs
        if len(ours) >= 3 and (there := texts.kjv.shifted(theirs, 1))
    ]
    caught = sum(outscored(texts, ours, there) for ours, there in moved)
    assert moved and caught >= 0.9 * len(moved)


def test_every_relabelled_verse_is_printed_under_its_new_label(
    policy: bible.policy.Policy,
    edition: bible.pipeline.Edition,
    sources: bible.sources.Sources,
) -> None:
    for source, printed_as in versification.relabelled(policy=policy).items():
        labels = usfm.inventory(sources.brenton[source.book])["chapters"]
        assert str(source.number) in labels[str(source.chapter)]
        assert printed(printed_as, edition) and not printed(source, edition)
