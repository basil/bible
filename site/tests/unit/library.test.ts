import { beforeEach, describe, expect, test, vi } from "vitest";
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { relative } from "node:path";
import type { Book, Matter } from "../../.vitepress/lib/library.ts";

vi.mock("node:fs", () => ({ readFileSync: vi.fn() }));

const books: Book[] = [
  {
    id: "GEN",
    section: "old_testament",
    title: "Genesis",
    short: "Genesis & beginnings",
    cited: "Genesis & beginnings",
    chapters: [
      { number: "1", label: "1", titled: false, verses: ["1", "2"] },
      { number: "2", label: "2", titled: false, verses: ["1"] },
    ],
  },
  {
    id: "DAG",
    section: "old_testament",
    title: "Daniel",
    short: "Daniel",
    cited: "Daniel",
    chapters: [{ number: "1", label: "Susanna", titled: true, verses: ["1"] }],
  },
];
// The front matter: the edition's own before the testaments, and each
// testament's before its books.
const matter: Matter[] = [
  { id: "XXD", section: "front", title: "Abbreviations", short: "Abbr." },
  { id: "XXB", section: "old_testament", title: "Preface", short: "Preface" },
];
const inventory = { books, matter };
const variants = {
  title: "Textual Variants",
  intro: [{ type: "para", marker: "ip", content: ["This appendix lists."] }],
  terms: { kjv: "KJV", apparatus: "apparatus" },
  books: [
    {
      id: "GEN",
      entries: [
        {
          chapter: "1",
          verse: "2",
          lanes: [
            {
              from: "TR",
              to: "RP26",
              language: "grc",
              segments: ["ἐν ", { from: "ἀρχή", to: "ἀρχῇ" }],
            },
          ],
        },
        {
          chapter: "2",
          verse: "9",
          lanes: [
            {
              from: "TR",
              to: "RP26",
              language: "grc",
              segments: [{ from: "καί" }, " δέ"],
            },
          ],
        },
      ],
    },
    {
      id: "DAG",
      entries: [
        {
          chapter: "1",
          verse: "1",
          lanes: [
            {
              from: "TR",
              to: "RP26",
              language: "grc",
              segments: [{ gap: true }, " ", { from: "ὁ", to: "ὅ" }],
            },
          ],
        },
      ],
    },
  ],
};
const files = () =>
  new Map<string, unknown>([
    ["manifest.json", inventory],
    ["variants.json", variants],
    [
      "matter/XXD.json",
      {
        content: [
          { type: "book", marker: "id", code: "XXD" },
          { type: "para", marker: "mt1", content: ["Abbreviations and Signs"] },
          {
            type: "table",
            content: [
              {
                type: "table:row",
                marker: "tr",
                content: [
                  { type: "table:cell", marker: "tc1", content: ["Alex."] },
                  {
                    type: "table:cell",
                    marker: "tc2",
                    content: ["for Codex Alexandrinus"],
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
    [
      "matter/XXB.json",
      {
        content: [
          { type: "book", marker: "id", code: "XXB" },
          { type: "para", marker: "mt2", content: ["To the Reader"] },
          { type: "para", marker: "mt1", content: ["Preface"] },
          {
            type: "para",
            marker: "ip",
            content: [
              "Some introduction",
              {
                type: "note",
                marker: "f",
                content: [
                  { type: "char", marker: "ft", content: ["See Bos."] },
                ],
              },
            ],
          },
        ],
      },
    ],
    ...books.flatMap((book) =>
      book.chapters.map(
        (chapter) =>
          [
            `books/${book.id}/${chapter.number}.json`,
            {
              content: [
                { type: "chapter", number: chapter.number },
                ...(book.id === "DAG"
                  ? [{ type: "para", marker: "s1", content: ["Susanna"] }]
                  : []),
                {
                  type: "para",
                  marker: "p",
                  content: chapter.verses.flatMap((number) => [
                    { type: "verse", number },
                    `Words ${number}.`,
                  ]),
                },
              ],
            },
          ] as const,
      ),
    ),
  ]);

let library: typeof import("../../.vitepress/lib/library.ts");
let fixture: ReturnType<typeof files>;
beforeEach(async () => {
  vi.resetModules();
  vi.mocked(readFileSync).mockReset();
  fixture = files();
  vi.mocked(readFileSync).mockImplementation((path) => {
    const key = relative(library.directory, String(path));
    if (!fixture.has(key)) {
      throw new Error(`Missing fixture: ${key}`);
    }
    return JSON.stringify(fixture.get(key));
  });
  library = await import("../../.vitepress/lib/library.ts");
});

describe("prepared Bible library", () => {
  test("reads and caches the manifest once", () => {
    const first = library.manifest();
    expect(first).toEqual(inventory);
    expect(library.manifest()).toBe(first);
    expect(readFileSync).toHaveBeenCalledTimes(1);
  });
  test.each(["missing", "malformed"])(
    "explains how to prepare a %s export",
    (kind) => {
      const cause = new Error("ENOENT");
      if (kind === "missing") {
        vi.mocked(readFileSync).mockImplementation(() => {
          throw cause;
        });
      } else {
        vi.mocked(readFileSync).mockReturnValue("{");
      }
      expect(() => library.manifest()).toThrow("run make web");
      try {
        library.manifest();
      } catch (error) {
        expect((error as Error).cause).toBeInstanceOf(Error);
      }
      // A failed read must not poison the cache.
      vi.mocked(readFileSync).mockReturnValue(JSON.stringify(inventory));
      expect(library.manifest()).toEqual(inventory);
    },
  );
  test("reads the requested chapter document", () => {
    expect(library.document(books[0], books[0].chapters[1])).toEqual(
      fixture.get("books/GEN/2.json"),
    );
    expect(readFileSync).toHaveBeenCalledWith(
      `${library.directory}/books/GEN/2.json`,
      "utf8",
    );
  });
  test("renders each unit of front matter under its printed title", () => {
    const routes = library.matterRoutes();
    expect(routes.map((r) => r.params.unit)).toEqual(["xxd", "xxb"]);
    expect(routes[0].params.title).toBe("Abbreviations");
    const abbreviations = JSDOM.fragment(routes[0].content);
    expect(abbreviations.querySelector("h1.mt1#matter")!.textContent).toBe(
      "Abbreviations and Signs",
    );
    expect(abbreviations.querySelector(".scripture.matter")).not.toBeNull();
    expect(abbreviations.querySelector("td.tc1")!.textContent).toBe("Alex.");
    const preface = JSDOM.fragment(routes[1].content);
    expect(preface.querySelector("p.mt2")!.textContent).toBe("To the Reader");
    expect(preface.querySelector(".notes li")!.textContent).toContain(
      "See Bos.",
    );
    expect(readFileSync).toHaveBeenCalledWith(
      `${library.directory}/matter/XXB.json`,
      "utf8",
    );
  });
  test("runs the pager through the front matter and the chapters in order", () => {
    const [abbreviations, preface] = library.matterRoutes();
    expect(abbreviations.params.prev).toBe(false);
    expect(abbreviations.params.next).toEqual({
      text: "Preface",
      link: "/read/xxb",
    });
    expect(preface.params.prev).toEqual({ text: "Abbr.", link: "/read/xxd" });
    expect(preface.params.next).toEqual({
      text: "Genesis & beginnings 1",
      link: "/read/gen/1",
    });
    const [genesis] = library.readerPages();
    expect(genesis.params.prev).toEqual({ text: "Preface", link: "/read/xxb" });
    expect(library.readerPages().at(-1)!.params.next).toBe(false);
  });
  test("refuses a page of a section the contents lack", () => {
    const altered = structuredClone(inventory);
    altered.matter[0].section = "back";
    fixture.set("manifest.json", altered);
    expect(() => library.matterRoutes()).toThrow(
      "Page in no section of the contents: /read/xxd",
    );
  });
  test("explains how to prepare a missing unit of front matter", () => {
    fixture.delete("matter/XXB.json");
    expect(() => library.matterRoutes()).toThrow(
      "Cannot read the prepared front matter XXB; run make web",
    );
  });
  test("explains how to prepare missing variants", () => {
    fixture.delete("variants.json");
    expect(() => library.variants()).toThrow(
      "Cannot read the prepared variants; run make web",
    );
    // A failed read must not poison the cache.
    fixture.set("variants.json", variants);
    expect(library.variants()).toEqual(variants);
  });
  test("provides front matter search content with its title", () => {
    const content = library.searchContent("read/xxb.md")!;
    expect(content).toMatch(/^# Preface \{#matter\}/);
    // The heading the index gives the page is its title's only one.
    expect(JSDOM.fragment(content).querySelector("#matter")).toBeNull();
    expect(content.match(/Preface/g)).toHaveLength(1);
    expect(content).toContain("Some introduction");
  });
  test("renders the chapter heading and scripture", () => {
    const page = library.readerPages()[1];
    const fragment = JSDOM.fragment(page.content);
    expect(fragment.querySelector("h1")!.textContent).toBe(
      "Genesis & beginnings 2",
    );
    expect(fragment.querySelector(".scripture")!.textContent).toContain(
      "Words 1.",
    );
  });
  test("uses the unnumbered heading as the page title once", () => {
    const page = library.readerPages()[2];
    expect(page.params.title).toBe("Susanna");
    const fragment = JSDOM.fragment(page.content);
    expect(fragment.querySelector("h1")!.textContent).toBe("Susanna");
    expect(fragment.querySelector(".s1")).toBeNull();
  });
  test("provides chapter search content with its title and scripture anchors", () => {
    const content = library.searchContent("read/gen/1.md")!;
    expect(content).toMatch(/^# Genesis & beginnings 1 \{#chapter\}/);
    expect(JSDOM.fragment(content).querySelector("#v2")!.textContent).toBe("2");
    expect(content).toContain("Words 1.");
  });
  test.each([
    "about/index.md",
    "read/gen.md",
    "read/gen/1.html",
    "/read/gen/1.md",
    "read/missing/1.md",
    "read/gen/99.md",
    "read/xxz.md",
    "variants/exo.md",
  ])("ignores unrelated or unknown search path %s", (path) => {
    expect(library.searchContent(path)).toBeUndefined();
  });
  test("renders each book's variants with anchors and a pager", () => {
    const routes = library.variantsRoutes().slice(1);
    expect(routes.map((r) => r.params.book)).toEqual(["gen", "dag"]);
    expect(routes[0].params.title).toBe(
      "Genesis & beginnings: Textual Variants",
    );
    expect(routes[0].params.prev).toEqual({
      text: "Introduction",
      link: "/variants/introduction",
    });
    expect(routes[0].params.next).toEqual({
      text: "Daniel",
      link: "/variants/dag",
    });
    expect(routes[1].params.next).toBe(false);
    const fragment = JSDOM.fragment(routes[0].content);
    expect(fragment.querySelector("h1")!.textContent).toBe(
      routes[0].params.title,
    );
    expect(
      [...fragment.querySelectorAll("tbody.variant")].map((s) => s.id),
    ).toEqual(["c1v2", "c2v9"]);
    // A verse the edition has is linked; one it lacks links its chapter.
    expect(
      [...fragment.querySelectorAll(".variant-link")].map((a) =>
        a.getAttribute("href"),
      ),
    ).toEqual(["/read/gen/1#v2", "/read/gen/2"]);
  });
  test("leaves the variants' index, a page of its own, to the search", () => {
    expect(library.searchContent("variants/index.md")).toBeUndefined();
  });
  test("provides variants search content with its title and anchors", () => {
    const content = library.searchContent("variants/dag.md")!;
    expect(content).toMatch(/^# Daniel: Textual Variants \{#variants\}/);
    expect(JSDOM.fragment(content).querySelector("#c1v1")).not.toBeNull();
  });
  test("the variants introduction shares search, sidebar and pager content", () => {
    const route = library.variantsRoutes()[0];
    expect(route.params.book).toBe("introduction");
    expect(route.params.prev).toBe(false);
    expect(route.params.next).toEqual({
      text: books[0].short,
      link: "/variants/gen",
    });
    expect(library.variantsLinks().map((p) => p.link)).toEqual(
      library.variantsRoutes().map((p) => `/variants/${p.params.book}`),
    );
    const content = library.searchContent("variants/introduction.md")!;
    expect(content).toMatch(/^# Introduction \{#variants\}/);
    expect(content).toContain("This appendix lists.");
    expect(
      JSDOM.fragment(route.content).querySelector("#variants"),
    ).not.toBeNull();
    expect(route.content).toContain(library.variantsIntro());
  });
  test("refuses variants of a book the edition lacks", () => {
    const altered = structuredClone(variants);
    altered.books[0].id = "EXO";
    fixture.set("variants.json", altered);
    expect(() => library.variantsRoutes()).toThrow(
      "Variants of a book the edition lacks: EXO",
    );
  });
  test.each([
    ["missing", ["1"]],
    ["reordered", ["2", "1"]],
    ["duplicate", ["1", "1"]],
  ])("rejects a %s verse inventory", (_kind, verses) => {
    const altered = structuredClone(inventory);
    altered.books[0].chapters[0].verses = verses;
    fixture.set("manifest.json", altered);
    expect(() => library.readerPages()).toThrow(
      "Verse anchors disagree with inventory: GEN 1",
    );
  });
  test("rejects duplicate anchors even when they match the inventory", () => {
    const altered = structuredClone(inventory);
    altered.books[0].chapters[0].verses = ["1", "1"];
    fixture.set("manifest.json", altered);
    fixture.set("books/GEN/1.json", {
      content: [
        { type: "chapter", number: "1" },
        {
          type: "para",
          marker: "p",
          content: [
            { type: "verse", number: "1" },
            { type: "verse", number: "1" },
          ],
        },
      ],
    });
    expect(() => library.readerPages()).toThrow(
      "Verse anchors disagree with inventory: GEN 1",
    );
  });
});
