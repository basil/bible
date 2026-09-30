"""The notes review: every note's lemma and styling, for reading through, in
build/notes-review.md, with the entries changed since the last review in
build/notes-review-changes.md."""

from bible import paths
from bible.files import read_json, write_json
from bible.validate import validate


def line(entry, status=""):
    return (
        f"- {status}`{entry['key']}` [{entry['rule']}; {entry['style']}] "
        f"{entry['verse']}\n  → {entry['lemma'] or '(verse)'}: {entry['note']}\n"
    )


def notes_review():
    # Validation checks the exception files' fields, which the build alone
    # would read as no override.
    _, scripture = validate()
    # A note a quotation link replaces doesn't print, so isn't reviewed.
    entries = [entry for unit in scripture.values() for entry in unit.review]
    data = paths.BUILD_DIR / "notes-review.json"
    previous = {e["key"]: e for e in read_json(data)} if data.exists() else {}
    changed = [e for e in entries if previous.get(e["key"]) != e]
    # A note dropped or renumbered since the last review is a change too.
    keys = {e["key"] for e in entries}
    removed = [e for key, e in previous.items() if key not in keys]
    for name, text in (
        ("notes-review.md", "".join(line(e) for e in entries)),
        (
            "notes-review-changes.md",
            "".join(line(e) for e in changed)
            + "".join(line(e, "removed: ") for e in removed),
        ),
    ):
        (paths.BUILD_DIR / name).write_text(text, encoding="utf-8")
    # The baseline advances only once the changes against it have been written.
    write_json(data, entries)
    print(
        f"Reviewed {len(entries)} notes, {len(changed)} changed, "
        f"{len(removed)} removed:",
        paths.BUILD_DIR / "notes-review.md",
    )


