"""Whether the apparatuses establish a unit's Scrivener reading as the
Received Text's, and so which witness its note names.

Boyd's apparatus and the printed RP2026's mark a reading TR where Scrivener
and Stephanus agree, and SCR where Scrivener stands alone. A note names TR
only where every unit it is about is established so: an apparatus row on
it gives TR, and none gives SCR. Otherwise it names the King James Version,
whose words it gives, as the Old Testament's name Brenton unless Swete
establishes a manuscript.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Literal

from bible.byzantine.rows import BoydNote, Disposition, Unit
from bible.byzantine.units import PRINTED_APPARATUS

type Status = Literal["TR", "SCR", "disputed"] | None
type Rows = Mapping[tuple[str, int], BoydNote]

# The terms (edition/terminology.json) the notes name.
RECEIVED, KING_JAMES = "textus-receptus", "king-james-version"


def rows(tcgnt: Iterable[BoydNote], printed: Iterable[BoydNote]) -> Rows:
    """The apparatus rows that give the Received Text a reading, by the
    inventory and entry a unit's attachment names."""
    return {
        **{("tcgnt", n["entry"]): n for n in tcgnt},
        **{(PRINTED_APPARATUS, n["entry"]): n for n in printed},
    }


def status(unit: Unit, found: Rows) -> Status:
    """What the apparatus rows on a unit say its Scrivener reading is: TR,
    SCR, both (disputed), or nothing."""
    sigla = {
        siglum
        for attachment in unit["inventories"]
        if (attachment["inventory"], attachment["entry"]) in found
        for reading in found[(attachment["inventory"], attachment["entry"])]["tr"]
        for siglum in reading["sigla"]
        if siglum in {"TR", "SCR"}
    }
    if not sigla:
        return None
    return "disputed" if len(sigla) > 1 else "TR" if "TR" in sigla else "SCR"


def labels(
    dispositions: Sequence[Disposition], units: Sequence[Unit], found: Rows
) -> dict[str, str]:
    """The term each note of the reconciliation names, by its key: the
    Received Text where every unit it is about is established as its,
    the King James Version otherwise. A note is about its row's unit, the
    units whose rows its owner executes (covered_by), and those of every
    row that holds the same note (a combined note). A correction of shared
    Greek is keyed by its verse and is about no unit; its "Or," note names
    no witness."""
    by_id = {u["id"]: u for u in units}
    covered: defaultdict[str, set[str]] = defaultdict(set)
    for row in dispositions:
        if row.get("covered_by"):
            covered[row["covered_by"]].add(row["unit"])
    about: defaultdict[str, set[str]] = defaultdict(set)
    for row in dispositions:
        ids = {i for i in (row["unit"], *covered[row["unit"]]) if i in by_id}
        held = [e["note"] for e in row.get("edits", []) if "note" in e]
        held += [n for n in (row.get("note"), row.get("source_note")) if n]
        for note in held:
            about[note["x-key"]] |= ids
    return {
        key: (
            RECEIVED
            if ids and all(status(by_id[i], found) == "TR" for i in ids)
            else KING_JAMES
        )
        for key, ids in about.items()
    }
