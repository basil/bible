"""The edition's numbering beside Brenton's, Turpie's, and the King James
Bible's: each run of edition/versification.json checked against the table,
the words of both translations, and the verses both Bibles have."""

import pytest

from bible import alignment, quotations, versification
from bible.checks import CheckFailed
from bible.crossrefs import _link_usfm, quotation_links
from bible.edition import scripture_unit
from bible.prepare import scripture_text
from bible.references import parse_passage, parse_verse
from bible.usfm import inventory
from bible.versification import lxx_to_edition


def printed(verse, scripture):
    chapters = inventory(scripture[verse.book])["chapters"]
    return f"{verse.number}{verse.letter}" in chapters.get(str(verse.chapter), [])


@pytest.mark.parametrize(
    "source,target",
    [
        ("JOL 2:28", "JOL 3:1"),
        ("JOL 2:32", "JOL 3:5"),
        ("HOS 1:10", "HOS 2:1"),
    ],
)
def test_source_numbering_exceptions_name_printed_verses(scripture, source, target):
    assert lxx_to_edition(parse_verse(source)) == parse_verse(target)
    assert printed(parse_verse(target), scripture)


def test_relabelled_verse_needs_no_exception_to_be_caught(archives, patched):
    # The edition prints Brenton's Malachias 3:23 as 4:5, so a quotation of
    # "MAL 3:23" has no printed verse to link and fails preparation.
    rows = patched(quotations, "TURPIE")["rows"]
    head = next(h for h in rows if h["lxx"].get("normalized") == "MAL 3:1")
    head["lxx"]["normalized"] = "MAL 3:23"
    with pytest.raises(CheckFailed, match="Quotation verse missing.*MAL"):
        links = quotation_links(archives)
        scripture_text(scripture_unit("MAL"), archives, links=links)


def test_every_exception_is_used(patched):
    patched(versification, "EXCEPTIONS")["MAL 3:19-24"] = {
        "target": "MAL 4:1-6",
        "why": "x",
    }
    with pytest.raises(CheckFailed, match=r"no quotation uses: \['MAL 3:19-24'\]"):
        quotations.reviewed_rows()


def test_an_unlinked_alternative_cannot_use_an_exception(patched):
    # Q095 links Exodus 32:1 and keeps Turpie's "or 23" as an alternative.
    patched(versification, "EXCEPTIONS")["EXO 32:23"] = {
        "target": "EXO 32:22",
        "why": "x",
    }
    with pytest.raises(CheckFailed, match=r"no quotation uses: \['EXO 32:23'\]"):
        quotations.reviewed_rows()


def test_mapped_run_must_match_its_target_run(patched):
    patched(versification, "EXCEPTIONS")["JOL 2:28-32"] = {
        "target": "JOL 3:1-4",
        "why": "x",
    }
    with pytest.raises(CheckFailed, match="misaligned mapping: JOL 2:28-32"):
        lxx_to_edition(parse_verse("JOL 2:30"))


def test_an_exception_gives_its_printed_verses_once(patched):
    # One that numbers as the King James Bible does takes them from the file.
    patched(versification, "EXCEPTIONS")["JOL 2:28-32"]["target"] = "JOL 3:1-5"
    with pytest.raises(CheckFailed, match="Mapping given twice: JOL 2:28-32"):
        lxx_to_edition(parse_verse("JOL 2:30"))


def test_an_exception_must_change_a_number(patched):
    patched(versification, "EXCEPTIONS")["GEN 1:1"] = {"numbering": "kjv", "why": "x"}
    with pytest.raises(CheckFailed, match="Mapping that changes nothing: GEN 1:1"):
        lxx_to_edition(parse_verse("GEN 1:2"))


def test_mapping_is_checked_whole(patched):
    exceptions = patched(versification, "EXCEPTIONS")
    exceptions["JOL 2:32"] = {"target": "JOL 3:5", "why": "x"}
    # Even a reference no exception reaches.
    with pytest.raises(CheckFailed, match="Overlapping mappings of JOL 2:32"):
        lxx_to_edition(parse_verse("GEN 1:1"))


