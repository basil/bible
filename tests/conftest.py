"""What the tests share: the sources, the edition's decisions, and the
edition prepared from them once in each test process."""

from __future__ import annotations

import copy
import dataclasses
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

import bible.annotate
import bible.pipeline
import bible.policy
import bible.sources
from bible import export, pipeline
from bible import policy as decisions
from bible import scripture
from bible import sources as source_files
from bible.byzantine import rendering, stages
from bible.byzantine.rows import Disposition, Instruction, Report, Unit
from bible.byzantine.stages import Reconciliation
from bible.sources import Content
from bible.usj import Document


def unreadable(*args: object, **kwargs: object) -> None:
    raise AssertionError("Preparation must not read files")


@pytest.fixture(scope="session")
def sources() -> bible.sources.Sources:
    """The pinned sources, read through the input-integrity checks."""
    return source_files.load()


@pytest.fixture(scope="session")
def declared() -> bible.policy.Policy:
    """The edition's decisions as its files declare them."""
    return decisions.load()


type ReadAsMade = tuple[bible.pipeline.Read, tuple[dict[str, Document], ...]]


@pytest.fixture(scope="session")
def read_as_made(
    sources: bible.sources.Sources, declared: bible.policy.Policy
) -> ReadAsMade:
    """The sources as documents, with a copy of them taken as they were made:
    the tests of the sources and the preparation share them, so a change in
    place by either, whichever ran first, shows against the copy when the
    stages are checked later in the same test process."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "open", unreadable)
        made = pipeline.read(sources, declared)
    return made, copy.deepcopy(
        (dict(made.brenton), dict(made.kjv), dict(made.updated_brenton))
    )


@pytest.fixture(scope="session")
def read(read_as_made: ReadAsMade) -> bible.pipeline.Read:
    """The sources as documents, their transcription corrected."""
    return read_as_made[0]


@pytest.fixture(scope="session")
def policy(edition: bible.pipeline.Edition) -> bible.policy.Policy:
    """The decisions, with the places of the verses that the build works out."""
    return edition.policy


@pytest.fixture(scope="session")
def prepared(edition: bible.pipeline.Edition) -> list[tuple[str, bible.usj.Document]]:
    """The full edition as PTXprint takes it, by unit, in order."""
    return export.prepared(edition, "pdf")


@pytest.fixture(scope="session")
def exported(prepared: list[tuple[str, bible.usj.Document]]) -> dict[str, str]:
    """The full edition as it is sent to be typeset, by unit."""
    return {code: bible.usj.serialize(doc) for code, doc in prepared}


def plain(value: object) -> object:
    """A copy of a value as plain objects, lists, and sets, a dataclass as its
    name and fields, to compare with the value later: copy.deepcopy cannot
    copy a mappingproxy. Any other object is kept as it is, compared by
    what it compares by."""
    if isinstance(value, (MappingProxyType, dict)):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return set(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return (
            type(value).__name__,
            {f.name: plain(getattr(value, f.name)) for f in dataclasses.fields(value)},
        )
    return value


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
    read_as_made: ReadAsMade,
) -> Iterator[tuple[bible.pipeline.Edition, Staged]]:
    """Prepare once, from the sources as the read fixture made them, keeping
    what four stages and the reconciliation's stages made, each with a copy
    taken as it finished, before the next stage ran.

    The reconciliation's records are frozen only at the top, and share their
    rows with the stages after them, so none may be changed in place: not by
    a later stage, nor by the promotion or the variants, which the
    preparation runs, nor by any test. They are checked against their copies
    once every test in the process has run, whatever ran and in what order."""
    made: dict[str, tuple[Any, Any]] = {}

    def reused(
        given: bible.sources.Sources, policy: bible.policy.Policy
    ) -> bible.pipeline.Read:
        assert given is sources and policy is declared, "read other sources"
        assert "read" not in made, "read ran twice"
        made["read"] = read_as_made
        return read_as_made[0]

    def kept(
        name: str, copied: Callable[[Any], object], module: object = pipeline
    ) -> Callable[..., object]:
        stage = getattr(module, name)

        def run(*args: object) -> object:
            assert name not in made, f"{name} ran twice"
            result = stage(*args)
            made[name] = (result, copied(result))
            return result

        return run

    def deep(copied: Callable[[Any], object]) -> Callable[[Any], object]:
        return lambda result: copy.deepcopy(copied(result))

    reconciling = ["inputs", *(n for n in vars(stages) if n.startswith("stage_"))]

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Path, "open", unreadable)
        patch.setattr(pipeline, "read", reused)
        patch.setattr(
            pipeline,
            "promote",
            kept("promote", deep(lambda p: (dict(p.brenton), dict(p.kjv)))),
        )
        patch.setattr(pipeline, "assemble", kept("assemble", deep(dict)))
        patch.setattr(pipeline, "lined", kept("lined", deep(dict)))
        for name in reconciling:
            patch.setattr(stages, name, kept(name, plain, stages))
        edition = pipeline.prepare(sources, declared)
    read_sources, read_before = made["read"]
    promoted, promoted_before = made["promote"]
    units, assembled = made["assemble"]
    lined, line_documents = made["lined"]
    yield edition, Staged(
        read_sources,
        (dict(promoted.brenton), dict(promoted.kjv)),
        dict(units),
        dict(lined),
        read_before,
        promoted_before,
        assembled,
        line_documents,
    )
    for name in reconciling:
        result, before = made[name]
        assert plain(result) == before, f"stages.{name} made what was changed later"


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
def byzantine(edition: bible.pipeline.Edition) -> Reconciliation:
    """What the reconciliation of the New Testament with the Byzantine text
    worked out, by the stage that made it (stages.Reconciliation)."""
    return edition.byzantine


def amended(found: Reconciliation, stage: str, **fields: Any) -> Reconciliation:
    """The reconciliation with some of one stage's results replaced."""
    return replace(found, **{stage: replace(getattr(found, stage), **fields)})


