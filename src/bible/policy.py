"""The edition's decisions (edition/*.json), read once and never changed.

Every stage takes the policy it needs from one Policy. Importing a module
reads nothing. Each file's own rules are checked where the file is used; what
is checked here is what every file shares: its fields, and a reason for each
departure from the sources.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast

from bible import paths
from bible import policy_schema as schema
from bible.checks import require, require_fields
from bible.files import read_json
from bible.policy_schema import Entry

FILES = (
    "manifest",
    "sample",
    "alexandrinus",
    "brenton-notes",
    "kjv-notes",
    "book-introductions",
    "abbreviations",
    "terminology",
    "prose",
    "revisions",
    "citations",
    "quotations",
    "turpie",
    "versification",
    "witnesses",
    "byzantine",
    "byzantine-placements",
)


def freeze(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    return value


# The edition's own pages, among the units the manifest lists.
EDITOR = cast(Entry, freeze({"id": "CNC", "file": "content/introduction.sfm"}))
NUMBERING = cast(Entry, freeze({"id": "XXA", "file": "content/numbering.sfm"}))
OLD_TESTAMENT = cast(Entry, freeze({"id": "XXF", "file": "content/old-testament.sfm"}))
NEW_TESTAMENT = cast(Entry, freeze({"id": "XXG", "file": "content/new-testament.sfm"}))
APPENDICES = cast(Entry, freeze({"id": "GLO", "file": "content/appendices.sfm"}))
READINGS = cast(Entry, freeze({"id": "XXC", "file": "content/byzantine.sfm"}))


# Compared and hashed by identity, so that what is worked out from a policy
# can be kept for as long as the policy is.
@dataclass(frozen=True, eq=False)
class Policy:
    manifest: schema.Manifest
    sample: Mapping[str, tuple[int, ...]]
    alexandrinus: schema.Alexandrinus
    brenton_notes: schema.BrentonNotes
    kjv_notes: schema.KjvNotes
    introductions: schema.BookIntroductions
    abbreviations: schema.Abbreviations
    terminology: Mapping[str, schema.Terminology]
    prose: Mapping[str, schema.Prose]
    revisions: schema.Revisions
    citations: schema.Citations
    quotations: schema.Quotations
    turpie: schema.Turpie
    versification: schema.Versification
    witnesses: tuple[schema.Witnesses, ...]
    byzantine: schema.Byzantine
    byzantine_placements: schema.ByzantinePlacements

    @property
    def title(self) -> str:
        return self.manifest["title"]

    @property
    def scripture(self) -> tuple[Entry, ...]:
        return self.manifest["scripture"]

    @property
    def entries(self) -> tuple[Entry, ...]:
        """Every unit the edition prints, in its order."""
        manifest = self.manifest
        scripture = manifest["scripture"]
        return (
            # Project units follow the contents page and are listed in it.
            *manifest["front_matter"],
            # The editor's introduction follows the list of abbreviations,
            # and the table of chapters and verses, which it refers to.
            EDITOR,
            NUMBERING,
            # Each testament opens with its divider and its translation's front matter.
            OLD_TESTAMENT,
            *manifest["old_testament_front"],
            *(u for u in scripture if u["section"] == "old_testament"),
            NEW_TESTAMENT,
            *manifest["new_testament_front"],
            *(u for u in scripture if u["section"] == "new_testament"),
            APPENDICES,
            *manifest["appendices"],
            # The readings of the Byzantine text close the book.
            READINGS,
        )

    def unit(self, code: str) -> Entry:
        return next(u for u in self.scripture if u["id"] == code)

    def replace(self, **files: object) -> Policy:
        """A policy with some of its files replaced: as a test declares them,
        or with what the build works out from the sources."""
        values = {name: getattr(self, name) for name in self.__dataclass_fields__}
        values.update({name: freeze(value) for name, value in files.items()})
        policy = Policy(**values)
        check(policy)
        return policy


def source_id(entry: Entry) -> str:
    """The id of the source file an entry is printed from."""
    return entry.get("source_id", entry["id"])


def thaw(value: object) -> Any:
    """A frozen value as plain lists and objects, to declare a changed policy."""
    if isinstance(value, (MappingProxyType, dict)):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [thaw(v) for v in value]
    return value


def check(policy: Policy) -> None:
    manifest_fields = {
        "title",
        "scripture",
        "front_matter",
        "old_testament_front",
        "new_testament_front",
        "appendices",
        "excluded",
    }
    require_fields(policy.manifest, manifest_fields, (), "Manifest")
    require_fields(policy.manifest["excluded"], {"brenton"}, (), "Excluded sources")
    names = {"source_id", "title", "short_title", "abbreviation", "heading"}
    for manifest_group in (
        "scripture",
        "front_matter",
        "old_testament_front",
        "new_testament_front",
        "appendices",
    ):
        for unit_entry in policy.manifest[manifest_group]:
            required = {"id", "source"}
            optional = names
            if manifest_group == "scripture":
                required = required | {"section", "title"}
                optional = (names - {"title"}) | {
                    "chapters",
                    "cited_singly",
                    "abbreviated_singly",
                }
            require_fields(
                unit_entry,
                required,
                optional,
                f"Manifest {manifest_group} entry {unit_entry.get('id')}",
            )
            require(
                unit_entry["source"] in {"brenton", "kjv"},
                f"Unknown source: {unit_entry['id']}",
            )
    scripture = policy.scripture
    unplaced = [
        u["id"]
        for u in scripture
        if u.get("section") not in ("old_testament", "new_testament")
    ]
    require(not unplaced, f"Scripture units outside both testaments: {unplaced}")
    ids = [entry["id"] for entry in policy.entries]
    require(len(ids) == len(set(ids)), "Duplicate project id")
    codes = {u["id"] for u in scripture}
    require(
        set(policy.sample) <= codes,
        f"Sample names units outside the edition: {sorted(set(policy.sample) - codes)}",
    )
    require(
        all(
            chapters
            and all(type(c) is int and c >= 0 for c in chapters)
            and len(chapters) == len(set(chapters))
            for chapters in policy.sample.values()
        ),
        "Invalid sample chapter selection",
    )
    # A misspelt field would be read as no override, and the entry as used.
    # The 1611 notes also say where George's lemma is found in the verse; a
    # note of either source may say which verse it belongs to.
    note_fields = {"lemma", "note", "sentence", "occurrence", "quotation"}
    for name, notes, fields in (
        ("Brenton", policy.brenton_notes, note_fields | {"verse", "widen"}),
        (
            "1611",
            policy.kjv_notes,
            note_fields | {"anchor", "former", "verse", "uncategorized", "omitted"},
        ),
    ):
        # Brenton's file also lists the lemmas whose shape has been read.
        require_fields(
            notes,
            {"notes", "corrections"},
            {"shapes"} if name == "Brenton" else (),
            f"{name} note file",
        )
        for key, override in notes["notes"].items():
            require_fields(override, {"why"}, fields, f"{name} note exception {key}")
            require(override["why"], f"{name} note exception without a why: {key}")
            # A note left out is left out whole: nothing else may be said of it.
            require(
                not override.get("omitted") or override.keys() == {"omitted", "why"},
                f"{name} note omitted with other exceptions: {key}",
            )
            if "quotation" in override:
                require(
                    override["quotation"] is True and bool(override.get("note")),
                    f"Quotation exception needs declared italic words: {key}",
                )
            if "widen" in override:
                require(
                    override["widen"] is False
                    and isinstance(override.get("lemma"), str)
                    and "occurrence" in override,
                    f"Unwidened note exception needs a repeated lemma: {key}",
                )
        for key, group in notes["corrections"].items():
            for entry in group if isinstance(group, tuple) else (group,):
                require_fields(
                    entry,
                    {"from", "to", "why"},
                    {"uncategorized"},
                    f"{name} correction {key}",
                )
                require(entry["why"], f"{name} correction without a why: {key}")
    # A Brenton exception's occurrence says which of a repeated lemma is meant.
    pointless = sorted(
        k
        for k, v in policy.brenton_notes["notes"].items()
        if "occurrence" in v and v.get("lemma") is None
    )
    require(
        not pointless, f"Note exceptions with an occurrence but no lemma: {pointless}"
    )
    # A note set in another verse has no caller there to say what it is about.
    unplaced = sorted(
        k
        for k, v in policy.brenton_notes["notes"].items()
        if "verse" in v and v.get("lemma") is None
    )
    require(not unplaced, f"Note exceptions with a verse but no lemma: {unplaced}")
    # Only an anchor is categorized, so the flag on any other exception is unused.
    unused = sorted(
        k
        for k, v in policy.kjv_notes["notes"].items()
        if "uncategorized" in v and "anchor" not in v
    )
    require(not unused, f"Uncategorized flag without an anchor: {unused}")
    require_fields(
        policy.introductions,
        {"source", "front", "books", "sections", "glosses", "names", "omit"},
        (),
        "Book introductions file",
    )
    # A change of wording names its note, or the front or back matter it is
    # made in: one that named neither, or a unit that nothing reads, would be
    # met by nothing, unnoticed.
    matter = {e["id"] for e in policy.entries if "file" not in e and "section" not in e}
    require_fields(
        policy.citations,
        {"units", "dialects", "decisions", "names"},
        (),
        "Citations file",
    )
    unused_names = sorted(set(policy.citations["names"]) - matter)
    require(not unused_names, f"Unused citation name changes: {unused_names}")
    for code, changes in policy.citations["names"].items():
        require(changes, f"Empty citation name changes: {code}")
        for change in changes:
            require_fields(
                change, {"from", "to", "why"}, (), f"Citation name change {code}"
            )
            require(
                change["from"] and change["why"],
                f"Citation name change without words or reason: {code}",
            )
            require(
                change["from"] != change["to"],
                f"Citation name change that changes nothing: {code}",
            )
    for name, prose_group in policy.prose.items():
        require_fields(prose_group, {"why", "changes"}, (), f"Prose changes {name}")
        require(prose_group["why"], f"Prose changes without a why: {name}")
        for change in prose_group["changes"]:
            require_fields(
                change,
                {"from", "to"},
                {"note", "unit", "why"},
                f"Prose change in {name}",
            )
            require(
                change["from"] and change["from"] != change["to"],
                f"Prose change that changes nothing: {name}: {change.get('note', change.get('unit'))}",
            )
            require(
                ("note" in change) != ("unit" in change),
                f"Prose change of neither a note nor a unit, or of both: {name}: {change['from']}",
            )
            require(
                "unit" not in change or change["unit"] in matter,
                f"Prose change to a unit that is no front or back matter: {name}: {change.get('unit')}",
            )

    require_fields(
        policy.byzantine,
        {"why", "readings", "structure", "accents", "hodges-farstad", "lemmas"},
        (),
        "Byzantine decisions",
    )
    require_fields(
        policy.byzantine["structure"],
        {"why", "omitted", "moved"},
        (),
        "Byzantine structure",
    )
    for key, reading in policy.byzantine["readings"].items():
        require_fields(
            reading,
            {"kind", "why", "evidence"},
            {"units", "tags", "edits"},
            f"Byzantine reading {key}",
        )
    for key, accent in policy.byzantine["accents"].items():
        require_fields(accent, {"tr", "rp", "why"}, (), f"Byzantine accent {key}")
        require(bool(accent["why"].strip()), f"Byzantine accent without a why: {key}")
    for key, side in policy.byzantine["hodges-farstad"].items():
        what = f"Byzantine Hodges-Farstad side {key}"
        require_fields(side, {"unit", "side", "why"}, (), what)
        require_fields(side["unit"], {"ref", "tr", "rp"}, (), what)
        require(bool(side["why"].strip()), f"{what} without a why")
    for key, lemma in policy.byzantine["lemmas"].items():
        require_fields(lemma, {"lemma", "why"}, (), f"Byzantine note lemma {key}")
    require_fields(
        policy.byzantine_placements, {"why", "placements"}, (), "Byzantine placements"
    )
    for key, placement in policy.byzantine_placements["placements"].items():
        require_fields(
            placement, {"ref", "unit", "why"}, (), f"Byzantine placement {key}"
        )


def load() -> Policy:
    """Read and check the edition's decisions."""
    data = {
        name: freeze(read_json(paths.EDITION_DIR / f"{name}.json")) for name in FILES
    }
    policy = Policy(
        manifest=cast(schema.Manifest, data["manifest"]),
        sample=cast(Mapping[str, tuple[int, ...]], data["sample"]),
        alexandrinus=cast(schema.Alexandrinus, data["alexandrinus"]),
        brenton_notes=cast(schema.BrentonNotes, data["brenton-notes"]),
        kjv_notes=cast(schema.KjvNotes, data["kjv-notes"]),
        introductions=cast(schema.BookIntroductions, data["book-introductions"]),
        abbreviations=cast(schema.Abbreviations, data["abbreviations"]),
        terminology=cast(Mapping[str, schema.Terminology], data["terminology"]),
        prose=cast(Mapping[str, schema.Prose], data["prose"]),
        revisions=cast(schema.Revisions, data["revisions"]),
        citations=cast(schema.Citations, data["citations"]),
        quotations=cast(schema.Quotations, data["quotations"]),
        turpie=cast(schema.Turpie, data["turpie"]),
        versification=cast(schema.Versification, data["versification"]),
        witnesses=cast(tuple[schema.Witnesses, ...], data["witnesses"]),
        byzantine=cast(schema.Byzantine, data["byzantine"]),
        byzantine_placements=cast(
            schema.ByzantinePlacements, data["byzantine-placements"]
        ),
    )
    check(policy)
    return policy