def test_a_lettered_verse_maps_alone_and_never_joins_a_range(scripture):
    assert lxx_to_edition(parse_verse("PRO 22:8")) == parse_verse("PRO 22:8a")
    assert printed(parse_verse("PRO 22:8a"), scripture)
    mapped = versification.mapped_passages(parse_passage("PRO 22:7-9"))
    assert list(map(str, mapped)) == ["PRO 22:7", "PRO 22:8a", "PRO 22:9"]


def test_a_link_to_a_lettered_verse_prints_its_label(links):
    [link] = [l for l in links["PRO"] if "Q216" in l["row_ids"]]
    assert link["origin"] == parse_verse("PRO 22:8a")
    assert _link_usfm(link) == r"\x - \xo 22:8a \xt 2 Corinthians 9:7\x*"


# How far a run's words may be outscored by the same run a few verses off.
MARGIN = 0.1
SHIFTS = (-3, -2, -1, 1, 2, 3)


def listed_runs(code):
    """A book's runs that pair verses, as (run, edition verses, King James verses)."""
    return [
        (run, versification.verses(run["edition"]), versification.verses(run["kjv"]))
        for run in versification.DATA["kjv"].get(code, [])
        if run["edition"] and run["kjv"]
    ]


def unplaced(texts):
    """What the file leaves without a place: the King James verses that no
    verse of the edition reaches and no run lists as wanting, and the
    edition's verses whose counterparts the King James Bible lacks."""
    missing, lost = [], []
    for code, kjv in texts.books.items():
        reached = {
            counterpart
            for verse in texts.edition.order[code]
            for counterpart in versification.to_kjv(verse)
        }
        lost += sorted(map(str, reached - set(texts.kjv.words)))
        wanting = {
            verse
            for run in versification.DATA["kjv"].get(code, [])
            if not run["edition"]
            for verse in versification.verses(run["kjv"])
        }
        assert not wanting & reached, f"Wanting and reached: {code}"
        missing += [
            str(verse)
            for verse in texts.kjv.order[kjv]
            if verse.number != versification.TITLE
            and verse not in reached
            and verse not in wanting
        ]
    return missing, lost


def test_every_verse_of_both_bibles_has_its_place(texts):
    assert unplaced(texts) == ([], [])


def test_a_verse_faces_the_verses_that_face_it(texts):
    for code in texts.books:
        for verse in texts.edition.order[code]:
            for counterpart in versification.to_kjv(verse):
                assert verse in versification.from_kjv(counterpart), verse


def test_a_lost_run_leaves_its_verses_without_a_place(texts, patched):
    # Joel 3:1-5 is the King James Bible's 2:28-32; unlisted, it would keep
    # its number, which Joel 4:1 has.
    runs = patched(versification, "DATA")["kjv"]["JOL"]
    runs[:] = [run for run in runs if run["edition"] != "JOL 3:1-5"]
    with pytest.raises(CheckFailed, match="Another verse has the place of JOL 3:1"):
        unplaced(texts)


def test_a_verse_the_edition_lacks_is_listed(texts, patched):
    # The Greek lacks the promise of the Branch, Jeremiah 33:14-26.
    runs = patched(versification, "DATA")["kjv"]["JER"]
    assert {"edition": None, "kjv": "JER 33:14-26"} in runs
    runs.remove({"edition": None, "kjv": "JER 33:14-26"})
    missing, _ = unplaced(texts)
    assert missing == [f"JER 33:{verse}" for verse in range(14, 27)]


def test_a_run_a_verse_off_takes_the_place_of_another_verse(patched):
    [run] = [
        run
        for run in patched(versification, "DATA")["kjv"]["JOL"]
        if run["edition"] == "JOL 3:1-5"
    ]
    run["kjv"] = "JOL 2:27-31"
    with pytest.raises(CheckFailed, match="Another verse has the place of JOL 2:27"):
        versification.to_kjv(parse_verse("JOL 2:27"))


