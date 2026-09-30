"""Seeding edition/versification.json: where each of the edition's Old
Testament verses stands in the King James Bible, by two witnesses.

The table (tvtms.py) says where a verse of a Bible numbered like this one
should stand. The words say where it does: the verses of the two translations
are aligned by the rarer words they share, without regard to their numbers.
Where the witnesses agree, the seed proposes their answer; where they don't,
it lists both for review. The build never reads the seed: what is reviewed is
copied into edition/versification.json, and tested there. What the editor has
read there stands, whatever the witnesses propose.
"""

import collections
import json
import re

from bible import alignment, paths, tvtms, versification
from bible.files import write_json
from bible.references import Verse, runs
from bible.usfm import NOTE, plain_text, verse_spans
from bible.validate import validate

# The table's names for the edition's books, where they aren't the King James code.
TABLE_NAMES = {"ESG": ["EST", "ESG"], "EZR": ["EZR", "2ES"]}
# A pair of verses must share this much to anchor the alignment...
ANCHOR = 0.3
# ...and this much to be aligned between anchors.
MATCH = 0.12
# A word found in more verses of a book than this can't pick one out.
COMMON = 60
# How far one answer must outscore another to be preferred.
MARGIN = 0.1
# A verse left over joins the pair beside it if the pair's other side has
# this share of its words.
MERGED = 0.5
# What the table's word is worth beside the words' own.
PRIOR = 0.15
# A stretch of verses stands elsewhere if its verses there outmatch, by this
# much, those the order of the book would give them.
MOVED = 0.25


class Texts:
    """Both translations' verses and words, book by book."""

    def __init__(self, scripture, archives):
        self.books = {
            code: versification.kjv_book(code)
            for code in versification.DATA["old_testament"]
        }
        self.edition = alignment.Verses(
            {code: scripture[code] for code in self.books},
            without=versification.apocryphal(),
        )
        self.kjv = alignment.Verses(
            {code: archives["kjv"][code] for code in self.books.values()}, titled=True
        )
        self.weight = alignment.weights(self.edition.words, self.kjv.words)

    def similarity(self, verse, counterpart):
        return alignment.similarity(
            self.weight, self.edition.words[verse], self.kjv.words[counterpart]
        )


def _best(words, index, others, weight):
    """The verse among the others that a verse's words pick out, and its score."""
    candidates = collections.Counter()
    # In the words' own order, so that verses that tie are taken alike each time.
    for word in sorted(words):
        found = index.get(word, ())
        if len(found) <= COMMON:
            for other in found:
                candidates[other] += weight[word]
    scored = [
        (alignment.similarity(weight, words, others[other]), str(other), other)
        for other, _ in candidates.most_common(8)
    ]
    if not scored:
        return None, 0
    score, _, other = max(scored)
    return other, score


def _index(words, verses):
    """The verses that have each word, in their book's order."""
    index = collections.defaultdict(list)
    for verse in verses:
        for word in words[verse]:
            index[word].append(verse)
    return index


def outvotes(texts, table, verse, other):
    """Whether a verse's words put it at another verse than the table does,
    by more than the table's word is worth."""
    said = [v for v in table.get(verse) or () if v in texts.kjv.words]
    if other in said:
        return True
    rival = max((texts.similarity(verse, v) for v in said), default=0)
    return texts.similarity(verse, other) - rival >= PRIOR


def anchors(texts, code, table):
    """Pairs of verses that pick each other out, as (edition, kjv, score) positions."""
    ours, theirs = texts.edition.order[code], texts.kjv.order[texts.books[code]]
    our_index = _index(texts.edition.words, ours)
    their_index = _index(texts.kjv.words, theirs)
    position = {verse: i for i, verse in enumerate(theirs)}
    found = []
    for i, verse in enumerate(ours):
        other, score = _best(
            texts.edition.words[verse], their_index, texts.kjv.words, texts.weight
        )
        if other is None or score < ANCHOR:
            continue
        back, _ = _best(
            texts.kjv.words[other], our_index, texts.edition.words, texts.weight
        )
        if back == verse and outvotes(texts, table, verse, other):
            found.append((i, position[other], score))
    return found


