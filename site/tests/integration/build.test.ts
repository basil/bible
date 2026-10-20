// VitePress can report a failed paths loader without failing its build.
// Require every exported chapter to have reached the static output.
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { expect, test } from "vitest";
import { JSDOM } from "jsdom";
import MiniSearch from "minisearch";
import {
  chapters,
  directory,
  manifest,
  matterURL,
  variants,
  variantsURL,
} from "../../.vitepress/lib/library.ts";
import comparisons from "../../about/compare.data.ts";

const dist = new URL("../../.vitepress/dist/", import.meta.url);
const assets = new URL("assets/", dist);
const fonts = pathToFileURL(`${directory}/fonts/`);
const books = manifest().books;
// The Old Testament's last book, after which the New Testament's front matter stands.
const lastOld = books.filter((b) => b.section === "old_testament").at(-1)!;
test("citation links retain spacing before their witness labels", () => {
  const page = JSDOM.fragment(builtFile("read/jhn/2.html"));
  const note = [...page.querySelectorAll(".notes li")].find((li) =>
    li.textContent.includes("Ps. 68:10"),
  )!;
  expect(note.textContent).toContain("Ps. 68:10 (Heb.");
  expect(note.querySelector('a[href="/read/psa/68#v10"]')).not.toBeNull();
});
function builtFile(path: string): string {
  try {
    return readFileSync(new URL(path, dist), "utf8");
  } catch (cause) {
    throw new Error(
      `Cannot read built site file ${path}; run npm --prefix site run build after make web.`,
      { cause },
    );
  }
}

test.each([
  "read/index",
  "variants/index",
  "variants/introduction",
  "variants/mat",
  "read/gen/1",
  "read/translators-to-reader",
])("headings on %s have accessible permalinks", (path) => {
  const page = JSDOM.fragment(builtFile(`${path}.html`));
  const headings = [
    ...page.querySelectorAll(".vp-doc h1, .vp-doc h2, .vp-doc h3, .vp-doc h4"),
  ];
  expect(headings.length).toBeGreaterThan(0);
  expect(new Set(headings.map((h) => h.id)).size).toBe(headings.length);
  for (const h of headings) {
    expect(h.id).not.toBe("");
    expect(h.getAttribute("tabindex")).toBe("-1");
    const link = h.querySelector(".header-anchor")!;
    expect(link).not.toBeNull();
    expect(link.getAttribute("href")).toBe(`#${h.id}`);
    expect(link.getAttribute("aria-label")).toMatch(/^Permalink to “.+”$/);
  }
});

// The reader's sidebar: the book's sections.
const reader = ["Old Testament", "New Testament"];
test.each([
  ["read/index", reader],
  ["read/gen/1", reader],
  ["read/mat/1", reader],
  ["read/dedication", reader],
  ["variants/index", ["Textual Variants"]],
  ["variants/introduction", ["Textual Variants"]],
  ["variants/rev", ["Textual Variants"]],
  ["about/index", ["OLEB", "About", "Resources"]],
  ["resources/liturgical-english", ["OLEB", "About", "Resources"]],
])("sidebar groups for %s", (path, headings) => {
  const page = JSDOM.fragment(builtFile(`${path}.html`));
  expect(
    [...page.querySelectorAll(".VPSidebar h2")].map((e) => e.textContent),
  ).toEqual(headings);
});

test("reader sidebar lists chapters of the current book", () => {
  const page = JSDOM.fragment(builtFile("read/gen/1.html"));
  const sidebar = page.querySelector(".VPSidebar")!;
  expect(sidebar.querySelector('a[href="/read/gen/2"]')).not.toBeNull();
  expect(sidebar.querySelector('a[href="/read/exo/1"]')).not.toBeNull();
  expect(sidebar.querySelector('a[href="/read/exo/2"]')).toBeNull();
});

