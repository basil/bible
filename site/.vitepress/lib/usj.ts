// Presentation only: words and note attribution come from the prepared USJ.
export type Node = {
  type: string;
  marker?: string;
  number?: string;
  pubnumber?: string;
  loc?: string;
  id?: string;
  alt?: string;
  category?: string;
  content?: (string | Node)[];
};
export type Document = { content: Node[] };
export const escape = (text: string) =>
  text.replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ]!,
  );
// Match the default theme's heading permalinks without adding to the words.
export const permalink = (id: string, title: string) =>
  `<a class="header-anchor" href="#${escape(id)}" aria-label="${escape(`Permalink to “${title}”`)}"></a>`;
// A heading anchored by its id, in the class its marker gives it.
export const headed = (
  tag: string,
  id: string,
  html: string,
  title: string,
  classes = "",
) =>
  `<${tag}${classes ? ` class="${classes}"` : ""} id="${escape(id)}" tabindex="-1">${html}${permalink(id, title)}</${tag}>`;
// A page's title.
export const heading = (id: string, title: string) =>
  headed("h1", id, escape(title), title);
// The site's route to a chapter, by its book's code.
export const chapterPath = (book: string, chapter: string) =>
  `/read/${book.toLowerCase()}/${chapter}`;
// A reference to a chapter, or to a verse by its anchor.
function refURL(loc: string) {
  const match = /^(\w+) (\d+)(?::(\d+[a-z]?))?$/.exec(loc);
  if (!match) {
    throw new Error(`Unknown reference ${loc}`);
  }
  const [, book, chapter, verse] = match;
  return chapterPath(book!, chapter!) + (verse ? `#v${verse}` : "");
}
// A chapter's document opens with its book.
const blocksOf = (doc: Document): Node[] =>
  doc.content.flatMap((n) =>
    n.type === "periph"
      ? blocksOf({ content: n.content as Node[] })
      : n.type !== "book" && n.type !== "chapter"
        ? [n]
        : [],
  );
