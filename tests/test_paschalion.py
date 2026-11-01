"""The Paschalion: each method checked against an independent one, and the
rule for the years a build covers."""

import datetime as dt

import pytest

from bible import paschalion, usj
from bible.paschalion import (
    first_year,
    gregorian,
    julian_pascha,
    last_year,
    pascha,
    span,
    table,
    western_easter,
)

# The Julian paschal full moons, the fourteenth day of the ecclesiastical
# moon, by Golden Number, as the traditional table gives them.
PASCHAL_FULL_MOONS = {
    1: (4, 5),
    2: (3, 25),
    3: (4, 13),
    4: (4, 2),
    5: (3, 22),
    6: (4, 10),
    7: (3, 30),
    8: (4, 18),
    9: (4, 7),
    10: (3, 27),
    11: (4, 15),
    12: (4, 4),
    13: (3, 24),
    14: (4, 12),
    15: (4, 1),
    16: (3, 21),
    17: (4, 9),
    18: (3, 29),
    19: (4, 17),
}
YEARS = range(1583, 4100)


def julian_day(year: int, month: int, day: int) -> int:
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return day + (153 * m + 2) // 5 + 365 * y + y // 4 - 32083


def pascha_by_the_full_moons(year: int) -> tuple[int, int]:
    """The first Sunday strictly after the paschal full moon."""
    month, day = PASCHAL_FULL_MOONS[year % 19 + 1]
    jdn = julian_day(year, month, day) + 1
    while jdn % 7 != 6:  # Sunday
        jdn += 1
    days = jdn - julian_day(year, 3, 1)
    return (3, days + 1) if days < 31 else (4, days - 30)


def easter_by_gauss(year: int) -> dt.date:
    a, b, c = year % 19, year % 4, year % 7
    k = year // 100
    p = (13 + 8 * k) // 25
    q = k // 4
    m = (15 - p + k - q) % 30
    n = (4 + k - q) % 7
    d = (19 * a + m) % 30
    e = (2 * b + 4 * c + 6 * d + n) % 7
    if d == 29 and e == 6:
        return dt.date(year, 4, 19)
    if d == 28 and e == 6 and (11 * m + 11) % 30 < 19:
        return dt.date(year, 4, 18)
    return dt.date(year, 3, 22) + dt.timedelta(days=d + e)


def test_the_julian_pascha_agrees_with_the_table_of_paschal_full_moons() -> None:
    for year in YEARS:
        assert julian_pascha(year) == pascha_by_the_full_moons(year), year


def test_the_western_easter_agrees_with_gauss_and_falls_on_a_sunday() -> None:
    for year in YEARS:
        easter = western_easter(year)
        assert easter == easter_by_gauss(year), year
        assert easter.weekday() == 6, year