test("every unit of front matter reaches the static output under its title", () => {
  const units = manifest().matter;
  expect(units.map((u) => u.id)).toEqual([
    "abbreviations",
    "editor-introduction",
    "numbering",
    "brenton-preface",
    "brenton-introduction",
    "dedication",
    "translators-to-reader",
  ]);
  for (const unit of units) {
    const page = JSDOM.fragment(builtFile(`${matterURL(unit).slice(1)}.html`));
    expect(
      page.querySelectorAll(".scripture.matter h1.mt1#matter"),
      unit.id,
    ).toHaveLength(1);
  }
  // The dedication's address stands around its title, as printed.
  const dedication = JSDOM.fragment(builtFile("read/dedication.html"));
  expect(dedication.querySelector(".matter h1.mt1")!.textContent).toBe(
    "James,",
  );
  expect(dedication.querySelectorAll(".matter p.mt2")).toHaveLength(4);
  // The abbreviations and the numbering are tables; the Preface quotes Hebrew.
  expect(
    JSDOM.fragment(builtFile("read/abbreviations.html")).querySelector(
      ".matter table td.tc1",
    ),
  ).not.toBeNull();
  expect(
    JSDOM.fragment(builtFile("read/numbering.html")).querySelector(
      ".matter table th.th1",
    ),
  ).not.toBeNull();
  expect(
    JSDOM.fragment(builtFile("read/brenton-preface.html")).querySelector(
      ".matter .wh",
    ),
  ).not.toBeNull();
});

test("the reader's index links each section's front matter before its books", () => {
  const page = JSDOM.fragment(builtFile("read/index.html"));
  expect(
    [...page.querySelectorAll(".matter-card h3 a:not(.header-anchor)")].map(
      (a) => a.getAttribute("href"),
    ),
  ).toEqual(manifest().matter.map(matterURL));
});

test("every book's variants reach the static output with their anchors", () => {
  for (const book of variants().books) {
    const page = JSDOM.fragment(
      builtFile(`${variantsURL(book).slice(1)}.html`),
    );
    expect(
      [...page.querySelectorAll("tbody.variant")].map((s) => s.id),
      book.id,
    ).toEqual(book.entries.map((e) => `c${e.chapter}v${e.verse}`));
    expect(page.querySelector('.variants [lang="grc"]')).not.toBeNull();
    // Every lane compares two columns, but for one the witnesses agree in,
    // which spans both.
    for (const pair of page.querySelectorAll(".variants .pair")) {
      const cells = pair.querySelectorAll(".cell");
      expect(cells).toHaveLength(cells[0]!.hasAttribute("colspan") ? 1 : 2);
    }
  }
});

test("the variants link the verses the edition has, and omitted verses' chapters", () => {
  const page = JSDOM.fragment(builtFile("variants/luk.html"));
  expect(
    page.querySelector("#c17v35 .variant-link")!.getAttribute("href"),
  ).toBe("/read/luk/17#v35");
  expect(
    page.querySelector("#c17v36 .variant-link")!.getAttribute("href"),
  ).toBe("/read/luk/17");
  // The omitted verse has the source's words against nothing, in both lanes.
  expect(
    [...page.querySelectorAll("#c17v36 .pair")].map(
      (pair) => pair.querySelectorAll(".slot").length,
    ),
  ).toEqual([1, 1]);
  expect(builtFile("read/luk/17.html")).toContain('id="v35"');
});

test("the variants' introduction has its own page, with sources in its prose", () => {
  const intro = JSDOM.fragment(builtFile("variants/introduction.html"));
  expect(intro.querySelector(".scripture .p")!.textContent).toContain(
    "conformed to the Byzantine text",
  );
  expect(
    [...intro.querySelectorAll(".scripture .p")].some((p) =>
      p.textContent.startsWith("The changes start from William G. Pierpont"),
    ),
  ).toBe(true);
  expect(intro.querySelector(".scripture .notes")).toBeNull();
  const page = JSDOM.fragment(builtFile("variants/index.html"));
  expect(page.querySelector(".scripture")).toBeNull();
  expect(
    [...page.querySelectorAll(".book-card h3 a:not(.header-anchor)")].map((a) =>
      a.getAttribute("href"),
    ),
  ).toEqual(variants().books.map(variantsURL));
});