def chain(found):
    """The anchors that stand in the same order in both translations: the
    heaviest run of them that rises in both."""
    found = sorted(found)
    weight = [score for _, _, score in found]
    before = [None] * len(found)
    for n, (i, j, score) in enumerate(found):
        for m in range(n):
            if found[m][1] < j and found[m][0] < i and weight[m] + score > weight[n]:
                weight[n], before[n] = weight[m] + score, m
    if not found:
        return []
    n = max(range(len(found)), key=weight.__getitem__)
    kept = []
    while n is not None:
        kept.append(found[n])
        n = before[n]
    return kept[::-1]


def _between(texts, ours, theirs, table):
    """Align two stretches of verses in order, leaving unlike verses unpaired.

    The table's word counts for something: a verse stands where the table
    says unless the words of another outvote it.
    """
    rows, columns = len(ours), len(theirs)

    def worth(i, j):
        said = theirs[j] in (table.get(ours[i]) or ())
        return texts.similarity(ours[i], theirs[j]) - MATCH + (PRIOR if said else 0)

    best = [[0.0] * (columns + 1) for _ in range(rows + 1)]
    for i in range(rows - 1, -1, -1):
        for j in range(columns - 1, -1, -1):
            best[i][j] = max(
                best[i + 1][j], best[i][j + 1], best[i + 1][j + 1] + worth(i, j)
            )
    pairs, i, j = [], 0, 0
    while i < rows and j < columns:
        pair = worth(i, j)
        if best[i][j] == best[i + 1][j + 1] + pair and pair > 0:
            pairs.append((ours[i], theirs[j]))
            i, j = i + 1, j + 1
        elif best[i][j] == best[i + 1][j]:
            i += 1
        else:
            j += 1
    return pairs


def moved(texts, code, found, kept):
    """The stretches of verses that stand elsewhere in the King James Bible,
    as (edition, kjv) positions: anchors off the chain, three or more on one
    diagonal, that the verses the chain would give them can't match.

    A passage the Bible itself repeats, as Pharaoh's dream and its telling,
    picks out its twin as well as its counterpart, and is no move.
    """
    ours, theirs = texts.edition.order[code], texts.kjv.order[texts.books[code]]
    on_chain = {i: j for i, j, _ in kept}
    places = sorted(on_chain)

    def in_order(i):
        """The verse the chain gives a position: its diagonal's, if it has one."""
        before = max((p for p in places if p < i), default=None)
        after = min((p for p in places if p > i), default=None)
        for anchor in (before, after):
            if anchor is not None:
                j = on_chain[anchor] + i - anchor
                low = on_chain[before] if before is not None else -1
                high = on_chain[after] if after is not None else len(theirs)
                if low < j < high:
                    return j
        return None

    def gain(i, j):
        j0 = in_order(i)
        rival = texts.similarity(ours[i], theirs[j0]) if j0 is not None else 0
        return texts.similarity(ours[i], theirs[j]) - rival

    blocks, block = [], []
    for i, j, _ in sorted(a for a in found if a[0] not in on_chain):
        if block and j - i == block[-1][1] - block[-1][0] and i - block[-1][0] <= 3:
            block.append((i, j))
        else:
            blocks.append(block)
            block = [(i, j)]
    blocks.append(block)
    pairs = {}
    for block in blocks:
        if len(block) < 3 or sum(gain(i, j) for i, j in block) / len(block) < MOVED:
            continue
        # The block runs on either way as far as its verses outmatch the chain's.
        (first, j0), last = block[0], block[-1][0]
        span = range(first, last + 1)
        for step, start in ((-1, first - 1), (1, last + 1)):
            i = start
            while (
                0 <= i < len(ours)
                and 0 <= i + j0 - first < len(theirs)
                and i not in on_chain
                and texts.similarity(ours[i], theirs[i + j0 - first]) >= MATCH
                and gain(i, i + j0 - first) >= MARGIN
            ):
                span = range(min(span[0], i), max(span[-1], i) + 1)
                i += step
        pairs.update({i: i + j0 - first for i in span if i not in on_chain})
    return pairs


