"""The review: what the edition prints, for reading through, in build/review/.

    notes.md         every note, with the words it is about marked in its verse
    ccel.md          what came of CCEL's notes: the counts, the notes held
                     back for a decision about Codex Alexandrinus, and the
                     notes left out, each with its reason
    alexandrinus.md  every Alexandrine decision: its source, the passage before
                     and after, its footnotes, its derivation, and Swete
    numbering.md     where each verse stands in the King James Bible, with
                     both translations' words for what rests on the words alone
    byzantine.md     the reconciliation of the New Testament with the
                     Byzantine text in figures: dispositions, witnesses, the
                     invariants, and what matched nothing
    byzantine/       one file per New Testament book: every place the Greek
                     texts differ, with its witnesses, its disposition and
                     the English before and after, and the corrections of
                     the English where the Greek is shared
    text/            every unit as it is sent to be typeset
    changes.diff     what differs in all of these from the last review

The decisions themselves, each with its reason, are edition/*.json; the
review shows what they come to. It is written from the prepared edition and
is never read by the build.
"""

from __future__ import annotations

import difflib
import json
import shutil
from collections.abc import Mapping

import bible.ccel
import bible.policy
from bible import (
    assembly,
    byzantine,
    export,
    paths,
    pipeline,
    places,
    quotations,
    references,
    scripture,
    versification,
    web,
)
from bible.alexandrinus import APPENDIX
from bible.byzantine import review as byzantine_review
from bible.checks import require
from bible.files import json_text
from bible.policy import thaw
from bible.policy_schema import Swete
from bible.usfm import plain_text
from bible.usj import Document


def note_line(row: Mapping[str, object]) -> str:
    return (
        f"- `{row['key']}` [{row['rule']}; {row['style']}] {row['verse']}\n"
        f"  → {row['lemma'] or '(verse)'}: {row['note']}\n"
        + (
            f"  Source: {row['source']}\n"
            if row["style"] == "editorial reversal"
            else ""
        )
    )


def notes_report(edition: pipeline.Edition) -> str:
    return "# Notes\n\n" + "".join(
        f"## {code}\n\n" + "".join(map(note_line, rows)) + "\n"
        for code, rows in edition.notes.items()
        if rows
    )


def ccel_line(item: bible.ccel.Listed) -> str:
    place = f" {item.place}" if item.place else ""
    return f"- `{item.key}`{place}: {item.text}\n" + (
        f"  Source: `{item.source}`\n" if item.source else ""
    )


def ccel_report(report: bible.ccel.Report) -> str:
    """CCEL's notes: how many were set in Brenton's verses, and each that
    was not, with its reason, its would-be key or the chapter the words
    suggest, and its source for a correction to name."""
    reasons: dict[str, list[bible.ccel.Listed]] = {}
    for item in report.left_out:
        reasons.setdefault(item.reason, []).append(item)
    lines = [
        "# CCEL notes\n\n",
        f"- Pages read: {report.pages}\n",
        f"- Note bodies read: {report.bodies}\n",
        f"- Notes set in Brenton's verses: {report.inserted}, "
        f"{len(report.supplied)} of them in verses promotion supplied\n",
        f"- Notes eBible already has: {report.duplicates}\n",
        f"- Notes held back for a decision about Codex Alexandrinus: {len(report.held)}\n",
        f"- Notes left out: {len(report.left_out)}\n",
        "\n## Notes accounted for by eBible\n\n",
    ]
    for match in report.matched:
        lines.extend(
            [
                f"- `{match.key}` (`{match.place}`) retains `{match.retained}`: {match.reason}\n",
                f"  CCEL caller before {match.scope!r} (offset {match.offset}): {match.text}\n",
                f"  eBible caller before {match.retained_scope!r} (offset {match.retained_offset}): {match.other}\n",
                f"  Source: `{match.source}`\n",
            ]
        )
    lines.append("\n## Set in verses promotion supplied\n\n")
    lines += (f"- `{key}` as `{printed}`\n" for key, printed in report.supplied)
    lines.extend(
        [
            "\n## Held back for a decision about Codex Alexandrinus\n\n",
            "Each would be set under the key shown; a decision in alexandrinus.json "
            "under that key brings it in.\n\n",
            *map(ccel_line, report.held),
        ]
    )
    for reason, items in sorted(reasons.items()):
        lines.append(f"\n## Left out: {reason}\n\n")
        lines += map(ccel_line, items)
    return "".join(lines)


def placed(
    policy: bible.policy.Policy, code: str, reference: str
) -> tuple[str, str] | None:
    """Where the edition prints a verse of one of Brenton's files: its unit
    and the verse's reference there."""
    ebible = assembly.unit_verse(policy, code, reference)
    if ebible is None:
        return None
    require(
        ebible not in versification.undivided(policy=policy),
        f"Review of a verse whose printed verse depends on its words: {ebible}",
    )
    moved = versification.relabelled(policy=policy).get(ebible, ebible)
    return ebible.book, moved.label


