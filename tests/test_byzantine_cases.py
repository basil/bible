"""Reading probes: what the Orthodox Liturgical English Bible (OLEB) must
and must not say at known verses (docs/new-testament.md)."""

from __future__ import annotations

import re
from typing import TypedDict

import pytest

from bible import scripture


class Probe(TypedDict):
    """A verse, the patterns its text must and must not match, and why."""

    verse: str
    required: list[str]
    forbidden: list[str]
    why: str


PROBES: list[Probe] = [
    {
        "verse": "MAT 3:8",
        "required": [r"\bfruit\b"],
        "forbidden": [r"\bfruits\b"],
        "why": "RP singular fruit.",
    },
    {
        "verse": "MAT 3:11",
        "required": [],
        "forbidden": [r"\bfire\b"],
        "why": "RP lacks kai puri, unlike TR and many critical-text translations.",
    },
    {
        "verse": "MAT 4:10",
        "required": ["behind me"],
        "forbidden": [],
        "why": "RP includes opiso mou.",
    },
    {
        "verse": "MAT 5:27",
        "required": [],
        "forbidden": ["old time|ancients"],
        "why": "RP lacks the old-time attribution.",
    },
    {
        "verse": "MAT 8:15",
        "required": ["(?:unto|to|serv(?:e|ed)) him"],
        "forbidden": ["unto them|to them"],
        "why": "RP singular recipient.",
    },
    {
        "verse": "MAT 10:8",
        "required": [],
        "forbidden": ["raise the dead"],
        "why": "RP lacks the dead-raising command here.",
    },
    {
        "verse": "MAT 26:26",
        "required": ["thank"],
        "forbidden": ["bless"],
        "why": "RP eucharistesas, not eulogesas.",
    },
    {
        "verse": "MAT 27:35",
        "required": [],
        "forbidden": ["fulfil|prophet"],
        "why": "RP lacks the appended fulfilment quotation.",
    },
    {
        "verse": "MAT 27:41",
        "required": ["Pharisee"],
        "forbidden": [],
        "why": "RP adds Pharisees.",
    },
    {
        "verse": "MAT 28:19",
        "required": [],
        "forbidden": ["therefore"],
        "why": "RP lacks oun.",
    },
    {
        "verse": "MRK 13:32",
        "required": ["day or (?:that )?hour"],
        "forbidden": ["day and"],
        "why": "RP disjunction.",
    },
    {
        "verse": "LUK 2:22",
        "required": ["their purification"],
        "forbidden": ["her purification"],
        "why": "RP plural pronoun.",
    },
    {
        "verse": "LUK 8:31",
        "required": ["he (?:besought|begged)"],
        "forbidden": ["they (?:besought|begged)"],
        "why": "RP singular predicate.",
    },
    {
        "verse": "LUK 9:23",
        "required": [],
        "forbidden": ["daily|every day"],
        "why": "RP lacks kath hemeran.",
    },
    {
        "verse": "JHN 6:69",
        "required": ["Christ|Messiah", "Son"],
        "forbidden": ["Holy One"],
        "why": "RP retains Christ/Son reading; ESV is an external comparison, not the target.",
    },
    {
        "verse": "ACT 9:5",
        "required": [],
        "forbidden": ["kick|goad|prick"],
        "why": "RP lacks the added saying.",
    },
    {
        "verse": "ACT 9:6",
        "required": [],
        "forbidden": ["trembl|astonish|what wilt|what do.*want"],
        "why": "RP lacks the added response and speaker clause.",
    },
    {
        "verse": "ACT 24:6",
        "required": [],
        "forbidden": ["according to our law|judged|judge him"],
        "why": "RP lacks the law-trial clause.",
    },
    {
        "verse": "ACT 24:8",
        "required": [],
        "forbidden": ["commanding|accusers"],
        "why": "RP lacks the command clause.",
    },
    {
        "verse": "EPH 4:6",
        "required": ["in us all"],
        "forbidden": ["in you all"],
        "why": "RP first-person plural.",
    },
    {
        "verse": "ROM 8:1",
        "required": ["flesh", "Spirit"],
        "forbidden": [],
        "why": "RP retains the flesh/Spirit clause here.",
    },
    {
        "verse": "1PE 5:10",
        "required": ["called you", "(?:shall|will).*stablish"],
        "forbidden": ["called us"],
        "why": "RP second-person plural plus future establish, strengthen, settle after optative perfect.",
    },
    {
        "verse": "1JN 5:7",
        "required": [],
        "forbidden": ["Father|Holy Ghost|Holy Spirit|heaven"],
        "why": "RP lacks the heavenly witness clause.",
    },
    {
        "verse": "1JN 5:8",
        "required": ["Spirit", "water", "blood"],
        "forbidden": ["in earth|on earth"],
        "why": "RP verse begins the list; no duplicated earthly witness formula.",
    },
    {
        "verse": "REV 2:17",
        "required": ["manna"],
        "forbidden": ["to eat"],
        "why": "Specifically RP2018 omission of phagein.",
    },
    {
        "verse": "REV 1:8",
        "required": ["Lord God"],
        "forbidden": ["beginning and (?:the )?end"],
        "why": "Both the divine title and omitted clause must be addressed.",
    },
    {
        "verse": "REV 13:5",
        "required": [r"\bblasphemy\b", "war"],
        "forbidden": ["blasphemies"],
        "why": "Singular noun plus polemon; a one-edit partial candidate fails.",
    },
    {
        "verse": "REV 20:2",
        "required": ["deceiv", "whole world"],
        "forbidden": [],
        "why": "RP adds the relative clause.",
    },
    {
        "verse": "REV 22:21",
        "required": ["saints"],
        "forbidden": ["our Lord"],
        "why": "RP has all the saints and lacks our.",
    },
]
# verse -> reason, for probes the OLEB does not yet satisfy
XFAIL: dict[str, str] = {}


def test_there_are_29_probes() -> None:
    assert len(PROBES) == 29
    assert len({p["verse"] for p in PROBES}) == 29
    for p in PROBES:
        assert p["required"] or p["forbidden"]
        for pattern in [*p["required"], *p["forbidden"]]:
            re.compile(pattern)


@pytest.fixture(scope="module")
def texts(prepared_verses: dict[str, scripture.Verse]) -> dict[str, str]:
    return {ref: verse.text for ref, verse in prepared_verses.items()}


@pytest.mark.parametrize(
    "probe",
    [
        pytest.param(
            p,
            id=p["verse"],
            marks=(
                [pytest.mark.xfail(reason=XFAIL[p["verse"]], strict=True)]
                if p["verse"] in XFAIL
                else []
            ),
        )
        for p in PROBES
    ],
)
def test_probe(probe: Probe, texts: dict[str, str]) -> None:
    text = texts.get(probe["verse"])
    assert text is not None, f"{probe['verse']} is not in the OLEB"
    for pattern in probe["required"]:
        assert re.search(
            pattern, text
        ), f"{probe['verse']} lacks /{pattern}/ ({probe['why']}): {text}"
    for pattern in probe["forbidden"]:
        assert not re.search(
            pattern, text
        ), f"{probe['verse']} still has /{pattern}/ ({probe['why']}): {text}"
