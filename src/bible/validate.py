"""Validating the pinned sources against the edition before anything is built:
the archive hashes, the marginal notes, divided sources, and the overlapping
Nehemias witness, reported in build/validation.json."""

import difflib

from bible import edition, paths
from bible.checks import require
from bible.edition import brenton_source_use, scripture_unit, source_id
from bible.files import write_json
from bible.notes import marginal_notes
from bible.sources import load_archives
from bible.usfm import chapter_parts, inventory, renumber_chapters


def validate():
    """Check the pinned sources and report on them; returns their books."""
    archives = load_archives()
    notes = marginal_notes()
    units = edition.MANIFEST["scripture"]
    require(
        set(notes) <= {u["id"] for u in units if u["source"] == "kjv"},
        "Marginal notes name a book outside the KJV New Testament",
    )
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
        "kjv_marginal_notes": sum(len(n) for n in notes.values()),
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
