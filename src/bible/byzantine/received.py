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
Brenton. A note that would name the King James Version, or a correction of
shared Greek that would name no witness, names instead a version (VERSIONS)
where a decision (note_witnesses) cites it for the former English words.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

from bible import usj
from bible.byzantine.greek import accent_key, occurrences
from bible.byzantine.notes import edition_key
from bible.byzantine.rows import BoydNote, Disposition, Unit
from bible.byzantine.units import PRINTED_APPARATUS
from bible.checks import require
from bible.notes import quotation_of
from bible.terminology import NEW_TESTAMENT

type Status = Literal["TR", "SCR", "disputed"] | None
type Rows = Mapping[tuple[str, int], BoydNote]

# The terms (edition/terminology.json) the notes name.
RECEIVED, KING_JAMES = "textus-receptus", "king-james-version"
# The versions a note witness decision may cite for the former English words,
# whatever Greek stands behind them (edition/byzantine.json note_witnesses).
VERSIONS = frozenset({"vulgate"})
# The terms an edition decision may name: the printed editions the King
# James translators followed.
NAMED = frozenset(NEW_TESTAMENT) - {RECEIVED, KING_JAMES} - VERSIONS


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
    note_witnesses: Sequence[Mapping[str, Any]] = (),
) -> dict[str, str]:
    """The term each note of the reconciliation names, by its key: the
    Received Text where every unit it is about is established as its,
    the King James Version otherwise. A note is about its row's unit, the
    units whose rows its owner executes (covered_by), and those of every
    row that holds the same note (a combined note). A correction of shared
    Greek is keyed by its verse and is about no unit; its "Or," note names
    no witness unless a note witness decision cites one. An edition
    decision names the printed edition instead of the King James Version
    for its note and every other note about the same units, and stops the
    build on a term it may not name, a key that names no note or more than
    one, a note that names no witness, one the apparatuses establish as the
    Received Text's, or a second decision about the same units. A note witness
    decision names a version (VERSIONS) for each note it lists, a replaced
    reading or a correction of shared Greek whose former words it quotes, and
    stops the build on any other term, a key that names no one note or is listed
    twice, another kind of note, another quotation, a note the Received Text or
    an edition decision already labels, or another note about the same units
    that it does not
    cite alike."""
    by_id = {u["id"]: u for u in units}
    covered: defaultdict[str, set[str]] = defaultdict(set)
    for row in dispositions:
        if row.get("covered_by"):
            covered[row["covered_by"]].add(row["unit"])
    about: defaultdict[str, set[str]] = defaultdict(set)
    held_notes: dict[str, usj.Node] = {}
    for row in dispositions:
        ids = {i for i in (row["unit"], *covered[row["unit"]]) if i in by_id}
        held = [e["note"] for e in row.get("edits", []) if "note" in e]
        held += [n for n in (row.get("note"), row.get("source_note")) if n]
        for note in held:
            about[note["x-key"]] |= ids
            held_notes[note["x-key"]] = note
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
    result = {
        key: label.get(frozenset(about[key]), witness) for key, witness in named.items()
    }
    # An explicitly cited witness to the former words is independent of the
    # Greek edition behind them. It can also name a shared-Greek correction.
    decided_notes: set[str] = set()
    cited: dict[str, str] = {}
    for decision in note_witnesses:
        witness = decision["witness"]
        require(witness in VERSIONS, f"Unknown note witness: {witness}")
        for key in decision["notes"]:
            require(key not in decided_notes, f"Repeated note witness decision: {key}")
            decided_notes.add(key)
            matches = keys.get(key, [])
            require(len(matches) == 1, f"Note witness names no one note: {key}")
            source_key = matches[0]
            note = held_notes[source_key]
            require(
                note["x-scope"]["kind"] in {"rendering", "replace"},
                f"Note witness does not name a replaced reading: {key}",
            )
            # The words the note prints for the lemma (notes.for_edition).
            quotation = quotation_of(note)
            require(
                quotation == decision["reading"],
                f"Note witness reading does not match {key}: {quotation!r}",
            )
            # The Received Text and an edition decision each stand on the
            # Greek; a version cited for the English does not displace them.
            require(
                result[source_key] == KING_JAMES,
                f"Note witness overrides the Received Text or an edition "
                f"decision; remove one: {key}",
            )
            result[source_key] = witness
            cited[source_key] = witness
    # The notes about the same units cite the same version, as they name the
    # same edition.
    groups: defaultdict[frozenset[str], set[str]] = defaultdict(set)
    for key in named:
        if about[key]:
            groups[frozenset(about[key])].add(key)
    split = sorted(
        " and ".join(sorted(ks))
        for ks in groups.values()
        if ks & cited.keys() and len({cited.get(k) for k in ks}) > 1
    )
    require(
        not split,
        f"Note witness decisions that cite notes about the same units "
        f"differently; list them alike: {split}",
    )
    return result


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