def swete_record(swete: Swete) -> str:
    return (
        f"Swete {swete['volume']} p. {swete['page']} ({swete['evidence']}; "
        f"agrees={swete['agrees']}): {swete['reading']}"
    )


def context(verses: Mapping[str, scripture.Verse], wanted: set[str]) -> str:
    """The wanted verses with the one before and the one after."""
    labels = list(verses)
    found = [n for n, label in enumerate(labels) if label in wanted]
    if not found:
        return "(No verse here.)"
    return "\n".join(
        f"{label} {scripture.plain(verses[label].text)}"
        for label in labels[max(0, min(found) - 1) : max(found) + 2]
    )


def alexandrinus_report(read: pipeline.Read, edition: pipeline.Edition) -> str:
    policy = edition.policy
    data = policy.alexandrinus
    sources: dict[str, dict[str, scripture.Verse]] = {}
    printed: dict[str, dict[str, scripture.Verse]] = {}
    borrowed_from: dict[str, dict[str, scripture.Verse]] = {}

    def verses(
        cache: dict[str, dict[str, scripture.Verse]],
        docs: Mapping[str, Document],
        code: str,
    ) -> dict[str, scripture.Verse]:
        if code not in cache:
            cache[code] = scripture.verses(docs[code])
        return cache[code]

    # Every note's row, by its key, by the key before the "@" of one that
    # has it, and by its unit and verse, in the order the review lists them.
    listed = [(unit, row) for unit, rows in edition.notes.items() for row in rows]
    by_key: dict[str, list[int]] = {}
    by_stem: dict[str, list[int]] = {}
    by_verse: dict[tuple[str, str], list[int]] = {}
    for index, (unit, row) in enumerate(listed):
        by_key.setdefault(row["key"], []).append(index)
        stem, at, _ = row["key"].partition("@")
        if at:
            by_stem.setdefault(stem, []).append(index)
        by_verse.setdefault((unit, row["reference"]), []).append(index)
    lines = ["# Alexandrine readings\n\n"]
    audit = []
    for section in ("readings", "passages", "kept"):
        for key, decision in data[section].items():
            code = references.book_of(key.removeprefix(f"{APPENDIX} "))
            # The verse a decision's note stands in, whatever source follows
            # its reference (GEN 1:2#2, 2CH 2:12 CCEL, BAK 1KI 2:35a).
            target = decision.get("target", key).removeprefix(f"{APPENDIX} ")
            wanted = {quotations.note_verse(target).split()[1]}
            for edit in decision.get("edits", ()):
                wanted.add(edit["target"].split()[-1])
            for insertion in decision.get("insertions", ()):
                wanted.update(v["reference"] for v in insertion["verses"])
                anchor = insertion.get("after", insertion.get("before"))
                assert anchor is not None
                wanted.add(anchor)
            for move in decision.get("moves", ()):
                moved = references.parse_passage(f"{code} {move['verses']}")
                # The verse the run leaves behind, where its other note stands.
                order = list(verses(sources, read.brenton, code))
                behind = order[order.index(moved.first.label) - 1]
                wanted.update(
                    {behind, moved.first.label, moved.last.label, move["before"]}
                )
            wanted = {w for w in wanted if ":" in w and "-" not in w}
            # An omitted run is shown with its neighbours apart from the rest,
            # so that the chapters between them are not printed as well; a
            # decision that only omits verses is shown by its runs alone.
            runs = [
                {*omission["verses"], omission["note_target"]}
                for omission in decision.get("omissions", ())
            ]
            wanted -= {v for run in runs for v in run}
            groups = ([wanted] if wanted or not runs else []) + runs
            source = decision.get("appendix", decision.get("source_note", ""))
            if "kjv" in decision:
                source = f"Authorized Version, {key}" + (
                    f"; {source}" if source else ""
                )
            before = "\n\n".join(
                context(verses(sources, read.brenton, code), group) for group in groups
            )
            if "kjv" in decision:
                borrowed = {v.label for v in references.parse_passage(key).verses}
                before += "\n\nKing James source:\n\n" + context(
                    verses(borrowed_from, read.kjv, code), borrowed
                )
            placements: list[dict[str, set[str]]] = []
            for group in groups:
                targets: dict[str, set[str]] = {}
                for reference in group:
                    where = placed(policy, code, reference)
                    if where:
                        targets.setdefault(where[0], set()).add(where[1])
                placements.append(targets)
            keys = {
                key,
                *decision.get("note_edits", ()),
                *decision.get("source_notes", ()),
            }
            found = {
                *(index for k in keys for index in by_key.get(k, ())),
                *by_stem.get(key, ()),
                *(
                    index
                    for targets in placements
                    for unit, references_ in targets.items()
                    for reference in references_
                    for index in by_verse.get((unit, reference), ())
                ),
            }
            footnotes = [listed[index][1] for index in sorted(found)]
            derivations = [
                {"target": item.get("target", key), **item["english"]}
                for item in ([decision] if "english" in decision else [])
                + list(decision.get("edits", ()))
                if item.get("english")
            ] + [
                {"target": f"{code} {verse['reference']}", **verse["english"]}
                for insertion in decision.get("insertions", ())
                for verse in insertion["verses"]
                if "english" in verse
            ]
            swete = decision["swete"]
            lines.append(
                f"## {key} — {section}\n\n"
                f"Source: {plain_text(source)}\n\n"
                f"Before:\n\n{before}\n\n"
                "After:\n\n"
                + (
                    "\n".join(
                        context(verses(printed, edition.documents, unit), references)
                        for targets in placements
                        for unit, references in targets.items()
                    )
                    or "(Not printed in a book.)"
                )
                + "\n\n"
                + "".join(
                    f"Footnote: {row['lemma'] or '(verse)'}: {row['note']}\n"
                    for row in footnotes
                )
                + "".join(
                    f"\nCompanion note {identity}: {plain_text(edit['from'])}\n"
                    f"Reason for rewriting it: {edit['why']}\n"
                    for identity, edit in decision.get("note_edits", {}).items()
                )
                + "".join(
                    f"\nDerivation ({proof['target']}): "
                    + json.dumps(thaw(proof), ensure_ascii=False)
                    + "\n"
                    for proof in derivations
                )
                + f"\nSupplied: {', '.join(decision.get('supplied', ())) or 'none'}\n\n"
                + "".join(
                    f"Omission: {', '.join(omission['verses'])}\n\n"
                    # A reading's run rests on the reading's reason and record.
                    + (
                        f"Reason: {omission['why']}\n\n"
                        f"{swete_record(omission['swete'])}\n\n"
                        if "why" in omission
                        else ""
                    )
                    + "".join(
                        f"Omitted source note {identity}: {plain_text(body)}\n\n"
                        for identity, body in omission["source_notes"].items()
                    )
                    for omission in decision.get("omissions", ())
                )
                + f"Decision: {decision['why']}\n\n"
                f"{swete_record(swete)}\n\n"
            )
            # Every Swete record the decision rests on, its omissions' too.
            for name, record in [
                (key, swete),
                *(
                    (f"{key}@omission{index}", omission["swete"])
                    for index, omission in enumerate(decision.get("omissions", ()), 1)
                    if "swete" in omission
                ),
            ]:
                reading = record["reading"].replace("|", "&#124;")
                audit.append(
                    f"| {name} | {record['volume']} | {record['page']} | {reading} | {record['agrees']} |\n"
                )
    lines.append(
        "# Swete audit\n\n| Decision | Volume | Page | Reading | Agrees |\n|---|---|---|---|---|\n"
    )
    return "".join(lines + audit)


