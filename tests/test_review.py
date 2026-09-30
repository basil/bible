"""The editorial audit includes notes for all affected passage verses."""

from bible import review
from bible.files import read_json


def test_alexandrine_audit_includes_inserted_and_surviving_notes(
    archives, prepared, monkeypatch, tmp_path
):
    monkeypatch.setattr(review, "validate", lambda: (archives, prepared))
    monkeypatch.setattr(review.paths, "BUILD_DIR", tmp_path)
    review.alexandrinus_review()
    entries = {e["key"]: e for e in read_json(tmp_path / "alexandrinus-review.json")}
    for owner, keys in {
        "1SA 17:55-58": ["1SA 17:55"],
        "1SA 18:1-11": ["1SA 18:1", "1SA 18:10"],
        "1SA 18:17-19": ["1SA 18:17"],
        "1CH 1:11-23": ["1CH 1:11", "1CH 1:18"],
        "EZK 33:25": ["EZK 33:26"],
        "1SA 17:12-31": [
            "1SA 17:13",
            "1SA 17:14",
            "1SA 17:15",
            "1SA 17:18",
            "1SA 17:23",
            "1SA 17:29",
            "1SA 17:30",
            "1SA 17:31",
        ],
    }.items():
        unit = prepared[owner.split()[0]]
        for key in keys:
            note = next(n for n in unit.review if n["key"] == key)
            rendered = f"{note['lemma'] or '(verse)'}: {note['note']}"
            assert rendered in entries[owner]["notes"], (owner, key)
    # Footnote-only changes must also appear in the subsequent change report.
    note = next(n for n in prepared["1SA"].review if n["key"] == "1SA 17:55")
    monkeypatch.setitem(note, "note", note["note"] + " Audit regression sentinel")
    review.alexandrinus_review()
    assert (
        "Audit regression sentinel"
        in (tmp_path / "alexandrinus-review-changes.md").read_text()
    )