def alexandrinus_review():
    """Read each decision in context, with the actual footnote and Swete audit."""
    from bible import abbreviations, alexandrinus, notes
    from bible.usfm import NOTE, plain_text, verse_spans
    import difflib
    import json
    import re

    archives, scripture = validate()
    originals = {
        code: notes.corrected_brenton(code, text, lambda *a, **k: None)
        for code, text in archives["brenton"].items()
    }
    entries = []

    def vatican_dropped(edit):
        # Whole verses already supplied from A are reprinted from the Appendix;
        # punctuation edits and that source transcription displace no Vatican words.
        unmarked = re.sub(r"\\add .*?\\add\*", "", edit["from"], flags=re.S)
        return (
            edit.get("note", "default") is None
            and bool(alexandrinus.tokens(unmarked))
            and alexandrinus.tokens(edit["from"]) != alexandrinus.tokens(edit["to"])
        )

    def printed_note(code, text):
        # Review entries precede the final abbreviation pass. Apply its declared
        # expansions too (for example the retained "See App." pointer).
        for section in ("numbers", "expanded"):
            for change in abbreviations.ABBREVIATIONS[section]["changes"]:
                if change["unit"] == code:
                    old, new = (plain_text(change[k]) for k in ("from", "to"))
                    if old:
                        text = text.replace(old, new)
        return abbreviations.chicago_forms(text, {})

    def verses(text):
        return [
            (r, plain_text(NOTE.sub("", text[a:b]))) for r, a, b in verse_spans(text)
        ]

    def context(items, wanted):
        indexes = [i for i, (r, _) in enumerate(items) if r in wanted]
        if not indexes:
            return "(No verse in this source.)"
        first, last = min(indexes), max(indexes)
        return "\n".join(
            f"{r} {text}" for r, text in items[max(0, first - 1) : last + 2]
        )

    for section in ("readings", "passages", "kept"):
        for key, decision in alexandrinus.DATA[section].items():
            code = key.split()[0]
            source_notes = {
                n["key"]: n["body"]
                for n in alexandrinus.keyed_notes(code, originals.get(code, ""))[1]
            }
            source = decision.get("appendix", source_notes.get(key, ""))
            if "kjv" in decision:
                source = alexandrinus.kjv_verse(decision["kjv"], archives)
            wanted = {decision.get("target", key).split()[-1].split("#")[0]}
            affected = set(wanted) if section == "readings" else set()
            for edit in decision.get("edits", []):
                wanted.add(edit["target"].split()[-1])
                affected.add(edit["target"].split()[-1])
            for insertion in decision.get("insertions", []):
                wanted.update(v["reference"] for v in insertion["verses"])
                affected.update(v["reference"] for v in insertion["verses"])
                wanted.add(insertion.get("after", insertion.get("before")))
            final = scripture.get(code)
            printed_notes = [
                n
                for n in (final.review if final else [])
                if n["key"] == key
                or n["key"].startswith(key + "@")
                or n["key"] in {e["key"] for e in decision.get("note_edits", [])}
                or n["key"].split()[-1].split("#")[0].split("@")[0] in affected
            ]
            printed_notes = [
                {**n, "note": printed_note(code, n["note"])} for n in printed_notes
            ]
            new_words = (
                decision.get("to", "")
                + " ".join(e["to"] for e in decision.get("edits", []))
                + " ".join(
                    alexandrinus.inserted_text(decision, v, archives)
                    for ins in decision.get("insertions", [])
                    for v in ins["verses"]
                )
            )
            new_note_words = " ".join(n["note"] for n in printed_notes)
            dropped = (
                sorted(
                    set(alexandrinus.tokens(source))
                    - set(alexandrinus.tokens(new_words + " " + new_note_words))
                )
                if section != "kept"
                else []
            )
            entry = {
                "key": key,
                "section": section,
                "source": (
                    f"Authorized Version, {decision['kjv']}: "
                    if "kjv" in decision
                    else ""
                )
                + plain_text(source),
                "before": context(verses(originals.get(code, "")), wanted),
                "after": (
                    context(verses(final.text), wanted)
                    if final
                    else "(Appendix information.)"
                ),
                "notes": [
                    f"{n['lemma'] or '(verse)'}: {n['note']}" for n in printed_notes
                ],
                "companion_notes": [
                    {"key": e["key"], "before": plain_text(e["from"]), "why": e["why"]}
                    for e in decision.get("note_edits", [])
                ],
                "english": [
                    {"target": e.get("target", key), **e["english"]}
                    for e in ([decision] if "english" in decision else [])
                    + decision.get("edits", [])
                    if "english" in e
                ]
                + [
                    {"target": f"{code} {v['reference']}", **v["english"]}
                    for ins in decision.get("insertions", [])
                    for v in ins["verses"]
                    if "english" in v
                ],
                "supplied": decision.get("supplied", []),
                "dropped": dropped,
                "why": decision["why"],
                "swete": decision["swete"],
                "dropped_vatican": (
                    [decision.get("from", "")]
                    if "from" in decision and vatican_dropped(decision)
                    else []
                ),
            }
            entry["dropped_vatican"] += [
                e["from"] for e in decision.get("edits", []) if vatican_dropped(e)
            ]
            entries.append(entry)

    def render(entry):
        sw = entry["swete"]
        return (
            f"## {entry['key']} — {entry['section']}\n\n"
            f"Source: {entry['source']}\n\nBefore:\n\n{entry['before']}\n\nAfter:\n\n{entry['after']}\n\n"
            + "\n".join(f"Footnote: {note}" for note in entry["notes"])
            + "".join(
                f"\n\nSource companion note ({note['key']}): {note['before']}\n"
                f"Reason for rewriting it: {note['why']}"
                for note in entry["companion_notes"]
            )
            + "".join(
                f"\n\nExact English derivation ({proof['target']}):\n\n```json\n"
                + json.dumps(proof, ensure_ascii=False, indent=2)
                + "\n```"
                for proof in entry["english"]
            )
            + f"\n\nSupplied: {', '.join(entry['supplied']) or 'none'}\n\n"
            f"Source note words absent from text and new note: {', '.join(entry['dropped']) or 'none'}\n\n"
            f"Vatican text dropped: {'; '.join(entry['dropped_vatican']) or 'none'}\n\n"
            f"Decision: {entry['why']}\n\nSwete {sw['volume']} p. {sw['page']} ({sw['evidence']}; agrees={sw['agrees']}): {sw['reading']}\n\n"
        )

    report = "# Alexandrine readings review\n\n" + "".join(render(e) for e in entries)
    report += "# Swete audit\n\n| Decision | Volume | Page | Reading | Agrees |\n|---|---|---|---|---|\n"
    for entry in entries:
        sw = entry["swete"]
        report += f"| {entry['key']} | {sw['volume']} | {sw['page']} | {sw['reading'].replace('|', '&#124;')} | {sw['agrees']} |\n"
    path = paths.BUILD_DIR / "alexandrinus-review.md"
    before = path.read_text(encoding="utf-8") if path.exists() else ""
    changes = "".join(
        difflib.unified_diff(
            before.splitlines(True),
            report.splitlines(True),
            fromfile="previous review",
            tofile="current review",
        )
    )
    (paths.BUILD_DIR / "alexandrinus-review-changes.md").write_text(
        changes, encoding="utf-8"
    )
    path.write_text(report, encoding="utf-8")
    write_json(paths.BUILD_DIR / "alexandrinus-review.json", entries)
    print(f"Reviewed {len(entries)} Alexandrine decisions:", path)