def review(edition: pipeline.Edition) -> None:
    """Write the review, and what differs in it from the last one."""
    read, policy = edition.read, edition.policy
    files = {
        "notes.md": notes_report(edition),
        "ccel.md": ccel_report(edition.ccel),
        "alexandrinus.md": alexandrinus_report(read, edition),
        "numbering.md": places.report(
            edition.policy.versification["kjv"], edition.documents, read.kjv
        ),
        "byzantine.md": byzantine_review.summary(edition.byzantine),
        **{
            f"byzantine/{name}": text
            for name, text in byzantine_review.packets(
                edition.byzantine,
                {code: edition.documents[code] for code in byzantine.BOOKS},
            ).items()
        },
        **{f"text/{code}.usfm": text for code, text in export.export(edition, "pdf")},
        # The numbering page and textual variants, as the website publishes them.
        f"text/{bible.policy.NUMBERING['id']}.json": json_text(edition.numbering_page),
        f"text/{bible.policy.VARIANTS['id']}.json": json_text(web.variants(edition)),
    }
    base = paths.BUILD_DIR / "review"
    changes: list[str] = []
    previous = (
        {
            str(path.relative_to(base)): path.read_text(encoding="utf-8")
            for path in sorted(base.rglob("*"))
            if path.is_file() and path.name != "changes.diff"
        }
        if base.exists()
        else {}
    )
    for name in sorted(set(previous) | set(files)):
        changes += difflib.unified_diff(
            previous.get(name, "").splitlines(True),
            files.get(name, "").splitlines(True),
            fromfile=f"previous/{name}",
            tofile=f"current/{name}",
        )
    if base.exists():
        shutil.rmtree(base)
    for name, text in files.items():
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (base / "changes.diff").write_text("".join(changes), encoding="utf-8")
    notes = sum(len(rows) for rows in edition.notes.values())
    decisions = sum(
        len(policy.alexandrinus[s]) for s in ("readings", "passages", "kept")
    )
    changed = len({line for line in changes if line.startswith("+++ ")})
    print(
        f"Reviewed {notes} notes ({edition.ccel.inserted} from CCEL), "
        f"{decisions} Alexandrine decisions and "
        f"{len(edition.documents)} units; {changed} files changed since the last review:",
        base,
        flush=True,
    )