def test_two_runs_cannot_reach_one_verse(patched):
    patched(versification, "DATA")["kjv"]["JOL"].append(
        {"edition": "JOL 1:1", "kjv": "JOL 2:28", "by": "words"}
    )
    with pytest.raises(CheckFailed, match="Two runs reach JOL 2:28"):
        versification.to_kjv(parse_verse("GEN 1:1"))


@pytest.mark.parametrize(
    "change,refusal",
    [
        ({"by": "guess"}, "without its witness"),
        ({"by": "reading"}, "A reading gives its reason"),
        ({"why": "x"}, "A reading gives its reason"),
        ({"kjv": "HOS 2:28-32"}, "outside its book"),
        ({"edition": "HOS 1:1-5"}, "outside its book"),
    ],
)
def test_a_malformed_run_is_refused(patched, change, refusal):
    [run] = [
        run
        for run in patched(versification, "DATA")["kjv"]["JOL"]
        if run["edition"] == "JOL 3:1-5"
    ]
    run.update(change)
    with pytest.raises(CheckFailed, match=refusal):
        versification.to_kjv(parse_verse("GEN 1:1"))


def test_a_run_keeps_out_of_the_apocrypha(patched):
    patched(versification, "DATA")["kjv"]["DAG"].append(
        {"edition": "DAG 3:24-28", "kjv": "DAN 3:24-28", "by": "words"}
    )
    with pytest.raises(CheckFailed, match="within the Apocrypha: DAG 3:24-28"):
        versification.to_kjv(parse_verse("GEN 1:1"))


def test_a_passage_is_mapped_verse_by_verse():
    # Never by its ends: Jeremias 25:13-16 stands in two places.
    jeremias = versification.kjv_passages(parse_passage("JER 25:13-16"))
    assert list(map(str, jeremias)) == ["JER 25:13", "JER 49:34-36"]
    cup = versification.edition_passages(parse_passage("JER 25:13-16"))
    assert list(map(str, cup)) == ["JER 25:13", "JER 32:15-16"]
    back = versification.edition_passages(parse_passage("JER 31:31-34"))
    assert list(map(str, back)) == ["JER 38:31-34"]
    psalm = versification.kjv_passages(parse_passage("PSA 33:13-17"))
    assert list(map(str, psalm)) == ["PSA 34:12-16"]


def test_an_addition_has_no_counterpart():
    assert versification.to_kjv(parse_verse("PRO 22:8a")) == ()
    assert versification.to_kjv(parse_verse("DAG 3:24")) == ()
    assert versification.to_kjv(parse_verse("PSA 151:1")) == ()
    with pytest.raises(CheckFailed, match="No King James counterpart: TOB"):
        versification.to_kjv(parse_verse("TOB 1:1"))


def test_malachias_ends_in_another_order():
    # Brenton has Elias before the law of Moses; the King James Bible after.
    ends = {
        verse: versification.to_kjv(parse_verse(f"MAL 4:{verse}"))[0].number
        for verse in range(1, 7)
    }
    assert ends == {1: 1, 2: 2, 3: 3, 4: 5, 5: 6, 6: 4}


def test_proverbs_sea_clause_overlaps_the_next_king_james_verse():
    first, second = map(parse_verse, ("PRO 8:28", "PRO 8:29"))
    assert versification.to_kjv(first) == (first, second)
    assert versification.to_kjv(second) == (second,)
    assert versification.from_kjv(first) == (first,)
    assert versification.from_kjv(second) == (first, second)


