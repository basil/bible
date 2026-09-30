"""Expand normalized editorial declarations for validation and review.

The JSON stores source text and editorial changes once. The working records
include the derived wording so the stage and its audit can check it against
the actual source independently.
"""

from copy import deepcopy

from bible.checks import require


def source_span(key, text, span):
    """Check a zero-based, half-open character span."""
    require(isinstance(text, str), f"Invalid English source: {key}")
    require(
        isinstance(span, list)
        and len(span) == 2
        and all(type(n) is int for n in span)
        and 0 <= span[0] <= span[1] <= len(text),
        f"Invalid English source span: {key}",
    )
    return tuple(span)


def expand_english(key, operation, source, why, output):
    require(isinstance(operation, dict), f"Invalid Alexandrine operation: {key}")
    require(output not in operation, f"Redundant derived English: {key}: {output}")
    proof = operation.get("english")
    require(
        isinstance(proof, dict)
        and {"source"} <= set(proof) <= {"source", "span", "edits"}
        and isinstance(proof["source"], str)
        and proof["source"] in {"brenton", "from"}
        and isinstance(proof.get("edits", []), list),
        f"Missing or malformed exact English derivation: {key}",
    )
    original = source if proof["source"] == "brenton" else operation.get("from")
    require(isinstance(original, str), f"Invalid English source: {key}")
    start, stop = source_span(key, original, proof.get("span", [0, len(original)]))
    base = original[start:stop]
    require(bool(base), f"Empty English source phrase: {key}")
    edits, parts = [], []
    end = 0
    for edit in proof.get("edits", []):
        require(
            isinstance(edit, dict)
            and {"span", "to"} <= set(edit) <= {"span", "to", "why"}
            and isinstance(edit["to"], str),
            f"Malformed English editorial edit: {key}",
        )
        a, b = source_span(key, base, edit["span"])
        reason = edit.get("why", operation.get("why", why))
        require(
            end <= a
            and isinstance(reason, str)
            and bool(reason.strip())
            and base[a:b] != edit["to"],
            f"Malformed English editorial edit: {key}",
        )
        edits.append({"start": a, "from": base[a:b], "to": edit["to"], "why": reason})
        parts.extend((base[end:a], edit["to"]))
        end = b
    parts.append(base[end:])
    after = "".join(parts)
    if "note_at" in operation:
        at = operation.pop("note_at")
        require(
            output == "to" and type(at) is int and 0 <= at <= len(after),
            f"Invalid Alexandrine note position: {key}",
        )
        after = after[:at] + "{note}" + after[at:]
    operation[output] = after
    operation["english"] = {"source": proof["source"], "text": base, "edits": edits}


def expand_decisions(data):
    """Materialize derived fields without changing the stored declarations."""
    require(
        isinstance(data, dict)
        and set(data) == {"swete", "readings", "passages", "kept"}
        and all(isinstance(v, dict) for v in data.values()),
        "Alexandrine file has missing or unknown sections",
    )
    data = deepcopy(data)
    for section in ("readings", "passages", "kept"):
        for key, entry in data[section].items():
            require(isinstance(entry, dict), f"Invalid Alexandrine decision: {key}")
            require(
                isinstance(entry.get("edits", []), list)
                and isinstance(entry.get("insertions", []), list),
                f"Invalid Alexandrine operations: {key}",
            )
            require(
                "book" not in entry and "consumes" not in entry,
                f"Redundant Alexandrine decision fields: {key}",
            )
            if section == "passages":
                require(
                    "source_note" not in entry, f"Invalid passage source note: {key}"
                )
                snapshots = entry.get("source_notes", {})
                require(
                    isinstance(snapshots, dict), f"Invalid source note snapshots: {key}"
                )
                entry["consumes"] = list(snapshots)
            elif "appendix" not in entry:
                require(
                    "source_note" in entry and "source_notes" not in entry,
                    f"Missing or redundant source note snapshot: {key}",
                )
                entry["source_notes"] = {key: entry.pop("source_note")}
            source = entry.get("appendix", entry.get("source_notes", {}).get(key, ""))
            operations = ([entry] if section == "readings" else []) + entry.get(
                "edits", []
            )
            for operation in operations:
                expand_english(key, operation, source, entry.get("why"), "to")
            if "kjv" in entry:
                require(entry["kjv"] is True, f"Invalid KJV source declaration: {key}")
                entry["kjv"] = key
            for insertion in entry.get("insertions", []):
                require(
                    isinstance(insertion, dict)
                    and isinstance(insertion.get("verses"), list),
                    f"Invalid Alexandrine insertion: {key}",
                )
                for verse in insertion["verses"]:
                    require(isinstance(verse, dict), f"Invalid inserted verse: {key}")
                    if "kjv" in entry:
                        require(
                            "text" not in verse and "english" not in verse,
                            f"Redundant KJV insertion text: {key}",
                        )
                    else:
                        expand_english(key, verse, source, entry.get("why"), "text")
    return data
