"""The edition's decisions (edition/*.json), read once and never changed.

Every stage takes the policy it needs from one Policy. Importing a module
reads nothing. Each file's own rules are checked where the file is used; what
is checked here is what every file shares: its fields, and a reason for each
departure from the sources.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast

from bible import paths
from bible import policy_schema as schema
from bible import usj
from bible.checks import require, require_fields
from bible.files import read_json
from bible.policy_schema import Entry

FILES = (
    "manifest",
    "sample",
    "alexandrinus",
    "brenton-notes",
    "kjv-notes",
    "ccel-notes",
    "appendix",
    "abbreviations",
    "terminology",
    "prose",
    "revisions",
    "citations",
    "quotations",
    "turpie",
    "versification",
    "lines",
    "margin",
    "psalter",
    "comparisons",
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
EDITOR = cast(
    Entry,
    freeze(
        {
            "id": "introduction",
            "source_id": "INT",
            "file": "content/introduction.sfm",
        }
    ),
)
# Brenton's list of abbreviations, completed from the registry and printed
# as a table of the introduction, where {abbreviations} asks for it.
GLOSSARY = cast(Entry, freeze({"id": "XXD", "source": "brenton", "source_id": "FRT"}))
OLD_TESTAMENT = cast(Entry, freeze({"id": "XXF", "file": "content/old-testament.sfm"}))
NEW_TESTAMENT = cast(Entry, freeze({"id": "XXG", "file": "content/new-testament.sfm"}))
# The numbering tables and textual variants are website-only.
NUMBERING = cast(Entry, freeze({"id": "XXA", "file": "content/numbering.sfm"}))
VARIANTS = cast(Entry, freeze({"id": "XXC", "file": "content/byzantine.sfm"}))


# Compared and hashed by identity, so that what is worked out from a policy
# can be kept for as long as the policy is.
@dataclass(frozen=True, eq=False)
class Policy:
    manifest: schema.Manifest
    sample: Mapping[str, tuple[int, ...]]
    alexandrinus: schema.Alexandrinus
    brenton_notes: schema.BrentonNotes
    kjv_notes: schema.KjvNotes
    ccel_notes: schema.CcelNotes
    appendix: schema.Appendix
    abbreviations: schema.Abbreviations
    terminology: Mapping[str, schema.Terminology]
    prose: Mapping[str, schema.Prose]
    revisions: schema.Revisions
    citations: schema.Citations
    quotations: schema.Quotations
    turpie: schema.Turpie
    versification: schema.Versification
    psalter: schema.Psalter
    comparisons: schema.Comparisons
    lines: schema.Lines
    margin: schema.Margin
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
    def front_matter(self) -> tuple[tuple[str, Entry], ...]:
        """Every unit of front matter the edition prints, in its order, with
        the section it stands in: the project's own pages before the
        testaments, then each testament's before its books."""
        manifest = self.manifest
        return (
            # The introduction follows the contents page and is
            # listed in it.
            ("front", EDITOR),
            *(("old_testament", unit) for unit in manifest["old_testament_front"]),
            *(("new_testament", unit) for unit in manifest["new_testament_front"]),
        )

    @property
    def sections(self) -> dict[str, str]:
        """The section each unit of front matter and each divider stands in."""
        return {
            **{entry["id"]: section for section, entry in self.front_matter},
            OLD_TESTAMENT["id"]: "old_testament",
            NEW_TESTAMENT["id"]: "new_testament",
        }

    @property
    def entries(self) -> tuple[Entry, ...]:
        """Every unit the edition prints, in its order."""
        front = self.front_matter
        scripture = self.manifest["scripture"]

        def of(section: str) -> tuple[Entry, ...]:
            return tuple(unit for where, unit in front if where == section)

        return (
            *of("front"),
            # Each testament opens with its divider and its translation's front matter.
            OLD_TESTAMENT,
            *of("old_testament"),
            *(u for u in scripture if u["section"] == "old_testament"),
            NEW_TESTAMENT,
            *of("new_testament"),
            *(u for u in scripture if u["section"] == "new_testament"),
        )

    @property
    def unprinted(self) -> tuple[Entry, ...]:
        """The source units read for what they send elsewhere, and printed
        nowhere as units: Brenton's Appendix, whose notes go to the books,
        and his list of abbreviations, whose table goes to the editor's
        introduction."""
        return (
            cast(Entry, freeze({"id": self.appendix["source"], "source": "brenton"})),
            GLOSSARY,
        )

    @property
    def matter(self) -> set[str]:
        """The units of front and back matter a decision may name: the
        translations' own, printed or read for the books."""
        return {
            e["id"]
            for e in (*self.entries, *self.unprinted)
            if "file" not in e and "section" not in e
        }

    def unit(self, code: str) -> Entry:
        return next(u for u in self.scripture if u["id"] == code)

    @functools.cached_property
    def kjv_units(self) -> frozenset[str]:
        """The books printed from the King James Bible: the New Testament,
        which the promote stage conforms to the Byzantine text."""
        return frozenset(u["id"] for u in self.scripture if u["source"] == "kjv")

    def replace(self, **files: object) -> Policy:
        """A policy with some of its files replaced: as a test declares them,
        or with what the build works out from the sources."""
        values = {name: getattr(self, name) for name in self.__dataclass_fields__}
        values.update(
            {name: freeze(normalized(name, value)) for name, value in files.items()}
        )
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


