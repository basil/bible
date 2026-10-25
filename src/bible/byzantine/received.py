"""Whether the apparatuses establish a unit's Scrivener reading as the
Received Text's, and so which witness its note names.

Boyd's apparatus and the printed RP2026's mark a reading TR where Scrivener
and Stephanus agree, and SCR where Scrivener stands alone. A note names TR
only where every unit it is about is established so: an apparatus row on
it gives TR, and none gives SCR. Otherwise it names the printed edition the
King James translators followed there, where a decision in
edition/byzantine.json (editions) shows it from that edition or Scrivener's
account of it, as an Old Testament note names Valpy; and failing that the
King James Version, whose words it gives, as an Old Testament note names
Brenton.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Literal

from bible.byzantine.greek import accent_key, occurrences
from bible.byzantine.notes import edition_key
from bible.byzantine.rows import BoydNote, Disposition, Unit
from bible.byzantine.units import PRINTED_APPARATUS
from bible.checks import require
from bible.terminology import NEW_TESTAMENT

type Status = Literal["TR", "SCR", "disputed"] | None
type Rows = Mapping[tuple[str, int], BoydNote]

# The terms (edition/terminology.json) the notes name.
RECEIVED, KING_JAMES = "textus-receptus", "king-james-version"
# The terms an edition decision may name: the printed editions the King
# James translators followed.
NAMED = frozenset(NEW_TESTAMENT) - {RECEIVED, KING_JAMES}


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
    dispositions: Sequence[Disposition],
    units: Sequence[Unit],
    found: Rows,
    editions: Mapping[str, Mapping[str, str]],
) -> dict[str, str]:
    """The term each note of the reconciliation names, by its key: the
    Received Text where every unit it is about is established as its,
    the King James Version otherwise. A note is about its row's unit, the
    units whose rows its owner executes (covered_by), and those of every
    row that holds the same note (a combined note). A correction of shared
    Greek is keyed by its verse and is about no unit; its "Or," note names
    no witness. An edition decision names the printed edition instead of the
    King James Version for its note and every other note about the same
    units, and stops the build on a term it may not name, a key that names
    no note or more than one, a note that names no witness, one the
    apparatuses establish as the Received Text's, or a second decision about
    the same units."""
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
    named = {
        key: (
            RECEIVED
            if ids and all(status(by_id[i], found) == "TR" for i in ids)
            else KING_JAMES
        )
        for key, ids in about.items()
    }
    # A decision names one note by the edition's key, "unit TR" for a unit's
    # one note.
    keys: defaultdict[str, list[str]] = defaultdict(list)
    for key in named:
        keys[edition_key(key)].append(key)
    unknown = sorted(
        f"{key}: {decision['label']}"
        for key, decision in editions.items()
        if decision["label"] not in NAMED
    )
    require(not unknown, f"Edition decisions that name no printed edition: {unknown}")
    stale = sorted(
        key
        for key in editions
        if len(keys.get(key, ())) != 1
        or not about[keys[key][0]]
        or named[keys[key][0]] == RECEIVED
    )
    require(
        not stale,
        f"Edition decisions that name no one note or change nothing, or override "
        f"an established Received Text: {stale}",
    )
    # The notes about the same units name the same edition, from one decision.
    decided: defaultdict[frozenset[str], list[str]] = defaultdict(list)
    for key in editions:
        decided[frozenset(about[keys[key][0]])].append(key)
    twice = sorted(" and ".join(sorted(ks)) for ks in decided.values() if len(ks) > 1)
    require(not twice, f"Edition decisions about the same units; merge them: {twice}")
    label = {ids: editions[ks[0]]["label"] for ids, ks in decided.items()}
    return {
        key: label.get(frozenset(about[key]), witness) for key, witness in named.items()
    }


def misquoted(
    editions: Mapping[str, Mapping[str, str]], scrivener: Mapping[str, Sequence[str]]
) -> list[str]:
    """The edition decisions whose verse in Scrivener's accented text lacks
    the words they say it reads (reads), or has those they say it lacks
    (lacks), compared without case, punctuation, or grave and acute."""
    errors = []
    for key, decision in editions.items():
        ref = key.partition("#")[0].removesuffix(" TR")
        words = [accent_key(w) for w in scrivener.get(ref, ())]
        for field, present in (("reads", True), ("lacks", False)):
            if field not in decision:
                continue
            run = [accent_key(w) for w in decision[field].split()]
            if bool(occurrences(words, run)) != present:
                fact = "lacks" if present else "has"
                errors.append(f"{key}: Scrivener's {ref} {fact} {decision[field]}")
    return errors
