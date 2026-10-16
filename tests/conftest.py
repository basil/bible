"""What the tests share: the sources, the edition's decisions, and the
edition prepared from them once."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

import bible.annotate
import bible.pipeline
import bible.policy
import bible.sources
from bible import export, pipeline
from bible import policy as decisions
from bible import scripture
from bible import sources as source_files
from bible.byzantine.rows import Disposition, Instruction, Report, Unit
from bible.byzantine.stages import Context
from bible.sources import Content
from bible.usj import Document


@pytest.fixture(scope="session")
def sources() -> bible.sources.Sources:
    """The pinned sources, read through the input-integrity checks."""
    return source_files.load()


@pytest.fixture(scope="session")
def declared() -> bible.policy.Policy:
    """The edition's decisions as its files declare them."""
    return decisions.load()


@pytest.fixture(scope="session")
def read(
    sources: bible.sources.Sources, declared: bible.policy.Policy
) -> bible.pipeline.Read:
    """The sources as documents, their transcription corrected."""
    return pipeline.read(sources, declared)


@pytest.fixture(scope="session")
def policy(edition: bible.pipeline.Edition) -> bible.policy.Policy:
    """The decisions, with the places of the verses that the build works out."""
    return edition.policy


@pytest.fixture(scope="session")
def exported(edition: bible.pipeline.Edition) -> dict[str, str]:
    """The full edition as it is sent to be typeset, by unit."""
    return dict(export.export(edition, "pdf"))


@dataclass(frozen=True)
class Staged:
    """Stages retained from edition preparation, with snapshots taken before
    the next stage ran, for the checks of preservation and immutability."""

    read: bible.pipeline.Read
    # Brenton's and the King James books as promoted.
    promoted: tuple[dict[str, Document], ...]
    units: dict[str, Document]
    lined: dict[str, Document]
    # The copies: the sources before promotion, the promoted books before
    # assembly, the assembled books before lining, the lined before annotation.
    read_before: tuple[dict[str, Document], ...]
    promoted_before: tuple[dict[str, Document], ...]
    assembled: dict[str, Document]
    line_documents: dict[str, Document]


@pytest.fixture(scope="session")
def prepared_edition(
    sources: bible.sources.Sources,
    declared: bible.policy.Policy,
) -> tuple[bible.pipeline.Edition, Staged]:
    """Prepare once, keeping what four stages made, each with a copy taken
    as it finished, before the next stage ran."""
    made: dict[str, tuple[Any, Any]] = {}

    def kept(name: str, copied: Callable[[Any], object]) -> Callable[..., object]:
        stage = getattr(pipeline, name)

        def run(*args: object) -> object:
            assert name not in made, f"pipeline.{name} ran twice"
            result = stage(*args)
            made[name] = (result, copy.deepcopy(copied(result)))
            return result

        return run

    def unreadable(*args: object, **kwargs: object) -> None:
        raise AssertionError("Preparation must not read files")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "open", unreadable)
        patch.setattr(
            pipeline,
            "read",
            kept(
                "read",
                lambda r: (dict(r.brenton), dict(r.kjv), dict(r.updated_brenton)),
            ),
        )
        patch.setattr(
            pipeline,
            "promote",
            kept("promote", lambda p: (dict(p.brenton), dict(p.kjv))),
        )
        patch.setattr(pipeline, "assemble", kept("assemble", dict))
        patch.setattr(pipeline, "lined", kept("lined", dict))
        edition = pipeline.prepare(sources, declared)
    read_sources, read_before = made["read"]
    promoted, promoted_before = made["promote"]
    units, assembled = made["assemble"]
    lined, line_documents = made["lined"]
    return edition, Staged(
        read_sources,
        (dict(promoted.brenton), dict(promoted.kjv)),
        dict(units),
        dict(lined),
        read_before,
        promoted_before,
        assembled,
        line_documents,
    )


@pytest.fixture(scope="session")
def edition(
    prepared_edition: tuple[bible.pipeline.Edition, Staged],
) -> bible.pipeline.Edition:
    """The edition, prepared without reading a file: everything is read
    before preparation starts."""
    return prepared_edition[0]


@pytest.fixture(scope="session")
def staged(prepared_edition: tuple[bible.pipeline.Edition, Staged]) -> Staged:
    return prepared_edition[1]


