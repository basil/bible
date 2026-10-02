"""Acceptance checks on PTXprint's work: first its processed copy of each
unit's text, then the rendered PDF (page size, fonts, contents, the way it
cites, and the phrases in edition/witnesses.json)."""

from __future__ import annotations

import io
import re
import subprocess
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypedDict

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
from bible.toolchain import capture as capture
from bible.toolchain import run
from bible.usfm import canonical_text, heading, inventory


class PdfReport(TypedDict):
    pages: int
    text_sha256: str


POINTS_PER_MM = 72 / 25.4
# TeX points (72.27 to the inch) in a PDF point.
TEX_POINTS = 72.27 / 72
XHTML = "{http://www.w3.org/1999/xhtml}"
# Notes, character styles and table cells, which PTXprint must keep.
KEPT_MARKERS = {
    *("f", "ef", "x", "xta", "add", "it", "tr", "th1", "th2", "tc1", "tc2", "vp")
}
# PTXprint's record of where the final run set a margin note: its reference,
# height, depth, page, and top (in scaled points from the foot of the page).
MARGIN_NOTE = re.compile(
    r"\\@marginnote\{([^}]*)\}(?:\{[^}]*\}){5}\{([\d.]+)pt\}\{([\d.]+)pt\}"
    r"(?:\{[^}]*\}){2}\{(\d+)\}\{\d+\}\{(\d+)\}"
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

    def readtoc(path: Path) -> list[tuple[str, str, str]]:
        main = (
            path.read_text(encoding="utf-8")
            .split("\\defTOC{main}{", 1)[1]
            .split("\n}", 1)[0]
        )
        return re.findall(
            r"\\doTOCline\{([^}]+)\}\{([^}]+)\}\{[^}]*\}\{[^}]*\}\{(\d+)\}", main
        )

    toc = readtoc(tocfiles[0])
    require(
        [r[0] for r in toc] == ids,
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

    def key(s: str) -> str:
        return "".join(
            c for c in unicodedata.normalize("NFKC", s).casefold() if c.isalnum()
        )

    usfm = {
        code: project_usfm(project, code).read_text(encoding="utf-8") for code in ids
    }
    # The basic front matter template restarts printed numbering at the
    # contents. Its TOC numbers therefore differ from physical PDF pages.
    first_heading = heading(usfm[ids[0]])
    first_physical = present(
        next(
            (
                i + 1
                for i in range(3, pages)
                if key(canonical_text(first_heading)) in key(page_text[i])
            ),
            None,
        ),
        "First unit heading missing from PDF",
    )
    page_offset = first_physical - int(toc[0][2])
    require(page_offset >= 3, "Front matter page offset is invalid")
    contents = key("".join(page_text[2 : first_physical - 1]))
    previous = 0
    for code, title, printed_page in toc:
        page = int(printed_page) + page_offset
        require(previous < page <= pages, f"Invalid boundary page: {code} {page}")
        previous = page
        require(
            key(title) + printed_page in contents,
            f"Contents entry missing/wrong printed page in PDF: {code}",
        )
        words = heading(usfm[code])
        require(words, f"Missing heading: {code}")
        require(
            key(canonical_text(words)) in key(page_text[page - 1]),
            f"Book heading not on advertised PDF page: {code} {page}",
        )
    write_json(
        base / "book-boundaries.json",
        [
            {"id": b, "title": t, "page": int(p) + page_offset, "printed_page": int(p)}
            for b, t, p in toc
        ],
    )
    by_code = {b: (i, int(p) + page_offset) for i, (b, t, p) in enumerate(toc)}

    for witness in witnesses:
        code = witness["id"]
        if code not in by_code or (
            "chapter" in witness
            and witness["chapter"] not in inventory(usfm[code])["chapters"]
        ):
            # The sample deliberately selects only representative units and chapters.
            require(sample, f"Special-content witness not checked: {witness}")
            continue
        index, start = by_code[code]
        end = (
            int(toc[index + 1][2]) + page_offset - 1 if index + 1 < len(toc) else pages
        )
        require(
            key(witness["phrase"]) in key("".join(page_text[start - 1 : end])),
            f"Special-content witness absent from rendered {code}: {witness['phrase']}",
        )


# A citation as a source writes it, and not as the edition prints it: a name,
# a chapter in Arabic or Roman, and a stop before the verse, as "Rom. 4. 7",
# "Mat. 18.28", "Gen. xlvii. 31", "2Ki. 19. 18". A number that a supplied
# passage is printed under has no name before it. A line may break at any of
# its spaces.
FOREIGN_CITATION = re.compile(
    r"(?<![\w.])(?:[1-4]\.?\s?)?[A-Z][a-z]+\.?\s(?:\d+|[ivxlc]+)\.\s?\d+"
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


def check_margin_notes(base: Path, top: float, bottom: float) -> None:
    """Every margin note is in the text block, below the note before it:
    PTXprint has nowhere else to put the notes of an overfull margin. top and
    bottom are the block's edges, in TeX points from the foot of the page."""
    files = list(base.rglob("*_ptxp.marginnotes"))
    require(len(files) == 1, "Missing/ambiguous margin note positions")
    records = files[0].read_text(encoding="utf-8")
    notes = MARGIN_NOTE.findall(records)
    # A record in a form this can't read would otherwise go unchecked.
    require(
        len(notes) == records.count("\\@marginnote"),
        "Could not read every margin note position",
    )
    last_page: str | None = None
    ceiling = top
    for ref, height, depth, page, y in notes:
        if page != last_page:
            last_page, ceiling = page, top
        note_top = int(y) / 65536
        note_bottom = note_top - float(height) - float(depth)
        # A twentieth of a point allows for rounding.
        require(
            note_top <= ceiling + 0.05 and note_bottom >= bottom - 0.05,
            f"Margin note does not fit: page {page} {ref}",
        )
        ceiling = note_bottom


def check_added_words_roman(
    pdf: str | Path, reading_text: str, project: Path, ids: Sequence[str], sample: bool
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
        if " ".join(words) in " ".join(page.split())
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


def check_publication(text: str) -> None:
    publication = " ".join(text.split("\f")[1].split())
    require(
        "Copyright © 2026 Basil Crow" in publication
        and "Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International (CC BY-NC-ND 4.0)"
        in publication
        and "https://creativecommons.org/licenses/by-nc-nd/4.0/" in publication,
        "Publication data page omitted the edition license notice",
    )
    require(
        "Berean Standard Bible" not in publication,
        "Inherited BSB publication text remains",
    )


def inspect_pdf(
    pdf: Path,
    base: Path,
    project: Path,
    ids: Sequence[str],
    sample: bool,
    witnesses: Sequence[Witnesses],
) -> PdfReport:
    with (base / "qpdf.log").open("w", encoding="utf-8") as log:
        run("qpdf", "--check", pdf, stdout=log, stderr=subprocess.STDOUT)
    info = capture("pdfinfo", "-box", pdf)
    (base / "pdfinfo.txt").write_text(info, encoding="utf-8")
    page_count = re.search(r"Pages:\s+(\d+)", info)
    assert page_count is not None
    pages = int(page_count[1])
    # Check every page, not just the first MediaBox.
    boxes = capture("pdfinfo", "-f", 1, "-l", pages, "-box", pdf)
    sizes = re.findall(r"(?:Page\s+\d+ size:|Page size:)\s+([\d.]+) x ([\d.]+)", boxes)
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
    rows = fonts.splitlines()[2:]
    require(
        rows
        and all(
            re.search(r"\s+yes\s+(?:yes|no)\s+(?:yes|no)\s+\d+\s+\d+\s*$", r)
            for r in rows
        ),
        "Unembedded PDF font",
    )
    settings = project_settings(project)
    family = text_font(settings)
    text_fonts = (family, "GFSDidot", "Ezra")
    require(
        all(f in fonts for f in text_fonts),
        "Expected text/quotation fonts missing",
    )
    # Every embedded face must belong to an edition font; merely finding
    # the text family in verse labels would not catch substitution in the body text.
    allowed_fonts = (*text_fonts, "SourceCodePro")
    require(
        all(any(f in row.split()[0] for f in allowed_fonts) for row in rows),
        "Unexpected font family in PDF; inspect font selections",
    )
    text = capture("pdftotext", "-layout", pdf, "-")
    (base / "text.txt").write_text(text, encoding="utf-8")
    require(not re.search(r"['\"`]", text), "Straight quote in the rendered PDF text")
    require(
        not re.search(r"[\ue000-\uf8ff]", text),
        "Private-use glyph code in extracted PDF text",
    )
    check_publication(text)
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
    check_margin_notes(base, (height - top) * TEX_POINTS, bottom * TEX_POINTS)
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
    return {
        "pages": pages,
        "text_sha256": sha256(text.encode()),
    }
