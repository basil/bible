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
            "title": book.get("long"),
            "short_title": book.get("short"),
            "abbreviation": book.get("abbr"),
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
def sources(monkeypatch):
    """A private copy of sources.json that a test may alter."""
    data = copy.deepcopy(pipeline.SOURCES)
    monkeypatch.setattr(pipeline, "SOURCES", data)
    return data


@pytest.fixture
def marginal_notes_config(monkeypatch):
    """A private copy of config/marginal-notes.json that a test may alter."""
    data = copy.deepcopy(pipeline.MARGINAL_NOTES)
    monkeypatch.setattr(pipeline, "MARGINAL_NOTES", data)
    return data
