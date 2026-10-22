"""Acceptance checks on PTXprint's work: first its processed copy of each
unit's text, then the rendered PDF (page size, fonts, contents, the way it
cites, and the phrases in edition/witnesses.json)."""

from __future__ import annotations

import configparser
import io
import re
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from pathlib import Path

from bible import peripherals, scripture, typeface, usj
from bible.checks import CheckFailed, present, require
from bible.files import sha256, write_json
from bible.policy_schema import Witnesses
from bible.project import (
    PROCESSED_DIR,
    processed_usfm,
    project_settings,
    project_usfm,
    text_font,
)
from bible.scripture import plain
from bible.toolchain import capture as capture
from bible.toolchain import run
from bible.usfm import canonical_text, heading, inventory

POINTS_PER_MM = 72 / 25.4
# TeX points (72.27 to the inch) in a PDF point.
TEX_POINTS = 72.27 / 72
XHTML = "{http://www.w3.org/1999/xhtml}"
# Notes, character styles, table cells, the Psalter's chapter label and
# headings, the Pause lines, and acrostic headings, and the terms and
# definitions of Brenton's list of translations, which PTXprint must keep.
KEPT_MARKERS = {
    *(
        "f",
        "x",
        "xta",
        "add",
        "it",
        "tr",
        "th1",
        "th2",
        "tc1",
        "tc2",
        "tc3",
        "th3",
        "po",
        "pm",
        "li1",
        "s1",
        "s2",
        "mt1",
        "mt2",
        "d",
        "vp",
        "fv",
        "ms1",
        "cl",
        "ms2",
        "lit",
        "sd1",
        "qs",
        "qd",
        "ref",
        "esb",
        "esbe",
        "periph",
        "sd2",
        "qr",
        "qa",
        "ili1",
        "ili2",
    )
}
# PTXprint's record of where the final run set a margin note: its reference,
# height, depth, page, and top (in scaled points from the foot of the page,
# negative for a note an overfull margin pushes off the page).
MARGIN_NOTE = re.compile(
    r"\\@marginnote\{([^}]*)\}(?:\{[^}]*\}){5}\{([\d.]+)pt\}\{([\d.]+)pt\}"
    r"(?:\{[^}]*\}){2}\{(\d+)\}\{\d+\}\{(-?\d+)\}"
)


def processed_markers(markers: Mapping[str, int]) -> dict[str, int]:
    # Nested italic/quotation markers may be flattened by the module parser.
    result: dict[str, int] = {}
    for k, v in markers.items():
        k = k.lstrip("+")
        if k.rstrip("*") in KEPT_MARKERS:
            result[k] = result.get(k, 0) + v
    return result


def check_processed(project: Path, base: Path, ids: list[str]) -> None:
    records = []
    texfiles = list((project / PROCESSED_DIR).glob("*_ptxp.tex"))
    require(len(texfiles) == 1, "Missing typesetting driver")
    tex = texfiles[0].read_text(encoding="utf-8")
    require("%\\OmitCallerInNote{f}" in tex, "Footnote callers unexpectedly suppressed")
    require("\\AutoCallers{f}{1,2," in tex, "Footnote callers not numbered")
    for code in ids:
        source = project_usfm(project, code).read_text(encoding="utf-8")
        processed = processed_usfm(project, code)
        require(processed.exists(), f"PTXprint omitted {code}")
        output = processed.read_text(encoding="utf-8")
        before, after = inventory(source), inventory(output)
        require(
            before["chapters"] == after["chapters"],
            f"PTXprint changed chapter/verse labels: {code}",
        )
        content = canonical_text(output)
        require(
            canonical_text(source) == content,
            f"PTXprint changed printable content: {code}",
        )
        markers = processed_markers(after["markers"])
        require(
            processed_markers(before["markers"]) == markers,
            f"PTXprint changed notes, styles or tables: {code}",
        )
        require("\ue000" not in output, f"Unrestored pipe sentinel: {code}")
        records.append(
            {
                "id": code,
                "content_sha256": sha256(content.encode()),
                "chapters": after["chapters"],
                "preserved_markers": markers,
            }
        )
    write_json(base / "processed-integrity.json", records)