test("comparison keeps the full OSB quotations between KJV and OLEB", () => {
  const quoted = comparisons.load().filter((quote) => quote.osb);
  expect(quoted).not.toHaveLength(0);
  const page = JSDOM.fragment(builtFile("about/compare.html"));
  const shown = [...page.querySelectorAll("details.comparison")];
  for (const quote of quoted) {
    const entry = shown.find(
      (details) =>
        details.querySelector("summary")?.textContent.trim() ===
        quote.reference,
    );
    expect(entry, quote.reference).toBeDefined();
    expect(
      [...entry!.querySelectorAll("dt .comparison-label")].map(
        (e) => e.textContent,
      ),
    ).toEqual(["KJV", "OSB", "OLEB"]);
    expect(entry!.querySelectorAll("dd")[1].textContent).toBe(
      quote.osb!.map((span) => span.text).join(""),
    );
  }
});
function entries(directory: URL, instruction: string): string[] {
  try {
    const names = readdirSync(directory);
    if (!names.length) {
      throw new Error("Directory is empty");
    }
    return names;
  } catch (cause) {
    throw new Error(`Cannot read ${directory.pathname}; ${instruction}.`, {
      cause,
    });
  }
}
const assetNames = entries(
  assets,
  "run npm --prefix site run build after make web",
);
// The faces beside their stylesheet, which the theme imports.
const fontNames = entries(fonts, "run make web").filter((name) =>
  name.endsWith(".woff"),
);
const css = assetNames
  .filter((name) => name.endsWith(".css"))
  .map((name) => builtFile(`assets/${name}`))
  .join("\n");
const chunks = new URL("chunks/", assets);
const searchFile = entries(
  chunks,
  "run npm --prefix site run build after make web",
).find(
  (name) => name.startsWith("@localSearchIndexroot.") && name.endsWith(".js"),
);
if (!searchFile) {
  throw new Error(
    "Missing local search index; run npm --prefix site run build after make web.",
  );
}
const { default: serializedIndex } = await import(
  /* @vite-ignore */ new URL(searchFile, chunks).href
);
const search = MiniSearch.loadJSON(serializedIndex, {
  fields: ["title", "titles", "text"],
  storeFields: ["title", "titles"],
});

function expectSearchAnchor(id: string) {
  const [path, anchor] = id.split("#");
  expect(anchor, `Search result has no anchor: ${id}`).toBeTruthy();
  const fragment = JSDOM.fragment(builtFile(`${path.slice(1)}.html`));
  expect(
    fragment.getElementById(anchor),
    `Search result has no matching anchor: ${id}`,
  ).not.toBeNull();
}

// One pass over the built pages: parsing each into a DOM would cost more
// than building it.
test("every chapter reaches the static output with its verse anchors", () => {
  for (const { book, chapter } of chapters()) {
    const html = builtFile(
      `read/${book.id.toLowerCase()}/${chapter.number}.html`,
    );
    const anchors = Array.from(
      html.matchAll(/<(?:sup|span) class="verse" id="v([^"]+)"/g),
      (match) => match[1],
    );
    expect(anchors, `${book.id} ${chapter.number}`).toEqual(chapter.verses);
  }
});

test("Sirach's introduction has a named static page and search entry", () => {
  const page = JSDOM.fragment(builtFile("read/sir/prologue.html"));
  expect(page.querySelector("#introduction")!.textContent).toContain(
    "The Prologue",
  );
  expect(page.querySelector(".scripture .verse")).toBeNull();
  expect(page.querySelector(".VPDocFooter a.next")!.getAttribute("href")).toBe(
    "/read/sir/1",
  );
  expect(existsSync(new URL("read/sir/0.html", dist))).toBe(false);
  const results = search.search("Whereas many and great things", {
    prefix: true,
  });
  expect(
    results.some((result) =>
      String(result.id).startsWith("/read/sir/prologue#"),
    ),
  ).toBe(true);
});

test("numbering tables name each book once above their Bible column headings", () => {
  const page = JSDOM.fragment(builtFile("read/numbering.html"));
  const tables = [...page.querySelectorAll(".matter table")];
  expect(tables).toHaveLength(34);
  expect(page.querySelector("h1")!.textContent).toBe(
    "Chapters and Verses in the King James Bible",
  );
  const introduction = JSDOM.fragment(
    builtFile("read/editor-introduction.html"),
  );
  const names = [...introduction.querySelectorAll(".matter table")].find(
    (table) => table.textContent?.includes("King James Bible"),
  )!;
  expect(names).toBeDefined();
  expect(names.textContent).toContain("1 Kings");
  for (const row of names.querySelectorAll("tr")) {
    const cells = [...row.querySelectorAll("td")].map(
      (cell) => cell.textContent,
    );
    if (cells.length === 2) {
      expect(cells[0]).not.toBe(`${cells[1]} (Apocrypha)`);
    }
  }
  for (const table of tables) {
    expect(
      [...table.querySelectorAll("th")].map((cell) => cell.textContent),
    ).toEqual(["King James Bible", "Orthodox Liturgical English Bible"]);
  }
  expect(
    [...page.querySelectorAll("h2.s1")].filter(
      (heading) => heading.textContent === "Amos",
    ),
  ).toHaveLength(1);
});