def aligned(texts, code, table):
    """A book's verses and their counterparts by their words, as blocks of
    (edition verses, King James verses), either of which may be empty.

    The chain of anchors divides the book, and between two of them the verses
    are aligned in order. What stands elsewhere, as the chapters Jeremias
    arranges otherwise, is aligned along its own diagonal. A verse left over
    beside a pair joins it, if the pair's other side has its words: Brenton
    often divides a verse where the King James Bible doesn't, or the reverse.
    """
    ours, theirs = texts.edition.order[code], texts.kjv.order[texts.books[code]]
    found = anchors(texts, code, table)
    kept = chain(found)
    elsewhere = moved(texts, code, found, kept)
    pairs = {ours[i]: theirs[j] for i, j, _ in kept}
    taken = set(pairs.values())
    for i, j in sorted(elsewhere.items()):
        # A verse has one counterpart: the chain's, or the first to claim it.
        if theirs[j] not in taken:
            pairs[ours[i]] = theirs[j]
            taken.add(theirs[j])
    ends = [(-1, -1), *((i, j) for i, j, _ in kept), (len(ours), len(theirs))]
    for (i0, j0), (i1, j1) in zip(ends, ends[1:]):
        gap = [v for v in ours[i0 + 1 : i1] if v not in pairs]
        facing = [v for v in theirs[j0 + 1 : j1] if v not in taken]
        pairs.update(_between(texts, gap, facing, table))
    pairs.update(_out_of_order(texts, ours, theirs, pairs, table))
    placed = _in_place(ours, theirs, pairs)
    pairs.update(placed)
    blocks = {verse: ([verse], [other]) for verse, other in pairs.items()}
    facing = {other: blocks[verse] for verse, other in pairs.items()}
    _join(texts.edition, texts.kjv, ours, blocks, 0)
    _join(texts.kjv, texts.edition, theirs, facing, 1)
    result, seen = [], set()
    paired = {id(block): block for block in blocks.values()}
    for verse in ours:
        block = blocks.get(verse)
        if block is None:
            result.append(([verse], [], "words"))
        elif id(block) not in seen:
            seen.add(id(block))
            by = "place" if block[0][0] in placed and len(block[0]) == 1 else "words"
            result.append((*block, by))
    claimed = {v for block in paired.values() for v in block[1]}
    result += [([], [verse], "words") for verse in theirs if verse not in claimed]
    # A verse that holds a psalm's title and its first words is its first verse.
    return [
        (
            ours,
            [v for v in theirs if v.number or all(o.number == 0 for o in theirs)],
            by,
        )
        for ours, theirs, by in result
    ]


def _in_place(ours, theirs, pairs):
    """Verses left over that face as many left over, between two pairs that
    stand in the same order: names spelt otherwise share no words.

    A lettered verse is an addition, and faces nothing. Nor does a title face
    a verse.
    """
    position = {verse: j for j, verse in enumerate(theirs)}
    taken = set(pairs.values())
    found, run, before = {}, [], -1
    for verse in [*ours, None]:
        if verse is not None and verse not in pairs:
            run.append(verse)
            continue
        after = position[pairs[verse]] if verse is not None else len(theirs)
        facing = theirs[before + 1 : after] if before < after else []
        if (
            run
            and len(run) == len(facing)
            and not any(v.letter for v in run)
            and not any(o in taken or o.number == 0 for o in facing)
        ):
            found.update(zip(run, facing))
        run, before = [], after
    return found


def _out_of_order(texts, ours, theirs, pairs, table):
    """Verses left over that pick each other out within a chapter, as where
    the Greek numbers Gad after the other tribes."""
    taken = set(pairs.values())
    left = collections.defaultdict(list)
    for verse in theirs:
        if verse not in taken:
            left[verse.chapter].append(verse)
    found = {}
    for verse in ours:
        if verse in pairs or not left[verse.chapter]:
            continue
        score, _, other = max(
            (texts.similarity(verse, o), str(o), o) for o in left[verse.chapter]
        )
        rivals = [v for v in ours if v.chapter == verse.chapter and v not in pairs]
        if (
            score >= ANCHOR
            and outvotes(texts, table, verse, other)
            and all(texts.similarity(rival, other) <= score for rival in rivals)
        ):
            found[verse] = other
            left[verse.chapter].remove(other)
    return found