def numbered(page: str, entries: Sequence[tuple[str, str, str]]) -> bool:
    """Whether a contents page, read as one string of its letters and
    figures, gives its entries their page numbers: as one block of numbers
    after the titles, which is how a full page's columns read, or each
    number after its title and abbreviation, which is how a short page reads."""
    if page.endswith("".join(number for _, _, number in entries)):
        return True
    at = 0
    for title, abbreviation, number in entries:
        found = page.find(title, at)
        expected = title + abbreviation + number
        if found < 0 or not page.startswith(expected, found):
            return False
        at = found + len(expected)
    return True


def check_contents(
    contents: Sequence[str], toc: Sequence[tuple[str, str, str, str]]
) -> None:
    """Refuse contents pages, each read as one string of its letters and
    figures, unless they list the units in order, each page giving its own
    units their page numbers. A contents page reads by its columns: the
    titles with the abbreviations, then the page numbers. A title is sought
    after the one before it on its page, since one title may be part of
    another's ("Introduction" of "Editor's Introduction")."""
    listed = at = 0
    entries: list[tuple[str, str, str]] = []
    for code, title, abbreviation, number in toc:
        found = contents[listed].find(title, at) if listed < len(contents) else -1
        if found < 0 and listed < len(contents):
            require(
                entries and numbered(contents[listed], entries),
                f"Contents page numbers wrong in PDF before: {code}",
            )
            listed, entries = listed + 1, []
            found = contents[listed].find(title) if listed < len(contents) else -1
        require(found >= 0, f"Contents entry missing in PDF: {code}")
        at = found + len(title)
        entries.append((title, abbreviation, number))
    require(
        numbered(contents[listed], entries),
        "Contents page numbers wrong in PDF on the last page of the contents",
    )


def printed_key(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum()
    )


def check_colophon_order(source: str, printed: str) -> None:
    """A terminal sidebar must follow the completed final scripture verse."""
    if "\\cat colophon\\cat*" not in source:
        return
    doc = usj.parse(source)
    colophons = [b for b in doc["content"] if b.get("category") == "colophon"]
    last = next(reversed(scripture.verses(doc).values()))
    tail = printed_key(" ".join(last.text.split()[-12:]))
    words = printed_key(printed)
    for colophon in colophons:
        notice = printed_key(usj.text_of(colophon["content"]))
        at = words.find(notice)
        require(
            at >= 0 and words.rfind(tail, 0, at) >= 0,
            "Colophon missing or printed before scripture ends",
        )