const CHAR_TAGS: Record<string, string> = {
  add: "span",
  sc: "span",
  it: "i",
  lik: "i",
  bd: "b",
  fv: "span",
  vp: "span",
  // Greek and Hebrew, tagged for their fonts as the typesetter has them.
  wg: "span",
  wh: "span",
  qs: "span",
};
const CHAR_ATTRIBUTES: Record<string, string> = {
  wg: ' lang="grc"',
  wh: ' lang="he"',
};
const NOTE_TAGS: Record<string, string> = {
  fr: "b",
  fq: "span",
  fqa: "i",
  ft: "span",
  fl: "span",
  xo: "b",
  xt: "span",
  xta: "span",
};
const CELL_TAGS: Record<string, string> = {
  th1: "th",
  th2: "th",
  th3: "th",
  tc1: "td",
  tc2: "td",
  tc3: "td",
};
const PARAGRAPH_TAGS: Record<string, string> = {
  // A unit of front matter's printed title, and the lines about it.
  mt1: "h1",
  mt2: "p",
  p: "p",
  m: "p",
  mi: "p",
  nb: "p",
  po: "p",
  pm: "blockquote",
  q1: "p",
  q2: "p",
  // A standalone Pause and an acrostic heading.
  qr: "p",
  qa: "p",
  qc: "p",
  d: "p",
  qd: "p",
  cl: "p",
  lit: "p",
  s1: "h2",
  s2: "h3",
  s3: "h4",
  ms1: "h2",
  ms2: "h3",
  ip: "p",
  im: "p",
  imi: "p",
  iex: "p",
  li1: "li",
  is1: "h2",
  is2: "h3",
};
const LIST_ITEMS = new Set(["li1"]);
// The blocks in the runs they render in: list entries together, and every
// other block alone.
function runs(nodes: Node[]) {
  const result: Node[][] = [];
  for (const n of nodes) {
    const last = result.at(-1);
    if (last && LIST_ITEMS.has(n.marker!) && LIST_ITEMS.has(last[0]!.marker!)) {
      last.push(n);
    } else {
      result.push([n]);
    }
  }
  return result;
}
// A zero-width space stands for a number that a chapter or verse doesn't print.
const HIDDEN = "\u200b";
// The words of a run of blocks as HTML, with the notes among them numbered
// from one and gathered for a list below, and the verses met in order.
// The page's title has the anchor its page kind gives it: the mt1 that
// opens a unit of front matter prints it, and no section heading takes it.
function renderer(titleAnchor = "") {
  const notes: string[] = [];
  const verses: string[] = [];
  // A heading's anchor from its words, unique on the page, so that the
  // outline lists it: apart from the page title's, too.
  const anchors = new Set<string>([titleAnchor]);
  function anchor(words: string) {
    const base =
      words
        .toLowerCase()
        .replace(/[^\p{L}\p{N}]+/gu, "-")
        .replace(/^-|-$/g, "") || "section";
    let id = base;
    for (let i = 1; anchors.has(id); i++) {
      id = `${base}-${i}`;
    }
    anchors.add(id);
    return id;
  }
  function inline(item: string | Node, inNote = false): string {
    if (typeof item === "string") {
      return escape(item);
    }
    const marker = item.marker || "";
    if (item.type === "verse") {
      if (inNote || !item.number) {
        throw new Error("Unexpected verse milestone");
      }
      verses.push(item.number);
      if (item.pubnumber === HIDDEN) {
        // An unnumbered verse keeps its anchor, for the links to it.
        return `<span class="verse" id="v${escape(item.number)}"></span>`;
      }
      return ` <sup class="verse" id="v${escape(item.number)}"><a href="#v${escape(item.number)}">${escape(item.pubnumber || item.number)}</a></sup> `;
    }
    if (item.type === "note") {
      if (inNote || !["f", "x"].includes(marker)) {
        throw new Error(`Unexpected note ${marker}`);
      }
      // A note holds no note, so its number is fixed before its content.
      const k = notes.length + 1;
      const note = (item.content || []).map((n) => inline(n, true)).join("");
      notes.push(
        `<li id="n${k}">${note} <a href="#caller${k}" aria-label="Back to note ${k}">↩</a></li>`,
      );
      return `<sup class="note" id="caller${k}"><a href="#n${k}" aria-label="Note ${k}">[${k}]</a></sup>`;
    }
    const body = (item.content || []).map((n) => inline(n, inNote)).join("");
    if (item.type === "ref") {
      return `<a href="${escape(refURL(item.loc || ""))}">${body}</a>`;
    }
    if (item.type === "char") {
      if (Object.hasOwn(NOTE_TAGS, marker) && !inNote) {
        throw new Error(`Note field outside note: ${marker}`);
      }
      const tag = NOTE_TAGS[marker] ?? CHAR_TAGS[marker];
      if (!tag) {
        throw new Error(`Unknown character marker ${marker}`);
      }
      if (marker === "xt") {
        // Vue drops whitespace-only fragments at an element's edges.
        // Move edge spaces outside the citation wrapper, keeping styles inside.
        const before = body.match(/^\s*/)?.[0] || "";
        const after = body.slice(before.length).match(/\s*$/)?.[0] || "";
        const cited = body.slice(before.length, body.length - after.length);
        return `${before}<${tag} class="${marker}">${cited}</${tag}>${after}`;
      }
      return `<${tag} class="${marker}"${CHAR_ATTRIBUTES[marker] ?? ""}>${body}</${tag}>`;
    }
    throw new Error(`Unknown inline node ${item.type}/${marker}`);
  }
  function cell(c: string | Node): string {
    if (typeof c === "string" || c.type !== "table:cell") {
      throw new Error("Unexpected row content");
    }
    const marker = c.marker || "";
    const tag = CELL_TAGS[marker];
    if (!tag) {
      throw new Error(`Unknown cell marker ${marker}`);
    }
    return `<${tag} class="${marker}">${(c.content || []).map((i) => inline(i)).join("")}</${tag}>`;
  }
  function row(r: string | Node): string {
    if (typeof r === "string" || r.type !== "table:row") {
      throw new Error("Unexpected table content");
    }
    return `<tr>${(r.content || []).map(cell).join("")}</tr>`;
  }
  function block(n: Node): string {
    if (n.type === "sidebar") {
      return `<aside class="${escape(n.category || "")}" aria-label="${n.category === "colophon" ? "Source colophon" : "Annotation"}">${blocks(n.content as Node[])}</aside>`;
    }
    if (n.type === "table") {
      // Vue's parser inserts no tbody; the browser's does, and they must agree.
      return `<table><tbody>\n${(n.content || []).map(row).join("\n")}\n</tbody></table>`;
    }
    if (n.type !== "para") {
      throw new Error(`Unknown block ${n.type}`);
    }
    const marker = n.marker!;
    if (marker === "b") {
      return '<div class="stanza" aria-hidden="true"></div>';
    }
    if (marker === "sd1" || marker === "sd2") {
      return `<hr class="${marker}">`;
    }
    const tag = PARAGRAPH_TAGS[marker];
    if (!tag) {
      throw new Error(`Unknown paragraph marker ${marker}`);
    }
    // A unit of front matter's printed title is its heading, and the
    // target of its search results; its sections are in the outline.
    const words = (items: (string | Node)[]): string =>
      items
        .map((c) =>
          typeof c === "string"
            ? c
            : c.type === "note"
              ? ""
              : words(c.content || []),
        )
        .join("");
    const html = (n.content || []).map((c) => inline(c)).join("");
    if (marker !== "mt1" && !/^h[2-4]$/.test(tag)) {
      return `<${tag} class="${marker}">${html}</${tag}>`;
    }
    const title = words(n.content || []);
    const id = marker === "mt1" ? titleAnchor : anchor(title);
    return id
      ? headed(tag, id, html, title, marker)
      : `<${tag} class="${marker}">${html}</${tag}>`;
  }
  // One of the runs: a list, or a block alone.
  const run = (nodes: Node[]) =>
    LIST_ITEMS.has(nodes[0]!.marker!)
      ? `<ul>${nodes.map(block).join("\n")}</ul>`
      : block(nodes[0]!);
  const blocks = (nodes: Node[]) => runs(nodes).map(run).join("\n");
  // The notes list, once every block that calls one has been rendered: one
  // list, under one anchor, however often the page asks for it.
  let noteHTML: string | undefined;
  const noteList = () =>
    (noteHTML ??= notes.length
      ? (() => {
          const id = anchor("Notes");
          return `${headed("h2", id, "Notes", "Notes")}<ol class="notes">${notes.join("\n")}</ol>`;
        })()
      : "");
  // Rendered prose, which holds no verses, with its notes below it.
  function prose(html: string, ...classes: string[]) {
    if (verses.length) {
      throw new Error("Verse milestone in prose");
    }
    return scripture(html + noteList(), ...classes);
  }
  return { blocks, run, noteList, prose, verses };
}
// A page's Markdown is compiled as a Vue template: v-pre keeps the words,
// which escape leaves free to hold "{{", from being read as expressions.
const scripture = (html: string, ...classes: string[]) =>
  `<div class="${["scripture", ...classes].join(" ")}" v-pre>${html}</div>`;