def test_the_gregorian_date_agrees_with_the_century_rule() -> None:
    # From Julian March 1 of a year to the next February, the Julian calendar
    # trails the Gregorian by k - k // 4 - 2 days, k the century.
    for year in YEARS:
        month, day = julian_pascha(year)
        k = year // 100
        same = dt.date(year, month, day)
        assert gregorian(year, month, day) == same + dt.timedelta(k - k // 4 - 2)
    assert gregorian(1582, 10, 5) == dt.date(1582, 10, 15)
    assert gregorian(1918, 1, 31) == dt.date(1918, 2, 13)


def test_pascha_falls_on_a_sunday_in_both_styles() -> None:
    for year in YEARS:
        p = pascha(year)
        assert p.new_style.weekday() == 6, year
        assert julian_day(year, *p.old_style) % 7 == 6, year


@pytest.mark.parametrize(
    ("year", "month", "day"),
    [
        (1818, 3, 22),
        (1943, 4, 25),
        (2019, 4, 21),
        (2024, 3, 31),
        (2025, 4, 20),
        (2026, 4, 5),
        (2038, 4, 25),
        (2285, 3, 22),
    ],
)
def test_published_western_easters(year: int, month: int, day: int) -> None:
    assert western_easter(year) == dt.date(year, month, day)


@pytest.mark.parametrize(
    ("year", "month", "day", "shared"),
    [
        (2021, 5, 2, False),
        (2023, 4, 16, False),
        (2024, 5, 5, False),
        (2025, 4, 20, True),
        (2026, 4, 12, False),
        (2027, 5, 2, False),
    ],
)
def test_published_paschas(year: int, month: int, day: int, shared: bool) -> None:
    p = pascha(year)
    assert p.new_style == dt.date(year, month, day)
    assert p.shared is shared


def test_the_pages_claims_about_the_calendar() -> None:
    # Pascha falls no earlier than March 22 and no later than April 25, Old
    # Style: the Julian paschalion repeats every 532 years.
    dates = {julian_pascha(year) for year in range(1900, 1900 + 532)}
    assert min(dates) == (3, 22) and max(dates) == (4, 25)
    # Since March 1, 1900, Old Style, the Julian calendar has stood thirteen
    # days behind the Gregorian, and from March 1, 2100, fourteen.
    assert gregorian(1900, 2, 29) == dt.date(1900, 3, 13)
    assert gregorian(1900, 3, 1) == dt.date(1900, 3, 14)
    assert gregorian(2100, 2, 28) == dt.date(2100, 3, 13)
    assert gregorian(2100, 3, 1) == dt.date(2100, 3, 15)


def test_the_table_begins_with_the_next_pascha() -> None:
    assert first_year(dt.date(2026, 1, 1)) == 2026
    assert first_year(dt.date(2026, 4, 12)) == 2026  # Pascha itself
    assert first_year(dt.date(2026, 4, 13)) == 2027
    assert first_year(dt.date(2026, 11, 1)) == 2027


def test_the_table_ends_a_century_on_rounded_to_fifty() -> None:
    assert last_year(2026) == 2150
    assert last_year(2027) == 2150
    assert last_year(2051) == 2150
    assert last_year(2075) == 2200
    assert last_year(2076) == 2200
    assert span(dt.date(2026, 11, 1)) == (2027, 2150)
    assert span(dt.date(2026, 4, 12)) == (2026, 2150)


def test_the_build_date_honours_source_date_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", str(1_700_000_000))  # 2023-11-14 UTC
    assert paschalion.today() == dt.date(2023, 11, 14)
    monkeypatch.delenv("SOURCE_DATE_EPOCH")
    assert paschalion.today() == dt.date.today()


def cells(row: str | usj.Node) -> list[tuple[str, str]]:
    """A row's cells, each its marker and its words."""
    assert not isinstance(row, str)
    return [
        (cell["marker"], usj.text_of(cell["content"]))
        for cell in row["content"]
        if not isinstance(cell, str)
    ]


def test_the_table_gives_every_year_once_in_both_styles() -> None:
    heads, *rows = map(cells, table(2026, 2150)["content"])
    assert len(rows) == 125
    assert heads == list(zip(("th1", "th2", "th3"), paschalion.HEADS))
    assert all([marker for marker, _ in row] == ["tc1", "tc2", "tc3"] for row in rows)
    texts = [[text for _, text in row] for row in rows]
    assert [int(c[0].rstrip("†")) for c in texts] == list(range(2026, 2150 + 1))
    by_year = {int(c[0].rstrip("†")): c for c in texts}
    assert by_year[2026] == ["2026", "March 30", "April 12"]
    assert by_year[2028] == ["2028†", "April 3", "April 16"]
    assert by_year[2099] == ["2099†", "March 30", "April 12"]
    # From 2100 the styles are fourteen days apart.
    assert by_year[2100] == ["2100", "April 18", "May 2"]
    assert by_year[2150] == ["2150", "April 5", "April 19"]
    # The dagger marks the years the Western Easter shares, and no others.
    months = {name: month for month, name in paschalion.MONTHS.items()}
    for year, (label, _, new_style) in by_year.items():
        month, day = new_style.split()
        easter = western_easter(year) == dt.date(year, months[month], int(day))
        assert label.endswith("†") is easter, year
    assert sum(label.endswith("†") for label, _, _ in by_year.values()) == 33
