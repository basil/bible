import copy

import pytest

from bible import edition, notes, prepare, sources


@pytest.fixture(scope="session")
def archives():
    """The pinned source archives, read through the input-integrity checks."""
    return sources.load_archives()


@pytest.fixture(scope="session")
def scripture(archives):
    """Each printed scripture unit's prepared USFM, by id."""
    return {
        unit["id"]: prepare.scripture_text(unit, archives)
        for unit in edition.MANIFEST["scripture"]
    }


@pytest.fixture(scope="session")
def book_names(archives):
    """BookNames.xml values for every project unit, by project id."""
    return {
        book.get("code"): {
            field: book.get(attr)
            for field, attr in edition.BOOK_NAME_ATTRIBUTES.items()
        }
        for book in edition.book_names_element(edition.ordered_entries(), archives)
    }


@pytest.fixture(autouse=True)
def fresh_marginal_notes():
    # Tests may patch the notes' source or configuration.
    notes.marginal_notes.cache_clear()
    yield
    notes.marginal_notes.cache_clear()


@pytest.fixture
def patched(monkeypatch):
    """Give a module a private copy of one of its loaded files, for a test to alter."""

    def patch(module, name):
        data = copy.deepcopy(getattr(module, name))
        monkeypatch.setattr(module, name, data)
        return data

    return patch


@pytest.fixture(scope="session")
def with_source(archives):
    """A copy of the archives with one source file's text edited."""

    def edited(source, code, edit):
        return {
            **archives,
            source: {**archives[source], code: edit(archives[source][code])},
        }

    return edited
