"""What the tests share: the sources, the edition's decisions, and the
edition prepared from them once."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

import pytest

import bible.annotate
import bible.pipeline
import bible.policy
import bible.sources
from bible import pipeline
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
def edition(
    sources: bible.sources.Sources, declared: bible.policy.Policy
) -> bible.pipeline.Edition:
    """The edition, prepared without reading a file: everything is read
    before preparation starts."""

    def unreadable(*args: object, **kwargs: object) -> None:
        raise AssertionError("Preparation must not read files")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "open", unreadable)
        return pipeline.prepare(sources, declared)


@pytest.fixture(scope="session")
def policy(edition: bible.pipeline.Edition) -> bible.policy.Policy:
    """The decisions, with the places of the verses that the build works out."""
    return edition.policy


@pytest.fixture(scope="session")
def exported(edition: bible.pipeline.Edition) -> dict[str, str]:
    """The full edition as it is sent to be typeset, by unit."""
    return dict(pipeline.export(edition, "pdf"))


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
    edition: bible.pipeline.Edition,
    policy: bible.policy.Policy,
    sources: bible.sources.Sources,
) -> bible.annotate.Context:
    """What reading a note needs: the policy and what the edition prints."""
    from bible import annotate, assembly, terminology

    return annotate.Context(
        policy,
        edition.inventory,
        assembly.books(policy, sources),
        terminology.registry(policy),
        pipeline.note_prose(policy),
    )


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
    return edition.byzantine.context


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
