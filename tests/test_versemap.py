"""Quotation reference mapping checks for the prepared Brenton versification."""

import pytest

from bible import quotations, versemap
from bible.checks import CheckFailed
from bible.crossrefs import _link_usfm, quotation_links
from bible.edition import scripture_unit
from bible.prepare import scripture_text
from bible.usfm import inventory
from bible.versemap import lxx_to_edition, parse


def printed(reference, scripture):
    code, chapter, verse = parse(reference)
    return verse in inventory(scripture[code])["chapters"].get(str(chapter), [])


@pytest.mark.parametrize(
    "source,target",
    [
        ("JOL 2:28", "JOL 3:1"),
        ("JOL 2:32", "JOL 3:5"),
        ("HOS 1:10", "HOS 2:1"),
    ],
)
def test_source_numbering_exceptions_name_printed_verses(scripture, source, target):
    assert lxx_to_edition(source) == target
    assert printed(target, scripture)


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
    patched(versemap, "EXCEPTIONS")["MAL 3:19-24"] = {
        "target": "MAL 4:1-6",
        "why": "x",
    }
    with pytest.raises(CheckFailed, match=r"no quotation uses: \['MAL 3:19-24'\]"):
        quotations.reviewed_rows()


def test_an_unlinked_alternative_cannot_use_an_exception(patched):
    # Q095 links Exodus 32:1 and keeps Turpie's "or 23" as an alternative.
    patched(versemap, "EXCEPTIONS")["EXO 32:23"] = {"target": "EXO 32:22", "why": "x"}
    with pytest.raises(CheckFailed, match=r"no quotation uses: \['EXO 32:23'\]"):
        quotations.reviewed_rows()


def test_mapped_run_must_match_its_target_run(patched):
    patched(versemap, "EXCEPTIONS")["JOL 2:28-32"]["target"] = "JOL 3:1-4"
    with pytest.raises(CheckFailed, match="misaligned mapping: JOL 2:28-32"):
        lxx_to_edition("JOL 2:30")


def test_mapping_is_checked_whole(patched):
    exceptions = patched(versemap, "EXCEPTIONS")
    exceptions["JOL 2:32"] = {"target": "JOL 3:5", "why": "x"}
    # Even a reference no exception reaches.
    with pytest.raises(CheckFailed, match="Overlapping mappings of JOL 2:32"):
        lxx_to_edition("GEN 1:1")


def test_a_lettered_verse_maps_alone_and_never_joins_a_range(scripture):
    assert lxx_to_edition("PRO 22:8") == "PRO 22:8a"
    assert printed("PRO 22:8a", scripture)
    assert versemap.mapped_passages("PRO 22:7-9") == [
        "PRO 22:7",
        "PRO 22:8a",
        "PRO 22:9",
    ]
    with pytest.raises(CheckFailed, match="Lettered verse in a range"):
        versemap.expand("PRO 22:8a-9")


def test_a_link_to_a_lettered_verse_prints_its_label(links):
    [link] = [l for l in links["PRO"] if "Q216" in l["row_ids"]]
    assert link["origin"] == "PRO 22:8a"
    assert _link_usfm(link) == r"\x - \xo 22:8a \xt 2 Corinthians 9:7\x*"