// An acrostic name stands alone; the number of the verse it opens is set
// beside the poetic line that follows it, as in print.
function numberedAfterAcrostics(blocks: Node[]): Node[] {
  const result = [...blocks];
  for (const [at, heading] of blocks.entries()) {
    if (heading.marker !== "qa") {
      continue;
    }
    const milestones = (heading.content || []).filter(
      (n): n is Node => typeof n !== "string" && n.type === "verse",
    );
    if (!milestones.length) {
      continue;
    }
    const line = blocks[at + 1];
    if (milestones.length !== 1 || line?.marker !== "q1") {
      throw new Error("Acrostic verse without its following poetic line");
    }
    result[at] = {
      ...heading,
      content: (heading.content || []).filter(
        (n) => typeof n === "string" || n.type !== "verse",
      ),
    };
    result[at + 1] = {
      ...line,
      content: [...milestones, ...(line.content || [])],
    };
  }
  return result;
}
// A titled chapter's heading stands for its number, and so is the page title.
export function renderChapter(doc: Document, titled = false) {
  const blocks = numberedAfterAcrostics(blocksOf(doc));
  const title = titled ? blocks.find((n) => n.marker === "cl") : undefined;
  const render = renderer("chapter");
  const html = render.blocks(blocks.filter((n) => n !== title));
  return { html: scripture(html + render.noteList()), verses: render.verses };
}
// An entry of the variants: the verse it is about, the King James Bible's
// number where it differs, and its lanes: the Greek of both texts and, where
// the English changes, the words of both Bibles. A lane's segments are the
// words both witnesses share, a gap where words in agreement are left out,
// a reading: the source's words (from) and the adopted text's (to), one of
// them missing where that witness has nothing there, or words both share
// that a correction of the English is about.
export type Reading = { from?: string; to?: string };
export type Segment = string | { gap: true } | { about: string } | Reading;
export type Lane = {
  from: string;
  to: string;
  language: "grc" | "en";
  // The accented forms as the apparatus quotes them, where they differ
  // from the printed texts'.
  apparatus?: true;
  segments: Segment[];
};
export type Variant = {
  chapter: string;
  verse: string;
  kjv?: string;
  lanes: Lane[];
};
// Prose that holds no verses, such as the variants page's opening, under a
// page title with the anchor given.
export function renderProse(blocks: Node[], titleAnchor = "") {
  const render = renderer(titleAnchor);
  return render.prose(render.blocks(blocks), "prose");
}
// A unit of front matter, under its printed title, and without it, for the
// search index to set under the title it gives the page.
// On the web a title is one heading: the lines that continue a title opening
// the unit join it. The dedication's address, around its title, stays apart.
export function renderMatter(doc: Document) {
  let blocks = blocksOf(doc);
  const [first, ...rest] = blocks;
  if (first?.marker === "mt1") {
    const end = rest.findIndex((n) => n.marker !== "mt2");
    const lines = end === -1 ? rest : rest.slice(0, end);
    const title = {
      ...first,
      content: [
        ...(first.content || []),
        ...lines.flatMap((n) => [" ", ...(n.content || [])]),
      ],
    };
    blocks = [title, ...rest.slice(lines.length)];
  }
  const render = renderer("matter");
  const grouped = runs(blocks);
  const html = grouped.map((nodes) => render.run(nodes));
  const prose = (shown: string[]) => render.prose(shown.join("\n"), "matter");
  return {
    html: prose(html),
    body: prose(html.filter((_, i) => grouped[i]![0]!.marker !== "mt1")),
  };
}
// The terms the entries are labelled with, as the edition abbreviates them.
export type Terms = { kjv: string; apparatus: string };
const isReading = (s: Segment): s is Reading =>
  typeof s !== "string" && ("from" in s || "to" in s);
