"""Validating the pinned sources against the edition before anything is built:
the archive hashes, the notes and corrections, divided sources, and the overlapping
Nehemias witness, reported in build/validation.json."""

import difflib

from bible import edition, notes, paths
from bible.checks import require
from bible.edition import brenton_source_use, scripture_unit, source_id
from bible.files import write_json
from bible.prepare import recorder
from bible.sources import load_archives
from bible.usfm import chapter_parts, inventory, renumber_chapters


def validate():
    """Check the pinned sources and report on them; returns their books."""
    archives = load_archives()
    units = edition.MANIFEST["scripture"]
    # A unit checks only the exceptions and corrections keyed to it, so one keyed
    # to anything the edition doesn't print would go unused unnoticed.
    brenton_units = {u["id"] for u in units if u["source"] == "brenton"}
    unprinted = {k.split(" ")[0] for k in notes.BRENTON_NOTES["notes"]} - brenton_units
    require(
        not unprinted,
        f"Brenton note exceptions name a book outside the edition: {sorted(unprinted)}",
    )
    # A misspelt field would be read as no override, and the entry as used. The
    # 1611 notes also say where George's lemma is found in the verse, and
    # Brenton's which occurrence of a repeated lemma is meant.
    note_fields = {"lemma", "note", "sentence", "why"}
    placement_fields = {"anchor", "occurrence", "verse", "uncategorized"}
    for exceptions, fields in (
        (notes.BRENTON_NOTES["notes"], note_fields | {"occurrence"}),
        (notes.KJV_NOTES["notes"], note_fields | placement_fields),
    ):
        unknown = sorted(k for k, v in exceptions.items() if not v.keys() <= fields)
        require(not unknown, f"Note exceptions with unknown fields: {unknown}")
    # A correction replaces its from with its to, and a misspelt flag would be
    # read as none.
    malformed = sorted(
        k
        for corrections in (
            notes.BRENTON_NOTES["corrections"],
            notes.KJV_NOTES["corrections"],
        )
        for k, v in corrections.items()
        if not {"from", "to"} <= v.keys() <= {"from", "to", "why", "uncategorized"}
    )
    require(
        not malformed, f"Note corrections with missing or unknown fields: {malformed}"
    )
    # The edition gives the reason for each of its departures from its sources
    # and from its rules.
    unexplained = sorted(
        k
        for entries in (
            notes.BRENTON_NOTES["notes"],
            notes.BRENTON_NOTES["corrections"],
            notes.KJV_NOTES["notes"],
            notes.KJV_NOTES["corrections"],
        )
        for k, v in entries.items()
        if not v.get("why")
    )
    require(not unexplained, f"Note exceptions without a why: {unexplained}")
    # A Brenton exception's occurrence says which of a repeated lemma is meant,
    # so without a lemma it would go unused.
    pointless = sorted(
        k
        for k, v in notes.BRENTON_NOTES["notes"].items()
        if "occurrence" in v and v.get("lemma") is None
    )
    require(
        not pointless, f"Note exceptions with an occurrence but no lemma: {pointless}"
    )
    # Parsing the 1611 notes applies their corrections, so it follows the checks
    # on their fields.
    marginal = notes.marginal_notes()
    require(
        set(marginal) <= {u["id"] for u in units if u["source"] == "kjv"},
        "Marginal notes name a book outside the KJV New Testament",
    )
    printed_sources = set(brenton_source_use()) | {
        source_id(e)
        for e in edition.ordered_entries()
        if "section" not in e and e.get("source") == "brenton"
    }
    corrected_sources = {k.split(" ")[0] for k in notes.BRENTON_NOTES["corrections"]}
    unprinted_sources = sorted(corrected_sources - printed_sources)
    require(
        not unprinted_sources,
        "Brenton corrections name a source the edition doesn't print: "
        f"{unprinted_sources}",
    )
    # Apply them as the build does, so the two can't disagree.
    for source in sorted(corrected_sources):
        notes.corrected_brenton(
            source, archives["brenton"][source], recorder(None, source)
        )
    # Only an anchor is categorized, so the flag on any other exception is unused.
    unused = sorted(
        k
        for k, v in notes.KJV_NOTES["notes"].items()
        if "uncategorized" in v and "anchor" not in v
    )
    require(not unused, f"Uncategorized flag without an anchor: {unused}")
    # A source divided between units must be printed whole, each chapter once.
    divided = {}
    for u in units:
        if "chapters" in u:
            first, last = u["chapters"]
            divided.setdefault((u["source"], source_id(u)), []).extend(
                str(c) for c in range(first, last + 1)
            )
    for (source, code), chapters in divided.items():
        require(
            chapters == list(inventory(archives[source][code])["chapters"]),
            f"Divided source not printed whole: {source}/{code}",
        )
    source_use = brenton_source_use()
    # Explain the overlapping witness without modifying either original file.
    nehemias = scripture_unit("NEH")
    first, last = nehemias["chapters"]
    _, combined_chapters = chapter_parts(archives["brenton"][source_id(nehemias)])
    _, standalone_nehemias_witness = chapter_parts(archives["brenton"]["NEH"])
    renumbered_nehemias_chapters = "".join(
        renumber_chapters(combined_chapters[first - 1 : last], first - 1)
    )
    standalone_nehemias_chapters = "".join(standalone_nehemias_witness)
    nehemias_source_diff = list(
        difflib.unified_diff(
            renumbered_nehemias_chapters.splitlines(True),
            standalone_nehemias_chapters.splitlines(True),
            fromfile=f"{source_id(nehemias)} chapters {first}-{last} (renumbered for comparison)",
            tofile="standalone NEH",
        )
    )
    paths.BUILD_DIR.mkdir(exist_ok=True)
    (paths.BUILD_DIR / "nehemias-differences.diff").write_text(
        "".join(nehemias_source_diff), encoding="utf-8"
    )
    report = {
        "scripture_units": len(units),
        "brenton_units": sum(u["source"] == "brenton" for u in units),
        "brenton_source_files": len(set(source_use)),
        "kjv_units": sum(u["source"] == "kjv" for u in units),
        "kjv_marginal_notes": sum(len(n) for n in marginal.values()),
        "source_verse_labels": sum(
            len(verses)
            for source, code in {("brenton", c) for c in source_use}
            | {("kjv", u["id"]) for u in units if u["source"] == "kjv"}
            for verses in inventory(archives[source][code])["chapters"].values()
        ),
        "nehemias_equal_after_whitespace_normalization": (
            " ".join(renumbered_nehemias_chapters.split())
            == " ".join(standalone_nehemias_chapters.split())
        ),
        "nehemias_diff_lines": len(nehemias_source_diff),
    }
    write_json(paths.BUILD_DIR / "validation.json", report)
    print("Validated pinned sources:", report, flush=True)
    return archives