def normalized(name: str, data: Any) -> Any:
    """Give repeated decisions one shape at the policy boundary."""
    field = {"brenton_notes": "corrections", "citations": "decisions"}.get(name)
    if field is None or field not in data:
        return data
    return {
        **data,
        field: {
            key: (value,) if isinstance(value, Mapping) else value
            for key, value in data[field].items()
        },
    }


def check_prose_content(content: object, label: str) -> None:
    """Added prose is nonempty text with USJ character styles."""
    require(
        isinstance(content, (list, tuple)) and bool(content), f"{label}: empty content"
    )
    assert isinstance(content, (list, tuple))
    for item in content:
        if isinstance(item, str):
            require(bool(item), f"{label}: empty text")
            require("\\" not in item, f"{label}: markup in text")
        else:
            require(isinstance(item, Mapping), f"{label}: invalid content")
            assert isinstance(item, Mapping)
            require_fields(item, {"type", "marker", "content"}, (), label)
            require(
                item["type"] == "char" and item["marker"] in usj.CHARS,
                f"{label}: expected a character style",
            )
            check_prose_content(item["content"], label)


def check(policy: Policy) -> None:
    require_fields(
        policy.psalter, {"why", "kathismata", "middle", "notes"}, (), "Psalter"
    )
    require(bool(policy.psalter["why"].strip()), "Psalter without a why")
    for reference, closing in policy.psalter["notes"].items():
        require_fields(closing, {"why"}, (), f"Psalter note {reference}")
        require(
            bool(closing["why"].strip()), f"Psalter note without a why: {reference}"
        )
    require_fields(policy.margin, {"why", "below"}, (), "Margin")
    require(
        isinstance(policy.margin["why"], str)
        and bool(policy.margin["why"].strip())
        and isinstance(policy.margin["below"], Mapping),
        "Margin without a why, or without its placements by note",
    )
    for key, why in policy.margin["below"].items():
        require(
            isinstance(why, str) and bool(why.strip()),
            f"Note placement without a why: {key}",
        )
    # A decision's reason is required where it is carried out; a relocation
    # names the verse it prints at.
    decided: dict[str, frozenset[str]] = {
        "stubs": frozenset(),
        "unnumbered": frozenset(),
        "relocations": frozenset({"to"}),
    }
    for name, group in policy.versification.items():
        if name in decided:
            require_fields(group, {"why", "decisions"}, (), f"Versification {name}")
            assert isinstance(group, Mapping)
            require(
                isinstance(group["why"], str)
                and bool(group["why"].strip())
                and isinstance(group["decisions"], Mapping),
                f"Versification {name} without its reason or its decisions",
            )
            for reference, entry in group["decisions"].items():
                require_fields(
                    entry, decided[name], {"why"}, f"Versification {name} {reference}"
                )
    require_fields(policy.comparisons, {"why", "passages"}, (), "Comparisons")
    for comparison in policy.comparisons["passages"]:
        require_fields(comparison, {"passage", "kjv", "oleb"}, {"osb"}, "Comparison")
        if "osb" in comparison:
            osb = comparison["osb"]
            passage = comparison["passage"]
            require_fields(osb, {"text", "highlights"}, (), f"OSB quotation {passage}")
            require(
                isinstance(osb["text"], str) and bool(osb["text"].strip()),
                f"Empty OSB quotation: {passage}",
            )
    manifest_fields = {
        "title",
        "scripture",
        "old_testament_front",
        "new_testament_front",
        "excluded",
    }
    require_fields(policy.manifest, manifest_fields, (), "Manifest")
    require_fields(policy.manifest["excluded"], {"brenton"}, (), "Excluded sources")
    names = {"source_id", "title", "short_title", "abbreviation", "heading"}
    for manifest_group in (
        "scripture",
        "old_testament_front",
        "new_testament_front",
    ):
        units = policy.manifest[manifest_group]
        for unit_entry in units:
            required = {"id", "source"}
            optional = names
            if manifest_group == "scripture":
                required = required | {"section", "title"}
                optional = (names - {"title"}) | {
                    "chapters",
                    "cited_singly",
                    "abbreviated_singly",
                    "labelled_chapters",
                }
            require_fields(
                unit_entry,
                required,
                optional,
                f"Manifest {manifest_group} entry {unit_entry.get('id')}",
            )
            # Only true labels anything: false would be a decision that changes nothing.
            if "labelled_chapters" in unit_entry:
                require(
                    unit_entry["labelled_chapters"] is True
                    and "cited_singly" in unit_entry,
                    "Labelled chapters not true or without a singular name: "
                    f"{unit_entry['id']}",
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
    # The website-only pages' ids are taken too, and the list of
    # abbreviations', which is finished beside the printed units.
    taken = [*ids, NUMBERING["id"], VARIANTS["id"], GLOSSARY["id"]]
    require(len(taken) == len(set(taken)), "Duplicate project id")
    # The rendered PDF is searched by the contents' units.
    unread = sorted({witness["id"] for witness in policy.witnesses} - set(ids))
    require(not unread, f"Witnesses of units without a contents entry: {unread}")
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
    for key, rendering in policy.brenton_notes.get("renderings", {}).items():
        require_fields(
            rendering,
            {"from", "to", "source_note", "lemma", "why"},
            (),
            f"Brenton rendering {key}",
        )
        require(
            all(
                isinstance(value, str) and value.strip() for value in rendering.values()
            ),
            f"Empty Brenton rendering: {key}",
        )

    def check_correction(entry: schema.Correction, source: str, key: str) -> None:
        require_fields(
            entry,
            {"from", "to", "why"},
            {"uncategorized"},
            f"{source} correction {key}",
        )
        require(entry["why"], f"{source} correction without a why: {key}")

    # A misspelled field would be read as no override, and the entry as used.
    # The 1611 notes also say where George's lemma is found in the verse; a
    # note of either source may say which verse it belongs to.
    note_fields = {"lemma", "note", "sentence", "occurrence"}
    for name, notes, fields in (
        ("Brenton", policy.brenton_notes, note_fields | {"verse", "widen", "omitted"}),
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
            {"shapes", "renderings"} if name == "Brenton" else (),
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
            if "widen" in override:
                require(
                    override["widen"] is False
                    and isinstance(override.get("lemma"), str)
                    and "occurrence" in override,
                    f"Unwidened note exception needs a repeated lemma: {key}",
                )
    for key, group in policy.brenton_notes["corrections"].items():
        require(bool(group), f"Brenton correction group with no corrections: {key}")
        for entry in group:
            check_correction(entry, "Brenton", key)
    for key, entry in policy.kjv_notes["corrections"].items():
        check_correction(entry, "1611", key)
    # A CCEL decision names its existing duplicate, leaves it out, or places
    # it before its anchor words; its corrections are as the other sources' are.
    require_fields(policy.ccel_notes, {"notes", "corrections"}, (), "CCEL note file")
    for key, decision in policy.ccel_notes["notes"].items():
        require_fields(
            decision,
            {"why"},
            {"omitted", "duplicate", "verse", "anchor", "supplied"},
            f"CCEL note decision {key}",
        )
        require(decision["why"], f"CCEL note decision without a why: {key}")
        require(
            (decision.get("omitted") is True and decision.keys() == {"omitted", "why"})
            or (
                decision.keys() == {"duplicate", "why"}
                and isinstance(decision["duplicate"], str)
                and bool(decision["duplicate"])
            )
            or (
                "omitted" not in decision
                and isinstance(decision.get("verse"), str)
                and isinstance(decision.get("anchor"), str)
                and (
                    "duplicate" not in decision
                    or (
                        "supplied" not in decision
                        and isinstance(decision["duplicate"], str)
                        and bool(decision["duplicate"])
                    )
                )
                and ("supplied" not in decision or decision["supplied"] is True)
            ),
            f"CCEL note decision neither omits, duplicates nor places its note: {key}",
        )
    for key, entry in policy.ccel_notes["corrections"].items():
        check_correction(entry, "CCEL", key)
    # A Brenton exception's occurrence says which of a repeated lemma is meant.
    pointless = sorted(
        k
        for k, v in policy.brenton_notes["notes"].items()
        if "occurrence" in v and v.get("lemma") is None
    )
    require(
        not pointless, f"Note exceptions with an occurrence but no lemma: {pointless}"
    )
    # A note set in another verse has no caller there to say what it is about,
    # so its exception says, or says it is about no words (a reference).
    unplaced = sorted(
        k
        for k, v in policy.brenton_notes["notes"].items()
        if "verse" in v and "lemma" not in v
    )
    require(not unplaced, f"Note exceptions with a verse but no lemma: {unplaced}")
    # Only an anchor is categorized, so the flag on any other exception is unused.
    unused = sorted(
        k
        for k, v in policy.kjv_notes["notes"].items()
        if "uncategorized" in v and "anchor" not in v
    )
    require(not unused, f"Uncategorized flag without an anchor: {unused}")
    # A change of wording names its note, or the front or back matter it is
    # made in: one that named neither, or a unit that nothing reads, would be
    # met by nothing, unnoticed.
    require_fields(policy.appendix, {"source", "why", "notes"}, (), "Appendix file")
    require(policy.appendix["why"], "Appendix file without a why")
    for key, note in policy.appendix["notes"].items():
        require_fields(
            note,
            {"paragraphs", "why"},
            {"label", "before", "at"},
            f"Appendix note {key}",
        )
        require(
            re.fullmatch(r"[A-Z0-9]{3} \d+:\d+[a-z]?", key)
            and note["paragraphs"]
            and all(note["paragraphs"])
            and note["why"]
            and ("before" in note) != ("at" in note)
            and note.get("before", "x")
            and note.get("at", "start") in {"start", "end"},
            f"Invalid Appendix note: {key}",
        )
    matter = policy.matter
    unprinted = {entry["id"] for entry in policy.unprinted}
    scriptures = {entry["id"] for entry in policy.scripture}
    require_fields(
        policy.citations,
        {"units", "dialects", "decisions"},
        (),
        "Citations file",
    )
    sourced_colophons: set[str] = set()
    for name, prose_group in policy.prose.items():
        require_fields(
            prose_group,
            {"why", "changes"},
            {
                "additions",
                "markers",
                "sections",
                "italics",
                "references",
                "callers",
                "colophons",
                "sourced_colophons",
            },
            f"Prose changes {name}",
        )
        require(prose_group["why"], f"Prose changes without a why: {name}")
        for selection in prose_group.get("sourced_colophons", ()):
            code = selection.get("book")
            label = f"Sourced colophon in {name}: {code}"
            require_fields(selection, {"book", "source", "verse"}, (), label)
            require(code in policy.kjv_units, f"{label}: not a printed KJV book")
            require(selection["source"] == "tcent", f"{label}: unsupported source")
            require(
                isinstance(selection["verse"], str)
                and re.fullmatch(r"[1-9]\d*:[1-9]\d*", selection["verse"]),
                f"{label}: invalid source verse",
            )
            require(code not in sourced_colophons, f"{label}: duplicate book")
            sourced_colophons.add(selection["book"])
        for colophon_change in prose_group.get("colophons", ()):
            label = f"Colophon change in {name}: {colophon_change.get('book')}"
            require_fields(colophon_change, {"book", "from", "to"}, (), label)
            require(
                colophon_change["book"] in policy.kjv_units,
                f"{label}: not a printed KJV book",
            )
            require(
                isinstance(colophon_change["from"], str)
                and bool(colophon_change["from"])
                and isinstance(colophon_change["to"], str)
                and colophon_change["from"] != colophon_change["to"],
                f"{label}: invalid or ineffective wording change",
            )
        for field, required, optional in (
            ("sections", {"unit", "before", "heading"}, set()),
            ("italics", {"unit", "opening", "spans"}, set()),
            ("references", {"unit", "after", "passages"}, {"remove"}),
            ("callers", {"unit", "note", "after"}, set()),
        ):
            for presentation in cast(
                tuple[Mapping[str, Any], ...], prose_group.get(field, ())
            ):
                label = f"Prose {field} in {name}"
                require_fields(presentation, required, optional, label)
                require(
                    presentation["unit"] in matter
                    and presentation["unit"] not in unprinted,
                    f"{label}: not printed front or back matter",
                )
                for key, value in presentation.items():
                    if key == "spans":
                        require(
                            isinstance(value, tuple), f"{label}: spans must be a list"
                        )
                        for span in value:
                            if isinstance(span, str):
                                require(
                                    bool(span) and span.strip() == span,
                                    f"{label}: invalid italic span",
                                )
                            else:
                                require_fields(span, {"text", "within"}, (), label)
                                require(
                                    all(
                                        isinstance(v, str) and v.strip() == v and v
                                        for v in span.values()
                                    ),
                                    f"{label}: invalid italic span",
                                )
                    else:
                        require(
                            isinstance(value, str) and bool(value.strip()),
                            f"{label}: empty {key}",
                        )
                        if key != "remove":
                            require(
                                value == value.strip(),
                                f"{label}: surrounding space in {key}",
                            )
        for addition in prose_group.get("additions", ()):
            label = f"Prose addition in {name}"
            require_fields(addition, {"unit", "after", "paragraphs"}, (), label)
            require(addition["unit"] in matter, f"{label}: not front or back matter")
            after = addition["after"]
            require(bool(after.strip()), f"{label}: empty anchor")
            require(after == after.strip(), f"{label}: anchor with surrounding space")
            require(bool(addition["paragraphs"]), f"{label}: empty addition")
            for paragraph in addition["paragraphs"]:
                require_fields(paragraph, {"type", "marker", "content"}, (), label)
                require(
                    paragraph["type"] == "para" and paragraph["marker"] in {"ip", "ib"},
                    f"{label}: expected an introductory paragraph",
                )
                if paragraph["marker"] == "ib":
                    require(
                        paragraph["content"] == (),
                        f"{label}: a blank line takes no content",
                    )
                    continue
                check_prose_content(paragraph["content"], label)
                require(
                    bool(usj.unlabelled(thaw(paragraph["content"])).strip()),
                    f"{label}: blank paragraph",
                )
        for marker in prose_group.get("markers", ()):
            label = f"Marker decision in {name}"
            require_fields(
                marker,
                {"unit", "from", "to", "why"},
                {"opening", "before", "heading"},
                label,
            )
            # A unit taken apart, as the Appendix is, is never structured.
            require(
                (marker["unit"] in matter and marker["unit"] not in unprinted)
                or (marker["unit"] in scriptures and marker["to"] == "d"),
                f"{label}: not front or back matter or a scripture superscription",
            )
            require(
                {marker["from"], marker["to"]} <= usj.PARAGRAPHS,
                f"{label}: not a paragraph marker",
            )
            require(marker["from"] != marker["to"], f"{label}: changes nothing")
            require(bool(marker["why"].strip()), f"{label}: without a why")
            words = (
                marker.get("before")
                if marker["from"] == "ib"
                else marker.get("opening")
            ) or ""
            require(
                ("opening" in marker) != ("before" in marker) and bool(words),
                f"{label}: a paragraph is known by its opening words, a blank line by the words after it",
            )
            require(words == words.strip(), f"{label}: words with surrounding space")
            heading = marker.get("heading")
            # A blank line becomes a division as it is, a heading with words.
            needs_heading = marker["from"] == "ib" and marker["to"] in (
                usj.HEADINGS - {"sd1", "sd2"}
            )
            require(
                (heading is not None) == needs_heading,
                f"{label}: heading text is required only for a blank line becoming a section heading",
            )
            if heading is not None:
                require(bool(heading.strip()), f"{label}: empty heading")
                require(
                    heading == heading.strip(),
                    f"{label}: heading with surrounding space",
                )
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
        {"scrivener", "editions"},
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
            {"units", "wording", "grammar", "edits"},
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
    for key, correction in policy.byzantine.get("scrivener", {}).items():
        what = f"Scrivener correction {key}"
        require_fields(correction, {"from", "to", "why"}, (), what)
        require(bool(correction["why"].strip()), f"{what} without a why")
        require(correction["from"] != correction["to"], f"{what} changes nothing")
    for key, named in policy.byzantine.get("editions", {}).items():
        what = f"Byzantine edition {key}"
        require_fields(named, {"label", "why"}, {"reads", "lacks"}, what)
        require(isinstance(named["label"], str), f"{what} names no one label")
        require(bool(named["why"].strip()), f"{what} without a why")
        quoted = [named[field] for field in ("reads", "lacks") if field in named]
        require(
            all(isinstance(words, str) and words.strip() for words in quoted),
            f"{what} quotes no words",
        )
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
    """Read and check the edition's decisions, each file into the field of
    its name."""
    policy = Policy(
        **{
            name.replace("-", "_"): cast(
                Any,
                freeze(
                    normalized(
                        name.replace("-", "_"),
                        read_json(paths.EDITION_DIR / f"{name}.json"),
                    )
                ),
            )
            for name in FILES
        }
    )
    check(policy)
    return policy
