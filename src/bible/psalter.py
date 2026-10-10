"""The Psalter's kathismata and stases, added after its poetry is aligned."""

from bible import scripture, usj
from bible.checks import require
from bible.policy_schema import Psalter
from bible.usj import Document, Node

ORDINALS = (
    "First",
    "Second",
    "Third",
    "Fourth",
    "Fifth",
    "Sixth",
    "Seventh",
    "Eighth",
    "Ninth",
    "Tenth",
    "Eleventh",
    "Twelfth",
    "Thirteenth",
    "Fourteenth",
    "Fifteenth",
    "Sixteenth",
    "Seventeenth",
    "Eighteenth",
    "Nineteenth",
    "Twentieth",
)


def divided(doc: Document, policy: Psalter) -> Document:
    """Derive every opening from the preceding endpoint; share unchanged nodes."""
    groups = policy["kathismata"]
    require(len(groups) == 20, "Psalter needs twenty kathismata")
    require(
        all(len(group) == 3 for group in groups),
        "Psalter needs three stases per kathisma",
    )
    verses = scripture.verses(doc)
    labels = list(verses)
    chapters: dict[int, list[str]] = {}
    for label in labels:
        chapters.setdefault(int(label.split(":")[0]), []).append(label)
    require(
        list(chapters) == list(range(1, 152)), "Psalter needs Psalms 1–151 in order"
    )
    require(labels[0] == "1:1", "Psalter must open at Psalm 1:1")
    positions = {label: at for at, label in enumerate(labels)}
    major: dict[int, str] = {}
    rules: set[int] = set()
    minor: dict[str, Node] = {}
    previous = -1
    second: tuple[int, int] = (0, -1)
    for number, group in enumerate(groups, 1):
        for stasis, endpoint in enumerate(group, 1):
            require(
                type(endpoint) in (int, str), f"Invalid Psalter endpoint: {endpoint!r}"
            )
            if isinstance(endpoint, int):
                require(endpoint in chapters, f"Missing Psalter endpoint: {endpoint}")
                end = chapters[endpoint][-1]
            else:
                end = endpoint
            require(end in positions, f"Missing Psalter endpoint: {end}")
            at = positions[end]
            require(previous < at, f"Unordered Psalter endpoint: {end}")
            opening = labels[previous + 1]
            chapter, verse = opening.split(":")
            if stasis == 1:
                require(
                    verse == "1", f"Kathisma {number} opens inside a psalm: {opening}"
                )
                major[int(chapter)] = f"The {ORDINALS[number - 1]} Kathisma"
            elif number == 17:
                minor[opening] = usj.para("s2", f"{ORDINALS[stasis - 1]} Stasis")
                if stasis == 2:
                    second = (previous + 1, at)
            else:
                require(
                    verse == "1", f"Ordinary stasis opens inside a psalm: {opening}"
                )
                rules.add(int(chapter))
            require(
                (number == 17 and end.startswith("118:"))
                or (number != 17 and isinstance(endpoint, int)),
                f"Partial psalm endpoint outside the Seventeenth Kathisma: {end}",
            )
            previous = at
    require(labels[previous] == chapters[150][-1], "Kathismata must cover Psalms 1–150")
    require(
        groups[16][-1] == chapters[118][-1],
        "Seventeenth Kathisma must end with Psalm 118",
    )
    middle = policy["middle"]
    require(
        middle in positions
        and middle not in minor
        and second[0] <= positions[middle] <= second[1],
        f"Psalter Middle must fall within the Second Stasis: {middle}",
    )
    minor[middle] = usj.para("s3", "Middle")
    blocks: list[Node] = []
    chapter = ""
    met: set[str] = set()
    for block in doc["content"]:
        if block["type"] == "chapter":
            chapter = block["number"]
            if int(chapter) in rules:
                blocks.append(usj.para("sd2"))
            blocks.append(block)
            if int(chapter) in major:
                blocks.append(usj.para("ms1", major[int(chapter)]))
        elif block["type"] == "para":
            start = 0
            for at, item in enumerate(block["content"]):
                if not usj.is_type(item, "verse"):
                    continue
                label = f"{chapter}:{item['number']}"
                if label in minor:
                    if at > start:
                        blocks.append({**block, "content": block["content"][start:at]})
                    blocks.append(minor[label])
                    met.add(label)
                    start = at
            blocks.append(
                block if start == 0 else {**block, "content": block["content"][start:]}
            )
        else:
            blocks.append(block)
    require(met == set(minor), f"Unplaced Psalter headings: {set(minor) - met}")
    return usj.with_blocks(doc, blocks)
