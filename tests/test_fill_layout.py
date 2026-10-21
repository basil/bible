"""A short page before a heading is forced; any other gap is unresolved."""

from types import SimpleNamespace

import pytest

from bible.fill_layout import remaining


def pages(*following: tuple[str, str]) -> SimpleNamespace:
    """Three pages, of which the second opens with the given paragraphs."""
    paragraphs = [
        (SimpleNamespace(partype=kind, mrk=marker), SimpleNamespace(lines=1))
        for kind, marker in following
    ]
    return SimpleNamespace(
        pnums={}, numPages=lambda: 3, getParas=lambda page: iter(paragraphs)
    )


@pytest.mark.parametrize(
    "following,expected",
    [
        ([("section", "ms1"), ("other", "cl"), ("section", "d")], ([], [1])),
        ([("other", "cl"), ("section", "d"), ("versetext", "q1")], ([], [1])),
        ([("other", "lit"), ("versetext", "q1")], ([], [1])),
        ([("title", "imt1"), ("other", "ip")], ([], [1])),
        ([("versetext", "q1"), ("versetext", "q2")], ([1], [])),
        ([("versetext", "p")], ([1], [])),  # A paragraph continued, or not.
        ([("other", "ip")], ([1], [])),  # An introduction paragraph: no box.
        ([], ([1], [])),
    ],
)
def test_only_a_heading_forces_the_break_before_it(
    following: list[tuple[str, str]], expected: tuple[list[int], list[int]]
) -> None:
    assert remaining(pages(*following), [(1, "A", 594, 560, 11)]) == expected
    # Never apply the single-column exemption to a second column.
    assert remaining(pages(*following), [(1, "B", 594, 560, 11)]) == ([1], [])


def test_short_last_pages_and_full_pages_are_not_gaps() -> None:
    layout = pages(("versetext", "q1"))
    assert remaining(layout, [(3, "A", 594, 100, 11)]) == ([], [])
    assert remaining(layout, [(1, "A", 594, 588, 11)]) == ([], [])
    assert remaining(layout, [(-1, "A", 594, 100, 11)]) == ([], [])


def test_printed_pages_map_to_physical_pages() -> None:
    layout = pages(("versetext", "q1"))
    layout.pnums = {5: 1}
    assert remaining(layout, [(5, "A", 594, 560, 11), (5, "A", 594, 500, 11)]) == (
        [1],
        [],
    )