def _join(near, far, order, blocks, side):
    """Join each verse left over on one side to the pair before or after it,
    if the pair's other side has the greater share of its words."""
    for n, verse in enumerate(order):
        if verse in blocks:
            continue
        best = None
        for neighbour in (n - 1, n + 1):
            if not 0 <= neighbour < len(order):
                continue
            block = blocks.get(order[neighbour])
            if block is None:
                continue
            share = near.score(near.words[verse], far.bag(block[1 - side]))
            if share >= MERGED and (best is None or share > best[0]):
                best = (share, neighbour, block)
        if best:
            _, neighbour, block = best
            if neighbour < n:
                block[side].append(verse)
            else:
                block[side].insert(0, verse)
            blocks[verse] = block


def tabled(texts, scripture):
    """Each verse's counterparts by the table, or None where its rows disagree.

    A verse the table says nothing of keeps its number.
    """
    names = {code: TABLE_NAMES.get(code, [kjv]) for code, kjv in texts.books.items()}
    bible = tvtms.Bible(
        {name: scripture[code] for code, listed in names.items() for name in listed}
    )
    account = tvtms.account(bible, names)
    result = {}
    for verse in texts.edition.words:
        kjv = texts.books[verse.book]
        answers = {standard for standard, _ in account.get(verse, [])}
        if len(answers) > 1:
            result[verse] = None
        elif answers:
            (standard,) = answers
            # The table names a book as the tradition it describes does.
            result[verse] = tuple(
                Verse(kjv, v.chapter, v.number) if v.book in names[verse.book] else v
                for v in standard
            )
        elif verse.letter:
            result[verse] = ()
        else:
            result[verse] = (Verse(kjv, verse.chapter, verse.number),)
    return result


def witnesses(scripture, archives):
    """Both witnesses on every verse of every book, block by block."""
    texts = Texts(scripture, archives)
    table = tabled(texts, scripture)
    report = {}
    for code in texts.books:
        blocks = []
        for ours, theirs, by in aligned(texts, code, table):
            answers = [table[verse] for verse in ours]
            said = None
            if all(answer is not None for answer in answers):
                said = [v for answer in answers for v in answer]
            blocks.append(
                {
                    "edition": ours,
                    "words": theirs,
                    "table": said,
                    "by": by,
                    "score": (
                        alignment.similarity(
                            texts.weight,
                            texts.edition.bag(ours),
                            texts.kjv.bag(theirs),
                        )
                        if ours and theirs
                        else 0
                    ),
                }
            )
        report[code] = blocks
    return texts, report


def settle(texts, blocks):
    """Give back to the table what the words took without cause.

    Words carried over a verse's end draw it to its neighbour, and leave the
    next verse with no place. The words may not leave a verse without a place
    that the table gives one: every verse that stands in its way goes back to
    the table's place too, if it has one, and if none can't, nothing moves.
    """

    def said(block):
        real = [v for v in block["table"] or () if v in texts.kjv.words]
        return real if real and len(real) == len(block["table"]) else None

    holder = {v: n for n, b in enumerate(blocks) if b["edition"] for v in b["words"]}
    for n, block in enumerate(blocks):
        if not block["edition"] or block["words"] or not said(block):
            continue
        moving, waiting = {n}, [n]
        while waiting:
            wanted = said(blocks[waiting.pop()])
            for other in {holder[v] for v in wanted if v in holder} - moving:
                theirs = said(blocks[other])
                if theirs is None or sorted(map(str, theirs)) == sorted(
                    map(str, blocks[other]["words"])
                ):
                    moving = None
                    break
                moving.add(other)
                waiting.append(other)
            if moving is None:
                break
        if moving is None:
            continue
        for m in moving:
            for verse in blocks[m]["words"]:
                del holder[verse]
        for m in moving:
            blocks[m]["words"], blocks[m]["by"] = said(blocks[m]), "table"
            holder.update({verse: m for verse in blocks[m]["words"]})
    return blocks


def _same(ours, theirs, kjv):
    """Whether verses keep their numbers in the King James Bible."""
    return [(kjv, v.chapter, v.number, v.letter) for v in ours] == [
        (v.book, v.chapter, v.number, v.letter) for v in theirs
    ]