@pytest.mark.parametrize(
    "pairs",
    [
        {"PRO 8:28": "PRO 8:28-29"},
        {"PRO 8:28": "PRO 8:28", "PRO 8:29": "PRO 8:30"},
        {"PRO 8:28": "PRO 8:28", "PRO 8:29": "PRO 8:28"},
        {"PRO 8:28": "PRO 8:28-29", "PRO 8:29": ""},
    ],
)
def test_explicit_pairs_must_cover_only_the_declared_run(patched, pairs):
    run = next(r for r in patched(versification, "DATA")["kjv"]["PRO"] if "pairs" in r)
    run["pairs"] = pairs
    with pytest.raises(CheckFailed, match="verse pairs|Verse pairs"):
        versification.to_kjv(parse_verse("PRO 8:28"))


def test_a_run_rests_on_the_witness_it_names(texts, table):
    """A run by the table is the table's account of the verse, and any other
    run departs from it; so does no verse that the file leaves unlisted."""
    departs = {}
    for code in texts.books:
        listed = {}
        for run in versification.DATA["kjv"].get(code, []):
            if run["edition"]:
                for verse in versification.verses(run["edition"]):
                    listed[verse] = run
        for verse in texts.edition.order[code]:
            ours = sorted(map(str, versification.to_kjv(verse)))
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
                departs.setdefault(listed[verse]["edition"], []).append(ours != tabled)
    # A run departs from the table if any of its verses does: of two verses
    # that face one, the table may give one of them the same.
    assert [run for run, verses in departs.items() if not any(verses)] == []


def outscored(texts, ours, theirs):
    """Whether the same run a few verses off shares more words than the run.

    Verse for verse, where the run pairs its verses: a long run and the same
    run a verse off have nearly the same words between them.
    """

    def score(facing):
        if len(facing) != len(ours):
            return alignment.similarity(
                texts.weight, texts.edition.bag(ours), texts.kjv.bag(facing)
            )
        return sum(map(texts.similarity, ours, facing)) / len(ours)

    rivals = [
        score(shifted) for k in SHIFTS if (shifted := texts.kjv.shifted(theirs, k))
    ]
    return max(rivals, default=0) > score(theirs) + MARGIN


def runs_to_compare(texts, code):
    """A book's runs whose words can be compared: those the table or the
    words give, and each chapter's verses that keep their numbers."""
    named = {
        verse
        for run in versification.DATA["kjv"].get(code, [])
        if run["edition"]
        for verse in versification.verses(run["edition"])
    }
    found = [
        (run["edition"], ours, theirs)
        for run, ours, theirs in listed_runs(code)
        if run["by"] in {"table", "words"}
        and not any(verse.number == versification.TITLE for verse in theirs)
    ]
    chapters = {}
    for verse in texts.edition.order[code]:
        if verse not in named and versification.to_kjv(verse):
            chapters.setdefault(verse.chapter, []).append(verse)
    for chapter, ours in chapters.items():
        theirs = [versification.to_kjv(verse)[0] for verse in ours]
        found.append((f"{code} {chapter}", ours, theirs))
    return found


def test_the_words_bear_out_every_run(texts):
    flagged = {
        name
        for code in texts.books
        for name, ours, theirs in runs_to_compare(texts, code)
        if outscored(texts, ours, theirs)
    }
    assert flagged == set()


def test_a_run_a_verse_off_is_outscored(texts):
    # The check must still tell a run from its neighbour: most runs, moved a
    # verse, share fewer words than where they stand.
    caught = total = 0
    for code in texts.books:
        for _, ours, theirs in runs_to_compare(texts, code):
            if len(ours) < 3 or not (moved := texts.kjv.shifted(theirs, 1)):
                continue
            total += 1
            caught += outscored(texts, ours, moved)
    assert caught >= 0.9 * total


def test_every_relabelled_verse_is_printed_under_its_new_label(archives, scripture):
    for source, printed_as in versification.relabelled().items():
        labels = inventory(archives["brenton"][source.book])["chapters"]
        assert str(source.number) in labels[str(source.chapter)]
        assert printed(printed_as, scripture) and not printed(source, scripture)