def check_boundaries(
    base: Path,
    project: Path,
    ids: Sequence[str],
    pages: int,
    reading_text: str,
    sample: bool,
    witnesses: Sequence[Witnesses],
) -> None:
    tocfiles = list(base.rglob("*_ptxp.toc"))
    require(len(tocfiles) == 1, "Missing/ambiguous contents file")

    def readtoc(path: Path) -> list[tuple[str, str, str, str]]:
        main = (
            path.read_text(encoding="utf-8")
            .split("\\defTOC{main}{", 1)[1]
            .split("\n}", 1)[0]
        )
        return re.findall(
            r"\\doTOCline\{([^}]+)\}\{([^}]+)\}\{[^}]*\}\{([^}]*)\}\{(\d+)\}", main
        )

    # The units the contents list: each scripture book, and each division of
    # a front matter file.
    usfm: dict[str, str] = {}
    for code in ids:
        text = project_usfm(project, code).read_text(encoding="utf-8")
        if "\\periph " not in text:
            usfm[code] = text
            continue
        for division in usj.objects(usj.parse(text)["content"]):
            if division["type"] == "periph":
                blocks = usj.objects(division["content"])
                usfm[division["id"]] = usj.serialize(usj.document(blocks))
    toc = readtoc(tocfiles[0])
    require(
        [r[0] for r in toc] == list(usfm),
        "PDF contents omitted, duplicated or reordered units",
    )
    # Both files come from the final TeX run: PTXprint copies the raw TOC to _org.toc and
    # regenerates .toc from it. Convergence between runs is checked below, where the
    # printed contents page numbers must match these final pages.
    require(
        toc == readtoc(tocfiles[0].with_name(tocfiles[0].stem + "_org.toc")),
        "PTXprint's regenerated contents differ from the final TeX run",
    )
    page_text = reading_text.split("\f")

    # The basic front matter template restarts printed numbering at the
    # contents. Its TOC numbers therefore differ from physical PDF pages.
    first_heading = heading(next(iter(usfm.values())))
    first_physical = present(
        next(
            (
                i + 1
                for i in range(3, pages)
                if printed_key(canonical_text(first_heading))
                in printed_key(page_text[i])
            ),
            None,
        ),
        "First unit heading missing from PDF",
    )
    page_offset = first_physical - int(toc[0][3])
    require(page_offset >= 3, "Front matter page offset is invalid")
    abbreviations = project_settings(project).getboolean(
        "document", "usetoc3", fallback=False
    )
    check_contents(
        [printed_key(page) for page in page_text[2 : first_physical - 1]],
        [
            (
                code,
                printed_key(title),
                printed_key(abbreviation) if abbreviations else "",
                number,
            )
            for code, title, abbreviation, number in toc
        ],
    )
    # The physical pages each unit spans, from its heading's to the one
    # before the next unit's.
    spans = {
        code: (
            int(printed_page) + page_offset,
            int(toc[index + 1][3]) + page_offset - 1 if index + 1 < len(toc) else pages,
        )
        for index, (code, _, _, printed_page) in enumerate(toc)
    }
    previous = 0
    for code, title, abbreviation, printed_page in toc:
        page, end = spans[code]
        require(previous < page <= pages, f"Invalid boundary page: {code} {page}")
        previous = page
        # PTXprint writes an empty cell for a unit without \toc3; TeX in the
        # cell would not read as the letters it prints.
        require(
            not abbreviations or (abbreviation and not abbreviation.startswith("\\")),
            f"Unit without \\toc3: {code}",
        )
        words = heading(usfm[code])
        require(words, f"Missing heading: {code}")
        require(
            printed_key(canonical_text(words)) in printed_key(page_text[page - 1]),
            f"Book heading not on advertised PDF page: {code} {page}",
        )
        check_colophon_order(usfm[code], " ".join(page_text[page - 1 : end]))
    write_json(
        base / "book-boundaries.json",
        [
            {"id": b, "title": t, "page": int(p) + page_offset, "printed_page": int(p)}
            for b, t, _, p in toc
        ],
    )

    for witness in witnesses:
        code = witness["id"]
        if code in peripherals.UNITS:
            code = peripherals.UNITS[code].periph
        if code not in spans or (
            "chapter" in witness
            and witness["chapter"] not in inventory(usfm[code])["chapters"]
        ):
            # The sample deliberately selects only representative units and chapters.
            require(sample, f"Special-content witness not checked: {witness}")
            continue
        start, end = spans[code]
        require(
            printed_key(witness["phrase"])
            in printed_key("".join(page_text[start - 1 : end])),
            f"Special-content witness absent from rendered {code}: {witness['phrase']}",
        )


# A citation as a source writes it, and not as the edition prints it: a name,
# a chapter in Arabic or Roman, and a stop before the verse, as "Rom. 4. 7",
# "Mat. 18.28", "Gen. xlvii. 31", "2Ki. 19. 18". A number that a supplied
# passage is printed under has no name before it. A line may break at any of
# its spaces. Chapters have at most three digits and verses start at one:
# a date with a note caller ("February 2021.4") or a version ("Attribution
# 4.0") is not a citation.
FOREIGN_CITATION = re.compile(
    r"(?<![\w.])(?:[1-4]\.?\s?)?[A-Z][a-z]+\.?\s"
    r"(?:[1-9]\d{0,2}|[ivxlc]+)\.\s?[1-9]\d*"
)


def check_citations(reading_text: str) -> None:
    """Every citation on the pages is in the edition's way of writing.

    Preparation reads each citation where its source is read, and refuses
    what it can't read. This looks at the pages themselves, so that words
    which no reading met, as those of a unit added later, don't cite in a
    way of their own unnoticed.
    """
    found = sorted({match[0] for match in FOREIGN_CITATION.finditer(reading_text)})
    require(not found, f"Citation not written as the edition cites: {found[:12]}")


