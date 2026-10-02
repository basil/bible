"""The edition's decisions (edition/*.json), read once and never changed.

Every stage takes the policy it needs from one Policy. Importing a module
reads nothing. Each file's own rules are checked where the file is used; what
is checked here is what every file shares: its fields, and a reason for each
departure from the sources.
"""

from dataclasses import dataclass
from types import MappingProxyType

from bible import paths
from bible.checks import require, require_fields
from bible.files import read_json

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
)
# The edition's own pages, among the units the manifest lists.
EDITOR = {"id": "CNC", "file": "content/introduction.sfm"}
NUMBERING = {"id": "XXA", "file": "content/numbering.sfm"}
OLD_TESTAMENT = {"id": "XXF", "file": "content/old-testament.sfm"}
NEW_TESTAMENT = {"id": "XXG", "file": "content/new-testament.sfm"}
APPENDICES = {"id": "GLO", "file": "content/appendices.sfm"}


def freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(freeze(v) for v in value)
    return value


# Compared and hashed by identity, so that what is worked out from a policy
# can be kept for as long as the policy is.
@dataclass(frozen=True, eq=False)
class Policy:
    manifest: MappingProxyType
    sample: MappingProxyType
    alexandrinus: MappingProxyType
    brenton_notes: MappingProxyType
    kjv_notes: MappingProxyType
    introductions: MappingProxyType
    abbreviations: MappingProxyType
    terminology: MappingProxyType
    prose: MappingProxyType
    revisions: MappingProxyType
    citations: MappingProxyType
    quotations: MappingProxyType
    turpie: MappingProxyType
    versification: MappingProxyType
    witnesses: MappingProxyType

    @property
    def title(self):
        return self.manifest["title"]

    @property
    def scripture(self):
        return self.manifest["scripture"]

    @property
    def entries(self):
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
        )

    def unit(self, code):
        return next(u for u in self.scripture if u["id"] == code)

    def replace(self, **files):
        """A policy with some of its files replaced: as a test declares them,
        or with what the build works out from the sources."""
        values = {name: getattr(self, name) for name in self.__dataclass_fields__}
        values.update({name: freeze(value) for name, value in files.items()})
        policy = Policy(**values)
        check(policy)
        return policy


def source_id(entry):
    """The id of the source file an entry is printed from."""
    return entry.get("source_id", entry["id"])


def thaw(value):
    """A frozen value as plain lists and objects, to declare a changed policy."""
    if isinstance(value, (MappingProxyType, dict)):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [thaw(v) for v in value]
    return value


def check(policy):
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
    note_fields = {"lemma", "note", "sentence", "occurrence"}
    for name, notes, fields in (
        ("Brenton", policy.brenton_notes, note_fields | {"verse"}),
        ("1611", policy.kjv_notes, note_fields | {"anchor", "verse", "uncategorized"}),
    ):
        # Brenton's file also lists the lemmas whose shape has been read.
        require_fields(
            notes,
            {"notes", "corrections"},
            {"shapes"} if name == "Brenton" else (),
            f"{name} note file",
        )
        for key, entry in notes["notes"].items():
            require_fields(entry, {"why"}, fields, f"{name} note exception {key}")
            require(entry["why"], f"{name} note exception without a why: {key}")
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
    for name, group in policy.prose.items():
        require_fields(group, {"why", "changes"}, (), f"Prose changes {name}")
        require(group["why"], f"Prose changes without a why: {name}")
        for change in group["changes"]:
            require_fields(
                change,
                {"from", "to"},
                {"note", "unit", "why"},
                f"Prose change in {name}",
            )
            require(
                ("note" in change) != ("unit" in change),
                f"Prose change of neither a note nor a unit, or of both: {name}: {change['from']}",
            )
            require(
                "unit" not in change or change["unit"] in matter,
                f"Prose change to a unit that is no front or back matter: {name}: {change.get('unit')}",
            )


def load(directory=None):
    """Read and check the edition's decisions."""
    directory = paths.EDITION_DIR if directory is None else directory
    data = {name: freeze(read_json(directory / f"{name}.json")) for name in FILES}
    policy = Policy(
        manifest=data["manifest"],
        sample=data["sample"],
        alexandrinus=data["alexandrinus"],
        brenton_notes=data["brenton-notes"],
        kjv_notes=data["kjv-notes"],
        introductions=data["book-introductions"],
        abbreviations=data["abbreviations"],
        terminology=data["terminology"],
        prose=data["prose"],
        revisions=data["revisions"],
        citations=data["citations"],
        quotations=data["quotations"],
        turpie=data["turpie"],
        versification=data["versification"],
        witnesses=data["witnesses"],
    )
    check(policy)
    return policy
