"""What the tests share: the sources, the edition's decisions, and the
edition prepared from them once."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

import bible.annotate
import bible.pipeline
import bible.policy
import bible.sources
from bible import pipeline
from bible import policy as decisions
from bible import sources as source_files
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