def changed(
    policy: bible.policy.Policy, name: str, change: Callable[[dict[str, Any]], object]
) -> bible.policy.Policy:
    """A policy with one of its files changed: change is given the file's
    data as plain objects and lists, to alter in place."""
    data = decisions.thaw(getattr(policy, name))
    change(data)
    return policy.replace(**{name: data})


@pytest.fixture(scope="session")
def ctx(
    edition: bible.pipeline.Edition, policy: bible.policy.Policy
) -> bible.annotate.Context:
    """What reading a note needs: the policy and what the edition prints."""
    from bible import annotate

    return annotate.Context(policy, edition.inventory, edition.books)


def book(code: str, body: str, chapter: int = 99) -> Document:
    """A small book of scripture, its notes keyed as a source's are. Chapter
    99 is no book's, so that no exception in the edition's files applies."""
    from bible import usj

    return pipeline.keyed(code, usj.parse(f"\\id {code}\n\\c {chapter}\n\\p\n{body}\n"))


def verse_lines(doc: Document) -> dict[str, str]:
    """A document's verses as USFM lines, by their numbers."""
    from bible import usj

    return {
        line.split(" ", 2)[1]: line.split(" ", 2)[2]
        for line in usj.serialize(doc).splitlines()
        if line.startswith("\\v ")
    }


@pytest.fixture(scope="session")
def byzantine(edition: bible.pipeline.Edition) -> Context:
    """What the reconciliation of the New Testament with the Byzantine text
    worked out, by the names its stages gave it: the read inputs
    (source_inputs), the Greek texts (tr, rp), the unit ledger (units), the
    witnesses (instructions, reports, revision_rows), the readings
    (overrides), every unit's disposition (dispositions), the King James
    books before (documents) and after (prepared) the edits, the verses'
    texts (kjv), and the checks (invariants, finished)."""
    return edition.byzantine


@pytest.fixture(scope="session")
def byzantine_inputs(sources: bible.sources.Sources) -> Mapping[str, Content]:
    """The New Testament's Greek texts and witnesses, as the read stage
    gives them to the reconciliation, by the registry's names."""
    return sources.byzantine


@pytest.fixture(scope="session")
def kjv_text(byzantine: Mapping[str, Any]) -> Mapping[str, str]:
    """The pinned King James New Testament's verse texts, by "BOOK c:v",
    before the Byzantine readings."""
    return cast(Mapping[str, str], byzantine["kjv"])


@pytest.fixture(scope="session")
def units(byzantine: Mapping[str, Any]) -> list[Unit]:
    return cast(list[Unit], byzantine["units"])


@pytest.fixture(scope="session")
def by_id(units: list[Unit]) -> dict[str, Unit]:
    return {u["id"]: u for u in units}


@pytest.fixture(scope="session")
def dispositions(byzantine: Mapping[str, Any]) -> dict[str, Disposition]:
    return {r["unit"]: r for r in cast(list[Disposition], byzantine["dispositions"])}


@pytest.fixture(scope="session")
def instructions(
    byzantine: Mapping[str, Any],
) -> dict[tuple[str, int | str], Instruction]:
    return {
        (i["source"], i["entry"]): i
        for i in cast(list[Instruction], byzantine["instructions"])
    }


@pytest.fixture(scope="session")
def reports(byzantine: Mapping[str, Any]) -> dict[tuple[str, int | str], Report]:
    return {
        (r["witness"], r["entry"]): r for r in cast(list[Report], byzantine["reports"])
    }


@pytest.fixture(scope="session")
def prepared_verses(byzantine: Mapping[str, Any]) -> dict[str, scripture.Verse]:
    """Every verse of the conformed New Testament, by "BOOK c:v", before
    the annotate stage sets its notes in the edition's form."""
    return {
        f"{code} {address}": verse
        for code, doc in byzantine["prepared"].items()
        for address, verse in scripture.verses(doc).items()
    }


@pytest.fixture(scope="session")
def prepared_text(
    prepared_verses: dict[str, scripture.Verse],
) -> Callable[[str], str]:
    """The plain text of a verse of the conformed New Testament."""
    return lambda ref: scripture.plain(prepared_verses[ref].text)
