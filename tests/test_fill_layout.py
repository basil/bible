"""Protected major headings are distinguished from ordinary unresolved gaps."""

from types import SimpleNamespace

import pytest

from bible.fill_layout import remaining


@pytest.mark.parametrize(
    "marker,gap,body,expected",
    [
        ("ms1", 66, True, ([], [1])),
        ("ms1", 100, True, ([1], [])),  # The group would fit: a genuine gap.
        ("q1", 66, True, ([1], [])),
        ("ms1", 66, False, ([1], [])),  # Unknown heading block: refuse to guess.
    ],
)
def test_protected_heading_requires_measured_space(
    marker: str, gap: float, body: bool, expected: tuple[list[int], list[int]]
) -> None:
    def item(
        mark: str, ref: str, top: float, bottom: float
    ) -> tuple[SimpleNamespace, SimpleNamespace]:
        return SimpleNamespace(mrk=mark, pid=lambda: ref), SimpleNamespace(
            ystart=top, yend=bottom, lines=1
        )

    following = [
        item(marker, "PSA104.45[]", 670, 651),
        item("cl", "PSA105.0[1]", 642, 627),
        item("d", "PSA105.1[1]", 622, 609),
    ]
    if body:
        following += [
            item("q1", "PSA105.1[2]", 605, 592),
            item("q2", "PSA105.1[3]", 592, 581),
            item("q1", "PSA105.2[1]", 581, 570),
        ]
    pages = SimpleNamespace(
        pnums={}, numPages=lambda: 3, getParas=lambda page: following
    )
    assert remaining(pages, [(1, "A", 594, 594 - gap, 11)]) == expected
    # Last pages are permitted to be short, independently of headings.
    assert remaining(pages, [(3, "A", 594, 100, 11)]) == ([], [])
    # Never apply the single-column exemption to a second column.
    assert remaining(pages, [(1, "B", 594, 594 - gap, 11)]) == ([1], [])


def test_long_opening_paragraph_does_not_excuse_a_gap() -> None:
    following = [
        (SimpleNamespace(mrk="ms1"), SimpleNamespace(ystart=670, yend=650, lines=1)),
        (SimpleNamespace(mrk="p"), SimpleNamespace(ystart=640, yend=529, lines=10)),
    ]
    pages = SimpleNamespace(
        pnums={}, numPages=lambda: 3, getParas=lambda page: following
    )
    # The full paragraph cannot fit in 66pt, but its first line can.
    assert remaining(pages, [(1, "A", 594, 528, 11)]) == ([1], [])
