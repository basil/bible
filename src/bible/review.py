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
