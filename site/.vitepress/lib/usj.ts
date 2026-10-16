// Presentation only: words and note attribution come from the prepared USJ.
export type Node = {
  type: string;
  marker?: string;
  number?: string;
  pubnumber?: string;
  loc?: string;
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
const blocksOf = (doc: Document) =>
  doc.content.filter((n) => n.type !== "book" && n.type !== "chapter");
const CHAR_TAGS: Record<string, string> = {
  add: "span",
  sc: "span",
  it: "i",
  bd: "b",
  fv: "span",
  vp: "span",
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
const PARAGRAPH_TAGS: Record<string, string> = {
  p: "p",
  m: "p",
  mi: "p",
  nb: "p",
  q1: "p",
  q2: "p",
  // A standalone Pause, and an acrostic name with the verse it opens.
  qr: "p",
  qa: "p",
  qc: "p",
  d: "p",
  s1: "h2",
  s2: "h3",
  s3: "h4",
  ms1: "h2",
  ip: "p",
  im: "p",
  imi: "p",
  iex: "p",
  is1: "h2",
  is2: "h3",
};
// A zero-width space stands for a number that a chapter or verse doesn't print.
const HIDDEN = "\u200b";
// A titled chapter's heading, a section's or a title's, stands for its number,
// and so is the page title.
export function renderChapter(doc: Document, titled = false) {
  const blocks = blocksOf(doc);
  const title = titled
    ? blocks.find((n) => n.marker === "s1" || n.marker === "d")
    : undefined;
  const notes: string[] = [];
  const verses: string[] = [];
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
      if (inNote || !["f", "ef", "x"].includes(marker)) {
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
      return `<${tag} class="${marker}">${body}</${tag}>`;
    }
    throw new Error(`Unknown inline node ${item.type}/${marker}`);
  }
  const html = blocks
    .map((n) => {
      if (n === title) {
        return "";
      }
      if (n.type !== "para") {
        throw new Error(`Unknown block ${n.type}`);
      }
      const marker = n.marker!;
      if (marker === "b" || marker === "ib") {
        return '<div class="stanza" aria-hidden="true"></div>';
      }
      if (marker === "sd2") {
        return "<hr>";
      }
      const tag = PARAGRAPH_TAGS[marker];
      if (!tag) {
        throw new Error(`Unknown paragraph marker ${marker}`);
      }
      return `<${tag} class="${marker}">${(n.content || []).map((c) => inline(c)).join("")}</${tag}>`;
    })
    .join("\n");
  // A page's Markdown is compiled as a Vue template: v-pre keeps the words,
  // which escape leaves free to hold "{{", from being read as expressions.
  return {
    html: `<div class="scripture" v-pre>${html}${notes.length ? `<h2>Notes</h2><ol class="notes">${notes.join("\n")}</ol>` : ""}</div>`,
    verses,
  };
}
