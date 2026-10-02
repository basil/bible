"""Where each of the edition's Old Testament verses stands in the King James
Bible, by two witnesses and the editor's readings.

The table (tvtms.py) says where a verse of a Bible numbered like this one
should stand. The words say where it does: the verses of the two translations
are aligned by the rarer words they share, without regard to their numbers.
Where the witnesses agree, a verse stands where they say; where they don't,
the words decide if they speak, and the table if they are silent. What the
editor has read (edition/versification.json) stands, whatever the witnesses
give.

The build works the places out afresh each time, so that nothing is checked
in but the readings. The review lists every run, and both translations' words
for those that rest on the words or on their place alone, to be read.
"""

import collections
import re

from bible import alignment, scripture, tvtms, usj, versification
from bible.checks import require, require_fields
from bible.references import Verse, runs

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

    def __init__(self, books, kjv, *, policy):
        self.policy = policy
        self.books = {
            code: versification.kjv_book(code, policy=policy)
            for code in policy.versification["old_testament"]
        }
        self.edition = alignment.Verses(
            {code: books[code] for code in self.books},
            without=versification.apocryphal(policy=policy),
        )
        self.kjv = alignment.Verses(
            {code: kjv[code] for code in self.books.values()}, titled=True
        )
        self.weight = alignment.weights(self.edition.words, self.kjv.words)

    def similarity(self, verse, counterpart):
        return alignment.similarity(
            self.weight, self.edition.words[verse], self.kjv.words[counterpart]
        )


def _best(words, index, order, others, weight):
    """The verse among the others that a verse's words pick out, and its score."""
    candidates = collections.Counter()
    # In the words' own order, so that verses that tie are taken alike each time.
    for word in sorted(words):
        found = index.get(word, ())
        if len(found) <= COMMON:
            for n in found:
                candidates[n] += weight[word]
    scored = [
        (alignment.similarity(weight, words, others[order[n]]), str(order[n]), n)
        for n, _ in candidates.most_common(8)
    ]
    if not scored:
        return None, 0
    score, _, n = max(scored)
    return order[n], score


def _index(words, verses):
    """The verses that have each word, by their places in their book's order."""
    index = collections.defaultdict(list)
    for n, verse in enumerate(verses):
        for word in words[verse]:
            index[word].append(n)
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
            texts.edition.words[verse],
            their_index,
            theirs,
            texts.kjv.words,
            texts.weight,
        )
        if other is None or score < ANCHOR:
            continue
        back, _ = _best(
            texts.kjv.words[other], our_index, ours, texts.edition.words, texts.weight
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


def tabled(texts, books):
    """Each verse's counterparts by the table, or None where its rows disagree.

    A verse the table says nothing of keeps its number.
    """
    names = {code: TABLE_NAMES.get(code, [kjv]) for code, kjv in texts.books.items()}
    bible = tvtms.Bible(
        {name: books[code] for code, listed in names.items() for name in listed}
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


def witnesses(books, kjv, *, policy):
    """Both witnesses on every verse of every book, block by block."""
    texts = Texts(books, kjv, policy=policy)
    table = tabled(texts, books)
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
    """What the witnesses give, by book, as (edition verses, King James
    verses, witness): every verse that doesn't keep its number, and every
    one that keeps it against the table.

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


def read(texts, code, *, policy):
    """The runs of a book that the editor has read, which stand whatever the
    witnesses give."""
    found = []
    for run in policy.versification["readings"].get(code, []):
        name = f"{run.get('edition')} = {run.get('kjv')}"
        require_fields(run, {"edition", "kjv", "why"}, {"pairs"}, f"Reading {name}")
        require(run["edition"] and run["why"], f"Reading without its reason: {name}")
        ours = versification.verses(run["edition"])
        theirs = versification.verses(run["kjv"]) if run["kjv"] else []
        require(
            all(v in texts.edition.words for v in ours)
            and all(v in texts.kjv.words for v in theirs),
            f"Reading of a verse that its Bible lacks: {name}",
        )
        found.append((ours, theirs, "reading", run["why"]))
    return found


def written(texts, code, entries, *, policy):
    """A book's runs: what has been read, what the witnesses give of the
    rest, and what the edition wants of the King James Bible's verses."""
    decided = read(texts, code, policy=policy)
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
    # A reading may say which part of its run each verse faces.
    declared_pairs = {
        (run["edition"], run["kjv"]): run["pairs"]
        for run in policy.versification["readings"].get(code, [])
        if "pairs" in run
    }
    for run in written_runs:
        pair = (run["edition"], run["kjv"])
        if pair in declared_pairs:
            run["pairs"] = declared_pairs[pair]
    return written_runs + [
        {"edition": None, "kjv": str(passage)} for passage in runs(wanting)
    ]


def placed(books, kjv, *, policy):
    """Every book's runs, as the witnesses and the editor's readings give
    them: of the edition's books and the King James Bible's, as documents."""
    unknown = sorted(
        set(policy.versification["readings"])
        - set(policy.versification["old_testament"])
    )
    require(not unknown, f"Readings outside the Old Testament: {unknown}")
    texts, report = witnesses(books, kjv, policy=policy)
    proposed = proposal(texts, report)
    found = {
        code: written(texts, code, proposed[code], policy=policy)
        for code in texts.books
    }
    return {code: listed for code, listed in found.items() if listed}


def _runs(entries):
    """Entries as runs, verse for verse where a run of verses faces a run as
    long, and as a block where it doesn't."""
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


# A heading set among a verse's words, which the review leaves out.
HEADING = re.compile(r"s\d?|d")


def _plain(books):
    """Each verse's words as printed, by book and label, without its notes
    or a heading set within it."""
    found = {}
    for code, doc in books.items():
        for label, verse in scripture.verses(doc).items():
            found[code, label] = scripture.plain(
                " ".join(
                    usj.text_of(doc["content"][block]["content"][start:end])
                    for block, start, end, _ in verse.parts
                    # A paragraph that opens within the verse may be a heading.
                    if start or not HEADING.fullmatch(doc["content"][block]["marker"])
                )
            )
    return found


def report(found, books, kjv):
    """Every run, by book, for the review; those that rest on the words or on
    their place alone with both translations' words, for the editor to read."""
    # Only of the books that have such runs.
    unread = [
        run
        for listed in found.values()
        for run in listed
        if run.get("by") in {"words", "place"}
    ]
    ours = _plain(
        {code: books[code] for code in {run["edition"].split()[0] for run in unread}}
    )
    theirs = _plain(
        {
            code: kjv[code]
            for code in {run["kjv"].split()[0] for run in unread if run["kjv"]}
        }
    )
    lines = ["# Numbering\n\n"]
    for code, listed in found.items():
        lines.append(f"## {code}\n\n")
        for run in listed:
            by = run.get("by", "wanting")
            why = f": {run['why']}" if "why" in run else ""
            lines.append(
                f"- {run['edition'] or 'nothing'} = {run['kjv'] or 'nothing'} ({by}{why})\n"
            )
            if by not in {"words", "place"}:
                continue
            for side, words, passages in (
                ("Brenton", ours, run["edition"]),
                ("King James", theirs, run["kjv"]),
            ):
                for verse in versification.verses(passages) if passages else ():
                    said = words.get(
                        (verse.book, f"{verse.chapter}:{verse.number}{verse.letter}")
                    )
                    lines.append(f"  - {side} {verse.label}: {said or '(title)'}\n")
        lines.append("\n")
    return "".join(lines)