// One witness's words of a lane, the source's (from) or the adopted text's
// (to): its own reading tinted where they differ, an ellipsis where words in
// agreement are left out, an empty slot where it has nothing the other has,
// and the words a correction of the English is about in bold. The spaces are
// the segments' own; an empty slot is spaced as the other witness's words
// are, so that it stands apart from the words beside it.
function witness(lane: Lane, side: "from" | "to") {
  return lane.segments
    .map((s) => {
      if (typeof s === "string") {
        return escape(s);
      }
      if ("gap" in s) {
        return '<span class="gap">…</span>';
      }
      if ("about" in s) {
        return `<strong>${escape(s.about)}</strong>`;
      }
      const reading = s[side];
      if (reading === undefined) {
        const other = s[side === "from" ? "to" : "from"] ?? "";
        const [before, after] = [/^\s*/, /\s*$/].map((r) => r.exec(other)![0]);
        return `${before}<span class="slot">⌀</span>${other.trim() ? after : ""}`;
      }
      return `<span class="${side === "from" ? "del" : "ins"}">${escape(reading)}</span>`;
    })
    .join("");
}
// A lane as a row of the table, after the cells that lead it: the source's
// words in one column and the adopted text's in the other, each under its
// witness; a lane the witnesses agree in is printed once, across both.
function pair(lane: Lane, terms: Terms, lead: string) {
  const label = (name: string) =>
    escape(lane.apparatus ? `${name} (${terms.apparatus})` : name);
  const cell = (tag: string, html: string, span = "") =>
    `<td class="cell"${span}><div class="tag">${tag}</div><div lang="${lane.language}">${html}</div></td>`;
  const cells = lane.segments.some(isReading)
    ? cell(label(lane.from), witness(lane, "from")) +
      cell(label(lane.to), witness(lane, "to"))
    : cell(
        `${label(lane.from)} and ${label(lane.to)}`,
        witness(lane, "from"),
        ' colspan="2"',
      );
  return `<tr class="pair ${lane.language}">${lead}${cells}</tr>`;
}
// A book's variants as a table, each entry a group of rows under an anchor
// of its verse, with its reference linked to the verse in its chapter, or to
// the chapter where the edition omits the verse, beside its lanes.
export function renderVariants(
  book: string,
  entries: Variant[],
  hasVerse: (chapter: string, verse: string) => boolean,
  terms: Terms,
) {
  const head =
    "<thead><tr><th>Verse</th><th>Source</th><th>Adopted</th></tr></thead>";
  const html = entries
    .map((entry) => {
      const reference = `${entry.chapter}:${entry.verse}`;
      const id = `c${entry.chapter}v${entry.verse}`;
      const target =
        chapterPath(book, entry.chapter) +
        (hasVerse(entry.chapter, entry.verse) ? `#v${entry.verse}` : "");
      const kjv = entry.kjv
        ? `<small>${escape(`${terms.kjv} ${entry.kjv}`)}</small>`
        : "";
      const ref = `<td class="ref" rowspan="${entry.lanes.length}"><a class="variant-link" href="${escape(target)}">${escape(reference)}</a>${kjv}</td>`;
      const rows = entry.lanes
        .map((lane, i) => pair(lane, terms, i ? "" : ref))
        .join("");
      return `<tbody class="variant" id="${escape(id)}">${rows}</tbody>`;
    })
    .join("\n");
  return scripture(`<table>${head}\n${html}</table>`, "variants");
}
