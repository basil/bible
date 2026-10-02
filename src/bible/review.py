"""The review: what the edition prints, for reading through, in build/review/.

    notes.md         every note, with the words it is about marked in its verse
    alexandrinus.md  every Alexandrine decision: its source, the passage before
                     and after, its footnotes, its derivation, and Swete
    numbering.md     where each Old Testament verse stands in the King James
                     Bible, with both translations' words for what rests on
                     the words alone
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

import bible.pipeline
import bible.policy
import bible.sources
from bible import assembly, paths, pipeline, places, scripture, versification
from bible.alexandrinus import APPENDIX
from bible.policy import thaw
from bible.references import parse_passage
from bible.usfm import plain_text
from bible.usj import Document


def note_line(row: Mapping[str, object]) -> str:
    return (
        f"- `{row['key']}` [{row['rule']}; {row['style']}] {row['verse']}\n"
        f"  → {row['lemma'] or '(verse)'}: {row['note']}\n"
    )


def notes_report(edition: bible.pipeline.Edition) -> str:
    return "# Notes\n\n" + "".join(
        f"## {code}\n\n" + "".join(map(note_line, rows)) + "\n"
        for code, rows in edition.notes.items()
        if rows
    )


def placed(
    policy: bible.policy.Policy, code: str, reference: str
) -> tuple[str, str] | None:
    """Where the edition prints a verse of one of Brenton's files: its unit
    and the verse's reference there."""
    for part, number, _ in assembly.DANIEL:
        if code == part:
            return "DAG", f"{number}:{reference.split(':')[1]}"
    chapter, _, verse = reference.partition(":")
    for unit in policy.scripture:
        if unit.get("source_id", unit["id"]) != code or unit["source"] != "brenton":
            continue
        first, last = unit.get("chapters", (1, 10**6))
        if first <= int(chapter) <= last:
            where = f"{unit['id']} {int(chapter) - first + 1}:{verse}"
            moved = versification.relabelled(policy=policy).get(
                parse_passage(where).first
            )
            return (unit["id"], moved.label if moved else where.split()[1])
    return None


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


def alexandrinus_report(
    read: bible.pipeline.Read, edition: bible.pipeline.Edition
) -> str:
    policy = edition.policy
    data = policy.alexandrinus
    sources: dict[str, dict[str, scripture.Verse]] = {}
    printed: dict[str, dict[str, scripture.Verse]] = {}

    def verses(
        cache: dict[str, dict[str, scripture.Verse]],
        docs: Mapping[str, Document],
        code: str,
    ) -> dict[str, scripture.Verse]:
        if code not in cache:
            cache[code] = scripture.verses(docs[code])
        return cache[code]

    lines = ["# Alexandrine readings\n\n"]
    audit = []
    for section in ("readings", "passages", "kept"):
        for key, decision in data[section].items():
            code = key.removeprefix(f"{APPENDIX} ").split()[0]
            wanted = {decision.get("target", key).split()[-1].split("#")[0]}
            for edit in decision.get("edits", ()):
                wanted.add(edit["target"].split()[-1])
            for insertion in decision.get("insertions", ()):
                wanted.update(v["reference"] for v in insertion["verses"])
                anchor = insertion.get("after", insertion.get("before"))
                assert anchor is not None
                wanted.add(anchor)
            wanted = {w for w in wanted if ":" in w and "-" not in w}
            source = decision.get("appendix", decision.get("source_note", ""))
            if "kjv" in decision:
                source = "Authorized Version, " + key
            targets: dict[str, set[str]] = {}
            for reference in wanted:
                where = placed(policy, code, reference)
                if where:
                    targets.setdefault(where[0], set()).add(where[1])
            keys = {
                key,
                *decision.get("note_edits", ()),
                *decision.get("source_notes", ()),
            }
            footnotes = [
                row
                for unit, rows in edition.notes.items()
                for row in rows
                if row["key"] in keys
                or row["key"].startswith(key + "@")
                or row["reference"] in targets.get(unit, ())
            ]
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
                f"Before:\n\n{context(verses(sources, read.brenton, code), wanted)}\n\n"
                "After:\n\n"
                + (
                    "\n".join(
                        context(verses(printed, edition.documents, unit), references)
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
                f"Decision: {decision['why']}\n\n"
                f"Swete {swete['volume']} p. {swete['page']} ({swete['evidence']}; "
                f"agrees={swete['agrees']}): {swete['reading']}\n\n"
            )
            reading = swete["reading"].replace("|", "&#124;")
            audit.append(
                f"| {key} | {swete['volume']} | {swete['page']} | {reading} | {swete['agrees']} |\n"
            )
    lines.append(
        "# Swete audit\n\n| Decision | Volume | Page | Reading | Agrees |\n|---|---|---|---|---|\n"
    )
    return "".join(lines + audit)


def review(
    sources: bible.sources.Sources,
    policy: bible.policy.Policy,
    edition: bible.pipeline.Edition,
) -> None:
    """Write the review, and what differs in it from the last one."""
    read = pipeline.read(sources, policy)
    files = {
        "notes.md": notes_report(edition),
        "alexandrinus.md": alexandrinus_report(read, edition),
        "numbering.md": places.report(
            edition.policy.versification["kjv"], edition.documents, read.kjv
        ),
        **{f"text/{code}.usfm": text for code, text in pipeline.export(edition, "pdf")},
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
        f"Reviewed {notes} notes, {decisions} Alexandrine decisions and "
        f"{len(edition.documents)} units; {changed} files changed since the last review:",
        base,
        flush=True,
    )
