"""What the tests share: the sources, the edition's decisions, and the
edition prepared from them once."""

import pytest

from bible import pipeline
from bible import policy as decisions
from bible import sources as source_files


@pytest.fixture(scope="session")
def sources():
    """The pinned sources, read through the input-integrity checks."""
    return source_files.load()


@pytest.fixture(scope="session")
def declared():
    """The edition's decisions as its files declare them."""
    return decisions.load()


@pytest.fixture(scope="session")
def read(sources, declared):
    """The sources as documents, their transcription corrected."""
    return pipeline.read(sources, declared)


@pytest.fixture(scope="session")
def edition(sources, declared):
    return pipeline.prepare(sources, declared)


@pytest.fixture(scope="session")
def policy(edition):
    """The decisions, with the places of the verses that the build works out."""
    return edition.policy


@pytest.fixture(scope="session")
def exported(edition):
    """The full edition as it is sent to be typeset, by unit."""
    return dict(pipeline.export(edition, "pdf"))


def changed(policy, name, change):
    """A policy with one of its files changed: change is given the file's
    data as plain objects and lists, to alter in place."""
    data = decisions.thaw(getattr(policy, name))
    change(data)
    return policy.replace(**{name: data})


@pytest.fixture(scope="session")
def ctx(edition, policy, sources):
    """What reading a note needs: the policy and what the edition prints."""
    from bible import annotate, assembly, terminology

    return annotate.Context(
        policy,
        edition.inventory,
        assembly.books(policy, sources),
        terminology.registry(policy),
        pipeline.note_prose(policy),
    )


def book(code, body, chapter=99):
    """A small book of scripture, its notes keyed as a source's are. Chapter
    99 is no book's, so that no exception in the edition's files applies."""
    from bible import usj

    return pipeline.keyed(code, usj.parse(f"\\id {code}\n\\c {chapter}\n\\p\n{body}\n"))


def verse_lines(doc):
    """A document's verses as USFM lines, by their numbers."""
    from bible import usj

    return {
        line.split(" ", 2)[1]: line.split(" ", 2)[2]
        for line in usj.serialize(doc).splitlines()
        if line.startswith("\\v ")
    }