def stream_text(
    pdf: str | Path, top: float, bottom: float, inner: float | None = None
) -> str:
    """Each page's text in stream order within body and inner-note columns.
    Form feeds part the pages; blank lines part the extracted text blocks,
    so a heading cannot become the book name of the paragraph below it."""
    pages: list[str] = []
    # A whole Bible is a million words: drop each page's once they are read.
    for _, page in ET.iterparse(
        io.StringIO(capture("pdftotext", "-bbox-layout", pdf, "-"))
    ):
        if page.tag != XHTML + "page":
            continue
        body, notes = [], []
        for block in page.iter(XHTML + "block"):
            body_words: list[str] = []
            note_words: list[str] = []
            for word in block.iter(XHTML + "word"):
                # The running head and the folio stand in the margins.
                if (
                    not top
                    <= float(word.attrib["yMin"])
                    <= float(page.attrib["height"]) - bottom
                ):
                    continue
                # Side notes can interrupt a sentence in PDF stream order. Keep
                # each column together, allowing 3 pt for optical protrusion at
                # the body edge (less than the 5.5 mm gap to the notes).
                marginal = inner is not None and (
                    float(word.attrib["xMax"]) < inner - 3
                    if len(pages) % 2 == 0
                    else float(word.attrib["xMin"])
                    > float(page.attrib["width"]) - inner + 3
                )
                assert word.text is not None
                (note_words if marginal else body_words).append(word.text)
            if body_words:
                body.append(" ".join(body_words))
            if note_words:
                notes.append(" ".join(note_words))
        pages.append("\n\n".join([*body, *notes]))
        page.clear()
    return "\f".join(pages)


def margin_overflow(base: Path, top: float, bottom: float) -> list[str]:
    """The margin notes that are not in the text block, below the note placed
    above it: PTXprint has nowhere else to put the notes of an overfull
    margin, and lets them overlap at its foot. The notes are taken in the
    order they stand on the page, since PTXprint may set a note of a
    chapter's opening paragraph above an earlier verse's. top and bottom are
    the block's edges, in TeX points from the foot of the page."""
    files = list(base.rglob("*_ptxp.marginnotes"))
    require(len(files) == 1, "Missing/ambiguous margin note positions")
    records = files[0].read_text(encoding="utf-8")
    notes = MARGIN_NOTE.findall(records)
    # A record in a form this can't read would otherwise go unchecked.
    require(
        len(notes) == records.count("\\@marginnote"),
        "Could not read every margin note position",
    )
    pages: dict[str, list[tuple[float, float, str]]] = {}
    for ref, height, depth, page, y in notes:
        note_top = int(y) / 65536
        note_bottom = note_top - float(height) - float(depth)
        pages.setdefault(page, []).append((note_top, note_bottom, ref))
    overflow = []
    for page, placed in pages.items():
        ceiling = top
        for note_top, note_bottom, ref in sorted(placed, reverse=True):
            # A twentieth of a point allows for rounding.
            if not (note_top <= ceiling + 0.05 and note_bottom >= bottom - 0.05):
                overflow.append(f"page {page} {ref}")
            ceiling = note_bottom
    return overflow


def check_added_words_roman(
    pdf: Path, reading_text: str, project: Path, ids: Sequence[str], sample: bool
) -> None:
    # Malachias 4:2 has "\\add shall be\\add* in his wings". Check the added
    # words against their roman neighbours; "healing" may break as "heal- / ing".
    # Like the render witnesses, only the sample may leave the verse out.
    malachias = project_usfm(project, "MAL")
    if (
        "MAL" not in ids
        or "4" not in inventory(malachias.read_text(encoding="utf-8"))["chapters"]
    ):
        require(sample, "Added-word witness Malachias 4:2 is not in the build")
        return
    words = ["shall", "be", "in", "his", "wings"]
    pages = [
        number
        for number, page in enumerate(reading_text.split("\f"), 1)
        if " ".join(words) in plain(page)
    ]
    require(
        len(pages) == 1, f"Added-word witness Malachias 4:2 not found once: {pages}"
    )
    root = ET.fromstring(
        capture(
            "pdftohtml", "-xml", "-i", "-stdout", "-f", pages[0], "-l", pages[0], pdf
        )
    )
    families = {f.get("id"): f.get("family") for f in root.iter("fontspec")}
    runs = [
        (word, families[t.get("font")])
        for t in root.iter("text")
        for word in "".join(t.itertext()).split()
    ]
    for i in range(len(runs) - len(words) + 1):
        if [w.strip(":,") for w, _ in runs[i : i + len(words)]] == words:
            require(
                len({f for _, f in runs[i : i + len(words)]}) == 1,
                "Added words are not set in the surrounding roman font",
            )
            return
    raise CheckFailed("Added-word witness not found in PDF text runs")


def check_publication(text: str, settings: configparser.ConfigParser) -> None:
    """The publication data page carries the edition's copyright and license
    as config/layout.ini gives them, and nothing of the layout's own."""
    publication = plain(text.split("\f")[1])
    require(
        all(
            plain(settings["project"][key]) in publication
            for key in ("copyright", "license")
        ),
        "Publication data page omitted the edition license notice",
    )
    require(
        "Berean Standard Bible" not in publication,
        "Inherited BSB publication text remains",
    )


