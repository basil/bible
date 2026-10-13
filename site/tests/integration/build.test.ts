// VitePress can report a failed paths loader without failing its build.
// Require every exported chapter to have reached the static output.
import { readFileSync, readdirSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { expect, test } from "vitest";
import { JSDOM } from "jsdom";
import MiniSearch from "minisearch";
import { chapters, directory, manifest } from "../../.vitepress/lib/library.ts";
import comparisons from "../../about/compare.data.ts";

const dist = new URL("../../.vitepress/dist/", import.meta.url);
const assets = new URL("assets/", dist);
const fonts = pathToFileURL(`${directory}/fonts/`);
const books = manifest().books;
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
const fontNames = entries(fonts, "run make web");
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
      html.matchAll(/<sup class="verse" id="v([^"]+)"/g),
      (match) => match[1],
    );
    expect(anchors, `${book.id} ${chapter.number}`).toEqual(chapter.verses);
  }
});

test.each([
  ["gen/50", "next", "Exodus 1", "/read/exo/1"],
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

test("chapter pager stops at the first and last chapters", () => {
  const sequence = chapters();
  for (const [entry, direction] of [
    [sequence[0], "prev"],
    [sequence.at(-1)!, "next"],
  ] as const) {
    const fragment = JSDOM.fragment(
      builtFile(
        `read/${entry.book.id.toLowerCase()}/${entry.chapter.number}.html`,
      ),
    );
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
  ["Pierpont", "/resources/improvements-kjv#"],
  ["unencumbered", "/resources/improvements-kjv#"],
])("search query %s points to an existing anchor", (query, prefix) => {
  const result = search
    .search(query)
    .find((result) => result.id.startsWith(prefix));
  expect(result).toBeDefined();
  expectSearchAnchor(result!.id);
});
