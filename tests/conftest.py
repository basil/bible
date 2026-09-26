import copy

import pytest

import pipeline


@pytest.fixture(scope="session")
def archives():
    """The pinned source archives, read through the input-integrity checks."""
    return pipeline.validate()


@pytest.fixture(scope="session")
def scripture(archives):
    """Each printed scripture unit's prepared USFM, by id."""
    return {
        unit["id"]: pipeline.scripture_text(unit, archives)
        for unit in pipeline.EDITION["scripture"]
    }


@pytest.fixture(scope="session")
def book_names(archives):
    """BookNames.xml values for every project unit, by project id."""
    return {
        book.get("code"): {
            field: book.get(attr)
            for field, attr in pipeline.BOOK_NAME_ATTRIBUTES.items()
        }
        for book in pipeline.book_names_element(pipeline.ordered_entries(), archives)
    }


@pytest.fixture(autouse=True)
def fresh_marginal_notes():
    # Tests may patch the notes' source or configuration.
    pipeline.marginal_notes.cache_clear()
    yield
    pipeline.marginal_notes.cache_clear()


@pytest.fixture
def patched(monkeypatch):
    """Give the pipeline a private copy of one of its loaded files, for a test to alter."""

    def patch(name):
        data = copy.deepcopy(getattr(pipeline, name))
        monkeypatch.setattr(pipeline, name, data)
        return data

    return patch