def check_fonts(fonts: str, family: str) -> None:
    """Require the edition's embedded faces and refuse substitutes."""
    rows = fonts.splitlines()[2:]
    require(
        rows
        and all(
            re.search(r"\s+yes\s+(?:yes|no)\s+(?:yes|no)\s+\d+\s+\d+\s*$", r)
            for r in rows
        ),
        "Unembedded PDF font",
    )
    text_fonts = (
        family,
        typeface.postscript_family(typeface.greek_face()),
        "Ezra",
        typeface.postscript_name(typeface.chapter_face()),
    )
    missing = [f for f in text_fonts if f not in fonts]
    require(not missing, f"Expected text/quotation fonts missing: {missing}")
    # Every embedded face must belong to an edition font; merely finding
    # the text family in verse labels would not catch substitution in the body text.
    allowed_fonts = (*text_fonts, "SourceCodePro")
    require(
        all(any(f in row.split()[0] for f in allowed_fonts) for row in rows),
        "Unexpected font family in PDF; inspect font selections",
    )


def inspect_pdf(
    pdf: Path,
    base: Path,
    project: Path,
    ids: Sequence[str],
    sample: bool,
    witnesses: Sequence[Witnesses],
) -> int:
    """Check the typeset PDF against the project; returns its page count."""
    with (base / "qpdf.log").open("w", encoding="utf-8") as log:
        run("qpdf", "--check", pdf, stdout=log, stderr=subprocess.STDOUT)
    # Every page's boxes, not just the first MediaBox: a last page past the
    # end stops at the end.
    info = capture("pdfinfo", "-f", 1, "-l", 10**6, "-box", pdf)
    (base / "pdfinfo.txt").write_text(info, encoding="utf-8")
    page_count = re.search(r"Pages:\s+(\d+)", info)
    assert page_count is not None
    pages = int(page_count[1])
    sizes = re.findall(r"(?:Page\s+\d+ size:|Page size:)\s+([\d.]+) x ([\d.]+)", info)
    require(len(sizes) == pages, "Could not inspect every PDF page")
    require(
        all(
            abs(float(w) - 176 * POINTS_PER_MM) < 0.1
            and abs(float(h) - 250 * POINTS_PER_MM) < 0.1
            for w, h in sizes
        ),
        "Non-B5 page found",
    )
    fonts = capture("pdffonts", pdf)
    (base / "fonts.txt").write_text(fonts, encoding="utf-8")
    settings = project_settings(project)
    check_fonts(fonts, text_font(settings))
    text = capture("pdftotext", "-layout", pdf, "-")
    (base / "text.txt").write_text(text, encoding="utf-8")
    require(not re.search(r"['\"`]", text), "Straight quote in the rendered PDF text")
    require(
        not re.search(r"[\ue000-\uf8ff]", text),
        "Private-use glyph code in extracted PDF text",
    )
    check_publication(text, settings)
    height = float(sizes[0][1])
    top, bottom = (
        settings.getfloat("paper", key) * POINTS_PER_MM
        for key in ("topmargin", "bottommargin")
    )
    inner = (
        settings.getfloat("paper", "margins") + settings.getfloat("paper", "gutter")
    ) * POINTS_PER_MM
    reading_text = stream_text(pdf, top, bottom, inner)
    (base / "reading.txt").write_text(reading_text, encoding="utf-8")
    check_added_words_roman(pdf, reading_text, project, ids, sample)
    check_citations(reading_text)
    overflow = margin_overflow(base, (height - top) * TEX_POINTS, bottom * TEX_POINTS)
    # An overrun page pushes many notes off at once: name every such page,
    # for edition/margin.json to relieve, with the first note that does not fit.
    overrun: dict[str, str] = {}
    for entry in overflow:
        overrun.setdefault(entry.rsplit(" ", 1)[0], entry)
    require(not overflow, f"Margin notes do not fit: {list(overrun.values())}")
    logs = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in base.rglob("*.log")
    )
    require(
        not re.search(
            r"Missing character:|There is no .* in font|! (?:Emergency stop|Fatal error|TeX capacity|Undefined control)",
            logs,
        ),
        "Missing glyph or TeX error; inspect logs",
    )
    check_boundaries(base, project, ids, pages, reading_text, sample, witnesses)
    return pages
