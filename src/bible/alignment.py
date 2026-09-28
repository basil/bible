"""Comparing verses by their words, to tell a verse from its neighbour.

Existence checks can't see a reference that is off by a verse: a Psalm title
counted or not, a chapter renumbered, a Septuagint addition that Brenton
letters. Words can: a verse shares more of its rarer words with its
counterpart in another translation than with the verses around it.
"""

import collections
import math
import re

from bible.references import Verse, verse_at
from bible.usfm import MARKUP, NOTE, chapter_parts, verse_spans, words_of

# Words so common, or so much the quoting formula's, that sharing them shows nothing.
STOP_WORDS = set(
    """a all also am an and are art as at be because been behold but by did do
    even for from had hath have he her him his i if in into is it its let may me
    might my no nor not o of on or our said saith say says saying shall she so
    spake spoke that the thee their them then there therefore these they this
    thou thy to unto upon us was we were what when wherefore which who whom will
    with written ye you your""".split()
)


def stem(word):
    """A word without the commonest inflexions, so that sows meets sow."""
    for suffix in ("eth", "est", "ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def content_words(text):
    return {stem(w) for w in words_of(text) if w not in STOP_WORDS}


def titles(text):
    """Each chapter's title, by chapter: the words set before its first verse.

    The King James Bible sets a psalm's title so; Brenton numbers it as the
    psalm's first verse or two.
    """
    result = {}
    for chapter in chapter_parts(text)[1]:
        number, head = re.match(r"\\c (\d+)(.*?)(?=\\v |\Z)", chapter, re.S).groups()
        title = re.search(r"\\d ([^\n]*)", head)
        if title and MARKUP.sub("", title[1]).strip():
            result[int(number)] = title[1]
    return result


def title_verses(text):
    """The verses that make up each chapter's title, by chapter, as Brenton
    numbers them: those of the paragraph that the title marker opens."""
    result = {}
    for chapter in chapter_parts(text)[1]:
        number = int(re.match(r"\\c (\d+)", chapter)[1])
        title = re.search(r"\\d\s*\n((?:\\v [^\n]*\n)+)", chapter)
        if title:
            result[number] = re.findall(r"\\v (\S+)", title[1])
    return result


class Verses:
    """Every printed verse's content words, and each book's verses in order.

    With titles, a chapter's title is its verse 0. Verses may be left out.
    """

    def __init__(self, scripture, titled=False, without=()):
        self.words = {}
        self.order = collections.defaultdict(list)
        for code, text in scripture.items():
            # A note's words aren't the verse's.
            text = NOTE.sub("", text)
            heads = titles(text) if titled else {}
            for reference, start, end in verse_spans(text):
                verse = verse_at(code, reference)
                if verse in without:
                    continue
                if verse.chapter in heads:
                    title = Verse(code, verse.chapter, 0)
                    self.words[title] = content_words(heads.pop(verse.chapter))
                    self.order[code].append(title)
                self.words[verse] = content_words(text[start:end])
                self.order[code].append(verse)
        self.index = {
            v: i for verses in self.order.values() for i, v in enumerate(verses)
        }
        frequency = collections.Counter(w for ws in self.words.values() for w in ws)
        self.weight = {
            w: math.log(len(self.words) / (1 + n)) for w, n in frequency.items()
        }

    def bag(self, verses):
        return set().union(*(self.words[v] for v in verses))

    def score(self, quotation, source):
        """The share of the quotation's weighted words the source also has.

        A quotation is usually part of its source verse, so only the
        quotation's side is measured.
        """
        total = sum(self.weight[w] for w in quotation)
        return sum(self.weight[w] for w in quotation & source) / total if total else 0

    def shifted(self, verses, k):
        """The verses k places on in their book's printed order, lettered verses included."""
        result = []
        for verse in verses:
            book = self.order[verse.book]
            i = self.index[verse] + k
            if not 0 <= i < len(book):
                return None
            result.append(book[i])
        return result


def weights(*sides):
    """Each word's weight across translations: the rarer, the heavier."""
    bags = [bag for side in sides for bag in side.values()]
    frequency = collections.Counter(w for ws in bags for w in ws)
    return {w: math.log(len(bags) / (1 + n)) for w, n in frequency.items()}


def similarity(weight, a, b):
    """The weight of the words two bags share, as a share of both bags'."""
    total = sum(weight[w] for w in a) * sum(weight[w] for w in b)
    return sum(weight[w] for w in a & b) / math.sqrt(total) if total else 0