test.each([
  ["gen/50", "next", "Exodus 1", "/read/exo/1"],
  [
    "abbreviations",
    "next",
    "Editor’s Introduction",
    "/read/editor-introduction",
  ],
  ["brenton-introduction", "next", "Genesis 1", "/read/gen/1"],
  ["gen/1", "prev", "Introduction", "/read/brenton-introduction"],
  [
    `${lastOld.id.toLowerCase()}/${lastOld.chapters.at(-1)!.number}`,
    "next",
    "The Epistle Dedicatory",
    "/read/dedication",
  ],
  ["translators-to-reader", "next", "Matthew 1", "/read/mat/1"],
  [
    "mat/1",
    "prev",
    "The Translators to the Reader",
    "/read/translators-to-reader",
  ],
  [
    "neh/1",
    "prev",
    `2 Esdras ${books.find((book) => book.id === "EZR")!.chapters.at(-1)!.label}`,
    `/read/ezr/${books.find((book) => book.id === "EZR")!.chapters.at(-1)!.number}`,
  ],
])("chapter pager: %s %s", (page, direction, text, href) => {
  const fragment = JSDOM.fragment(builtFile(`read/${page}.html`));
  const link = fragment.querySelector(`.VPDocFooter a.${direction}`)!;
  expect(link.getAttribute("href")).toBe(href);
  expect(link.querySelector(".title")!.textContent).toBe(text);
});

test("variants navigation runs from the introduction through every book", () => {
  const links = [
    { text: "Introduction", link: "/variants/introduction" },
    ...variants().books.map((b) => ({
      text: books.find((book) => book.id === b.id)!.short,
      link: variantsURL(b),
    })),
  ];
  for (const [i, current] of links.entries()) {
    const page = JSDOM.fragment(builtFile(`${current.link.slice(1)}.html`));
    for (const [direction, target] of [
      ["prev", links[i - 1]],
      ["next", links[i + 1]],
    ] as const) {
      const link = page.querySelector(`.VPDocFooter a.${direction}`);
      if (target) {
        expect(link?.getAttribute("href")).toBe(target.link);
        expect(link?.querySelector(".title")!.textContent).toBe(target.text);
      } else {
        expect(link).toBeNull();
      }
    }
  }
});

test("the pager stops at the first page of the front matter and the last chapter", () => {
  const last = chapters().at(-1)!;
  for (const [path, direction] of [
    [matterURL(manifest().matter[0]).slice(1), "prev"],
    [`read/${last.book.id.toLowerCase()}/${last.chapter.number}`, "next"],
  ] as const) {
    const fragment = JSDOM.fragment(builtFile(`${path}.html`));
    expect(fragment.querySelector(`.VPDocFooter a.${direction}`)).toBeNull();
  }
});

test.each(fontNames)("bundles font %s unchanged with a root URL", (name) => {
  const dot = name.lastIndexOf(".");
  const matches = assetNames.filter(
    (asset) =>
      asset.startsWith(`${name.slice(0, dot)}.`) &&
      asset.endsWith(name.slice(dot)),
  );
  expect(matches).toHaveLength(1);
  expect(readFileSync(new URL(matches[0], assets))).toEqual(
    readFileSync(new URL(name, fonts)),
  );
  expect(css).toContain(`/assets/${matches[0]}`);
});

test.each(books)("search finds $short with an existing anchor", (book) => {
  const result = search
    .search(book.short)
    .find((result) => result.id.startsWith(`/read/${book.id.toLowerCase()}/`));
  expect(result).toBeDefined();
  expectSearchAnchor(result!.id);
});

test.each([
  ["Ezekiel", "/read/ezk/"],
  ["firmament", "/read/gen/"],
  ["Scrivener", "/variants/introduction#variants"],
  ["thankless", "/read/brenton-preface#"],
  ["Occidental", "/read/dedication#"],
  ["Pierpont", "/resources/improvements-kjv#"],
  ["unencumbered", "/resources/improvements-kjv#"],
])("search query %s points to an existing anchor", (query, prefix) => {
  const result = search
    .search(query)
    .find((result) => result.id.startsWith(prefix));
  expect(result).toBeDefined();
  expectSearchAnchor(result!.id);
});
