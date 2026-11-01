"""The Paschalion: the date of Pascha for the years the edition's page covers.

Pascha is reckoned by the Julian paschalion, the fourteenth day of the
ecclesiastical moon and the Sunday after it, and given in both styles: the
Julian date the Church keeps, and its day in the Gregorian calendar. A dagger
marks the years in which the Western Easter, reckoned by the Gregorian
paschalion, falls on the same day.

The years are not written down. The table begins with the year of the next
Pascha, the current year until its Pascha is past, and runs to the start plus
a hundred years, rounded to the nearest fifty, so that the page stays current
without being edited. The clock is read in one place, `today`, which honours
SOURCE_DATE_EPOCH for a build that must be reproducible.
"""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass

from bible import usj
from bible.usj import Node

MONTHS = {3: "March", 4: "April", 5: "May"}
HEADS = ("Years", "Old Style", "New Style")
DAGGER = "†"
# The end of the table is the start plus this, rounded to the nearest ROUND.
SPAN = 100
ROUND = 50


def julian_pascha(year: int) -> tuple[int, int]:
    """The month and day of Pascha in the Julian calendar, by Meeus's
    algorithm for the Julian paschalion."""
    a, b, c = year % 4, year % 7, year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month, day = divmod(d + e + 114, 31)
    return month, day + 1


def gregorian(year: int, month: int, day: int) -> dt.date:
    """The Gregorian date of a Julian one, through the Julian Day Number."""
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    jdn = day + (153 * m + 2) // 5 + 365 * y + y // 4 - 32083
    # The JDN of the proleptic Gregorian calendar's ordinal day 1.
    return dt.date.fromordinal(jdn - 1721425)


def western_easter(year: int) -> dt.date:
    """Easter in the Gregorian calendar, by the Meeus/Jones/Butcher algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


@dataclass(frozen=True)
class Pascha:
    year: int
    old_style: tuple[int, int]
    new_style: dt.date
    # Whether the Western Easter falls on the same day.
    shared: bool


def pascha(year: int) -> Pascha:
    old_style = julian_pascha(year)
    new_style = gregorian(year, *old_style)
    return Pascha(year, old_style, new_style, new_style == western_easter(year))


def today() -> dt.date:
    """The date of the build: SOURCE_DATE_EPOCH's, where it is set, so that a
    build can be pinned, and otherwise the clock's."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        return dt.datetime.fromtimestamp(int(epoch), dt.UTC).date()
    return dt.date.today()


def first_year(date: dt.date) -> int:
    """The year of the next Pascha: this year's until it is past."""
    return date.year if date <= pascha(date.year).new_style else date.year + 1


def last_year(start: int) -> int:
    """The start plus a hundred years, rounded to the nearest fifty."""
    return (start + SPAN + ROUND // 2) // ROUND * ROUND


def span(date: dt.date) -> tuple[int, int]:
    """The first and last years of the table built on a date."""
    start = first_year(date)
    return start, last_year(start)


def written(month: int, day: int) -> str:
    return f"{MONTHS[month]} {day}"


def table(start: int, end: int) -> Node:
    """The table of Pascha from one year to another, each year in both
    styles, daggered where the Western Easter falls on the same day."""

    def row(p: Pascha) -> Node:
        year = f"{p.year}{DAGGER if p.shared else ''}"
        return usj.row(
            usj.cell("tc1", year),
            usj.cell("tc2", written(*p.old_style)),
            usj.cell("tc3", written(p.new_style.month, p.new_style.day)),
        )

    heads = usj.row(*(usj.cell(f"th{n}", head) for n, head in enumerate(HEADS, 1)))
    return {
        "type": "table",
        "content": [heads, *(row(pascha(year)) for year in range(start, end + 1))],
    }
