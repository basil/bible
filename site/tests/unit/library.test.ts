import { beforeEach, describe, expect, test, vi } from "vitest";
import { JSDOM } from "jsdom";
import { readFileSync } from "node:fs";
import { relative } from "node:path";
import type { Book } from "../../.vitepress/lib/library.ts";

vi.mock("node:fs", () => ({ readFileSync: vi.fn() }));

const books: Book[] = [
  {
    id: "GEN",
    section: "old",
    title: "Genesis",
    short: "Genesis & beginnings",
    chapters: [
      { number: "1", label: "1", titled: false, verses: ["1", "2"] },
      { number: "2", label: "2", titled: false, verses: ["1"] },
    ],
  },
  {
    id: "DAG",
    section: "old",
    title: "Daniel",
    short: "Daniel",
    chapters: [{ number: "1", label: "Susanna", titled: true, verses: ["1"] }],
  },
];
const inventory = { books };
const files = () =>
  new Map<string, unknown>([
    ["manifest.json", inventory],
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
    const content = library.chapterSearchContent("read/gen/1.md")!;
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
  ])("ignores unrelated or unknown search path %s", (path) => {
    expect(library.chapterSearchContent(path)).toBeUndefined();
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
