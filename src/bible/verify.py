"""Acceptance checks on PTXprint's work: first its processed copy of each
unit's text, then the rendered PDF (page size, fonts, contents, and the
phrases in edition/witnesses.json)."""

import re
import subprocess
import unicodedata
import xml.etree.ElementTree as ET

from bible import paths
from bible.checks import CheckFailed, require
from bible.files import read_json, sha256, write_json
from bible.project import PROCESSED_DIR, processed_usfm, project_usfm
from bible.toolchain import capture, run
from bible.usfm import (
    HEADING_MARKERS,
    NOTE_AND_STYLE_MARKERS,
    canonical_text,
    inventory,
    marker_lines,
)


def processed_markers(markers):
    # Nested italic/quotation markers may be flattened by the module parser.
    result = {}
    for k, v in markers.items():
        k = k.lstrip("+")
        if k.rstrip("*") in NOTE_AND_STYLE_MARKERS:
            result[k] = result.get(k, 0) + v
    return result


def check_processed(project, base, ids):
    records = []
    texfiles = list((project / PROCESSED_DIR).glob("*_ptxp.tex"))
    require(len(texfiles) == 1, "Missing typesetting driver")
    tex = texfiles[0].read_text(encoding="utf-8")
    require("%\\OmitCallerInNote{f}" in tex, "Footnote callers unexpectedly suppressed")
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


def check_boundaries(base, project, ids, text, pages, reading_text, sample):
    tocfiles = list(base.rglob("*_ptxp.toc"))
    require(len(tocfiles) == 1, "Missing/ambiguous contents file")

    def readtoc(path):
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
    page_text = text.split("\f")

    def key(s):
        return "".join(
            c for c in unicodedata.normalize("NFKC", s).casefold() if c.isalnum()
        )

    usfm = {
        code: project_usfm(project, code).read_text(encoding="utf-8") for code in ids
    }
    # The contents follows the title page and precedes the first unit.
    contents = key("".join(page_text[1 : int(toc[0][2]) - 1]))
    previous = 0
    for code, title, page in toc:
        page = int(page)
        require(previous < page <= pages, f"Invalid boundary page: {code} {page}")
        previous = page
        require(
            key(title) + str(page) in contents,
            f"Contents entry missing/wrong page in PDF: {code}",
        )
        heading = " ".join(
            value for _, value in marker_lines(usfm[code], HEADING_MARKERS)
        )
        require(heading, f"Missing heading: {code}")
        require(
            key(canonical_text(heading)) in key(page_text[page - 1]),
            f"Book heading not on advertised PDF page: {code} {page}",
        )
    write_json(
        base / "book-boundaries.json",
        [{"id": b, "title": t, "page": int(p)} for b, t, p in toc],
    )
    reading_pages = reading_text.split("\f")
    reading_pages_without_headers = []
    for page_number, page in enumerate(reading_pages, 1):
        lines = page.splitlines(keepends=True)
        # A running head carries the page number as one of its words.
        if lines and str(page_number) in lines[0].split():
            lines = lines[1:]
        reading_pages_without_headers.append("".join(lines))
    by_code = {b: (i, int(p)) for i, (b, t, p) in enumerate(toc)}
    for witness in read_json(paths.EDITION_DIR / "witnesses.json"):
        code = witness["id"]
        if code not in by_code or (
            "chapter" in witness
            and witness["chapter"] not in inventory(usfm[code])["chapters"]
        ):
            # The sample deliberately selects only representative units and chapters.
            require(sample, f"Special-content witness not checked: {witness}")
            continue
        index, start = by_code[code]
        end = int(toc[index + 1][2]) - 1 if index + 1 < len(toc) else pages
        rendered = key("".join(reading_pages[start - 1 : end]))
        rendered_without_headers = key(
            "".join(reading_pages_without_headers[start - 1 : end])
        )
        require(
            key(witness["phrase"]) in rendered
            or key(witness["phrase"]) in rendered_without_headers,
            f"Special-content witness absent from rendered {code}: {witness['phrase']}",
        )


def check_added_words_roman(pdf, reading_text, project, ids, sample):
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


def inspect_pdf(pdf, base, project, ids, sample):
    with (base / "qpdf.log").open("w", encoding="utf-8") as log:
        run("qpdf", "--check", pdf, stdout=log, stderr=subprocess.STDOUT)
    info = capture("pdfinfo", "-box", pdf)
    (base / "pdfinfo.txt").write_text(info, encoding="utf-8")
    pages = int(re.search(r"Pages:\s+(\d+)", info)[1])
    # Check every page, not just the first MediaBox.
    boxes = capture("pdfinfo", "-f", 1, "-l", pages, "-box", pdf)
    sizes = re.findall(r"(?:Page\s+\d+ size:|Page size:)\s+([\d.]+) x ([\d.]+)", boxes)
    require(len(sizes) == pages, "Could not inspect every PDF page")
    require(
        all(
            abs(float(w) - 419.528) < 0.1 and abs(float(h) - 595.276) < 0.1
            for w, h in sizes
        ),
        "Non-A5 page found",
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
    require(
        all(f in fonts for f in ("Utopia", "Erewhon", "GFSDidot", "Ezra")),
        "Expected text/verse-number/quotation fonts missing",
    )
    text = capture("pdftotext", "-layout", pdf, "-")
    (base / "text.txt").write_text(text, encoding="utf-8")
    require(not re.search(r"['\"`]", text), "Straight quote in the rendered PDF text")
    # PTXprint emits columns in reading order. Protruding edge glyphs can make
    # pdftotext's geometric heuristics merge adjacent columns, so use stream
    # order for wording witnesses; keep the layout extraction above for pages.
    reading_text = capture("pdftotext", "-raw", pdf, "-")
    (base / "reading.txt").write_text(reading_text, encoding="utf-8")
    check_added_words_roman(pdf, reading_text, project, ids, sample)
    require(
        "Berean Standard Bible" not in text and "CC BY-NC-ND" not in text,
        "Inherited BSB publication text remains",
    )
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
    check_boundaries(base, project, ids, text, pages, reading_text, sample)
    return {
        "pages": pages,
        "text_sha256": sha256(text.encode()),
    }