@pytest.fixture(scope="session")
def checker(byzantine: Reconciliation) -> rendering.Checker:
    """A rendering check made as the one the instructions and decisions
    stages were given, from the same records."""
    return stages.checker(byzantine.greek, byzantine.english)


@pytest.fixture(scope="session")
def byzantine_inputs(sources: bible.sources.Sources) -> Mapping[str, Content]:
    """The New Testament's Greek texts and witnesses, as the read stage
    gives them to the reconciliation, by the registry's names."""
    return sources.byzantine


@pytest.fixture(scope="session")
def kjv_text(byzantine: Reconciliation) -> Mapping[str, str]:
    """The pinned King James New Testament's verse texts, by "BOOK c:v",
    before the Byzantine readings."""
    return byzantine.english.kjv


@pytest.fixture(scope="session")
def units(byzantine: Reconciliation) -> list[Unit]:
    return list(byzantine.greek.units)


@pytest.fixture(scope="session")
def by_id(units: list[Unit]) -> dict[str, Unit]:
    return {u["id"]: u for u in units}


@pytest.fixture(scope="session")
def dispositions(byzantine: Reconciliation) -> dict[str, Disposition]:
    return {r["unit"]: r for r in byzantine.verified.dispositions}


@pytest.fixture(scope="session")
def instructions(
    byzantine: Reconciliation,
) -> dict[tuple[str, int | str], Instruction]:
    return {(i["source"], i["entry"]): i for i in byzantine.decisions.instructions}


@pytest.fixture(scope="session")
def reports(byzantine: Reconciliation) -> dict[tuple[str, int | str], Report]:
    return {(r["witness"], r["entry"]): r for r in byzantine.apparatuses.reports}


@pytest.fixture(scope="session")
def prepared_verses(byzantine: Reconciliation) -> dict[str, scripture.Verse]:
    """Every verse of the conformed New Testament, by "BOOK c:v", before
    the annotate stage sets its notes in the edition's form."""
    return {
        f"{code} {address}": verse
        for code, doc in byzantine.edited.prepared.items()
        for address, verse in scripture.verses(doc).items()
    }


@pytest.fixture(scope="session")
def prepared_text(
    prepared_verses: dict[str, scripture.Verse],
) -> Callable[[str], str]:
    """The plain text of a verse of the conformed New Testament."""
    return lambda ref: scripture.plain(prepared_verses[ref].text)