def proposal(texts, report):
    """What the witnesses propose for edition/versification.json, by book, as
    (edition verses, King James verses, witness): every verse that doesn't
    keep its number, and every one that keeps it against the table.

    The words decide where they speak. Where they are silent the table does,
    if no other verse has its place; a verse neither can place is listed
    without a counterpart, to be read.
    """
    result = {}
    for code, blocks in report.items():
        kjv = texts.books[code]
        blocks = settle(texts, blocks)
        claimed = {v for block in blocks if block["edition"] for v in block["words"]}
        entries = []
        for block in blocks:
            ours, theirs, said = block["edition"], block["words"], block["table"]
            real = [v for v in said or () if v in texts.kjv.words]
            if not ours:
                continue
            titled = theirs and all(v.number == tvtms.TITLE for v in theirs)
            if (
                titled
                and real
                and len(real) == len(said)
                and not any(v.number == tvtms.TITLE for v in real)
                and not claimed & set(real)
            ):
                # A verse that opens with the psalm's title shares the title's
                # words, but is the verse the table says: the first.
                theirs, by = real, "table"
                claimed |= set(real)
            elif theirs:
                # Two verses that face one verse are each given it by the table.
                agreed = said is not None and set(said) == set(theirs)
                by = "table" if agreed else block["by"]
            elif real and len(real) == len(said) and not claimed & set(real):
                theirs, by = real, "table"
                claimed |= set(real)
            else:
                by = "words"
            if by == "table" and _same(ours, theirs, kjv):
                continue
            if not theirs and all(v.letter for v in ours):
                # An addition Brenton letters has no counterpart to list.
                continue
            entries.append((ours, theirs, by, None))
        result[code] = entries
    return result


def read(code):
    """The runs of a book that the file's editor has read, which stand
    whatever the witnesses propose."""
    found = []
    for run in versification.DATA["kjv"].get(code, []):
        if run.get("by") == "reading":
            ours = versification.verses(run["edition"]) if run["edition"] else []
            theirs = versification.verses(run["kjv"]) if run["kjv"] else []
            found.append((ours, theirs, "reading", run["why"]))
    return found


def written(texts, code, entries):
    """A book's runs as the file writes them: what has been read, what the
    witnesses propose of the rest, and what the edition wants of the King
    James Bible's verses."""
    decided = read(code)
    ours = {v for entry in decided for v in entry[0]}
    theirs = {v for entry in decided for v in entry[1]}
    kept = [
        entry
        for entry in entries
        if not ours.intersection(entry[0]) and not theirs.intersection(entry[1])
    ]
    order = {v: n for n, v in enumerate(texts.edition.order[code])}
    listed = sorted(
        kept + [entry for entry in decided if entry[0]],
        key=lambda entry: order[entry[0][0]],
    )
    claimed = {v for entry in listed for v in entry[1]}
    # A verse that keeps its number has its place, though nothing lists it.
    named = {v for entry in listed for v in entry[0]}
    for verse in texts.edition.order[code]:
        if verse not in named and not verse.letter:
            claimed.add(Verse(texts.books[code], verse.chapter, verse.number))
    wanting = [
        v
        for v in texts.kjv.order[texts.books[code]]
        if v not in claimed and v.number != tvtms.TITLE
    ]
    written_runs = _runs(listed)
    # Preserve precise overlaps when carrying the editor's readings forward.
    declared_pairs = {
        (run["edition"], run["kjv"]): run["pairs"]
        for run in versification.DATA["kjv"].get(code, [])
        if run.get("by") == "reading" and "pairs" in run
    }
    for run in written_runs:
        pair = (run["edition"], run["kjv"])
        if pair in declared_pairs:
            run["pairs"] = declared_pairs[pair]
    return written_runs + [
        {"edition": None, "kjv": str(passage)} for passage in runs(wanting)
    ]


def seed(scripture, archives):
    """The file's "kjv" as the witnesses and the editor's reading give it."""
    texts, report = witnesses(scripture, archives)
    proposed = proposal(texts, report)
    found = {code: written(texts, code, proposed[code]) for code in texts.books}
    return {code: listed for code, listed in found.items() if listed}


def _runs(entries):
    """Entries as the file writes them, verse for verse where a run of
    verses faces a run as long, and as a block where it doesn't."""
    written = []
    for ours, theirs, by, why in entries:
        last = written[-1] if written else None
        if (
            last
            and (last["by"], last["why"]) == (by, why)
            and len(ours) == len(theirs) == 1
            and last["paired"]
            and _follows(last["ours"][-1], ours[0])
            and _follows(last["theirs"][-1], theirs[0])
        ):
            last["ours"] += ours
            last["theirs"] += theirs
        elif (
            last
            and (last["by"], last["why"]) == (by, why)
            and not theirs
            and not last["theirs"]
            and _follows(last["ours"][-1], ours[0])
        ):
            last["ours"] += ours
        else:
            written.append(
                {
                    "ours": list(ours),
                    "theirs": list(theirs),
                    "by": by,
                    "why": why,
                    "paired": len(ours) == len(theirs) == 1,
                }
            )
    return [
        {
            "edition": "; ".join(map(str, runs(entry["ours"]))),
            "kjv": "; ".join(map(str, runs(entry["theirs"]))) or None,
            "by": entry["by"],
            **({"why": entry["why"]} if entry["why"] else {}),
        }
        for entry in written
    ]


def _follows(verse, other):
    return not (verse.letter or other.letter) and (
        verse.book,
        verse.chapter,
        verse.number + 1,
    ) == (other.book, other.chapter, other.number)


def _plain(scripture):
    """Each verse's words as printed, without its notes, by book and label."""
    found = {}
    for code, text in scripture.items():
        text = NOTE.sub("", text)
        for label, start, end in verse_spans(text):
            found[code, label] = plain_text(
                re.sub(r"\\(?:s\d?|d|c|cp)\b[^\n]*", "", text[start:end])
            )
    return found


def _worklist(found, scripture, archives):
    """The runs that rest on the words or on their place alone, with both
    translations' words, for the editor to read."""
    ours = _plain(scripture)
    theirs = _plain({code: archives["kjv"][code] for code in archives["kjv"]})
    lines = []
    for code, listed in found.items():
        for run in listed:
            if run.get("by") not in {"words", "place"}:
                continue
            lines.append(
                f"## {run['edition']} = {run['kjv'] or 'nothing'} ({run['by']})\n"
            )
            for side, words, passages in (
                ("Brenton", ours, run["edition"]),
                ("King James", theirs, run["kjv"]),
            ):
                for verse in versification.verses(passages) if passages else ():
                    said = words.get(
                        (verse.book, f"{verse.chapter}:{verse.number}{verse.letter}")
                    )
                    lines.append(f"- {side} {verse.label}: {said or '(title)'}\n")
            lines.append("\n")
    return "".join(lines)


def seed_versification():
    """Write what the witnesses propose to build/versification-seed.json,
    beside what differs from the file and what is left to read."""
    archives, prepared = validate()
    scripture = {code: unit.text for code, unit in prepared.items()}
    found = seed(scripture, archives)
    write_json(
        paths.BUILD_DIR / "versification-seed.json",
        {**versification.DATA, "kjv": found},
    )
    (paths.BUILD_DIR / "versification-to-read.md").write_text(
        _worklist(found, scripture, archives), encoding="utf-8"
    )
    before = {
        (code, json.dumps(run, sort_keys=True))
        for code, listed in versification.DATA["kjv"].items()
        for run in listed
    }
    after = {
        (code, json.dumps(run, sort_keys=True))
        for code, listed in found.items()
        for run in listed
    }
    (paths.BUILD_DIR / "versification-changes.md").write_text(
        "".join(
            f"- {mark} {code}: {run}\n"
            for mark, runs_ in (("removed", before - after), ("added", after - before))
            for code, run in sorted(runs_)
        ),
        encoding="utf-8",
    )
    by = collections.Counter(
        run.get("by", "wanting") for listed in found.values() for run in listed
    )
    print(
        f"Seeded {sum(by.values())} runs {dict(sorted(by.items()))}, "
        f"{len(before ^ after)} unlike the file's:",
        paths.BUILD_DIR / "versification-seed.json",
    )
