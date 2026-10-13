import { expect, test } from "vitest";
import { JSDOM } from "jsdom";
import {
  chapters,
  chapterURL,
  manifest,
  readerPages,
} from "../../.vitepress/lib/library.ts";

// readerPages refuses verse anchors that disagree with the inventory.
const pages = readerPages();
// Every chapter and verse a citation may link to, as the site routes them.
const targets = new Set(
  chapters().flatMap(({ book, chapter }) => {
    const url = chapterURL(book, chapter);
    return [url, ...chapter.verses.map((verse) => `${url}#v${verse}`)];
  }),
);
test.each(pages)(
  "exported note links: $params.book $params.chapter",
  ({ content }) => {
    const fragment = JSDOM.fragment(content);
    for (const link of fragment.querySelectorAll('a[href^="#"]')) {
      const target = link.getAttribute("href")!.slice(1);
      expect(
        fragment.getElementById(target),
        `Unresolved link #${target}`,
      ).not.toBeNull();
    }
    // A citation the build cannot read prints without a link.
    for (const field of fragment.querySelectorAll(".xt")) {
      expect(
        field.querySelector("a"),
        `Unlinked citation ${field.textContent}`,
      ).not.toBeNull();
    }
    for (const link of fragment.querySelectorAll(".xt a")) {
      const href = link.getAttribute("href")!;
      expect(targets.has(href), `Unresolved citation ${href}`).toBe(true);
    }
  },
);

test("Exodus 4 links its note's citation to 1 Corinthians 2:16", () => {
  const page = pages.find(
    (p) => p.params.book === "exo" && p.params.chapter === "4",
  )!;
  const fragment = JSDOM.fragment(page.content);
  expect(
    fragment.querySelector('.xt a[href="/read/1co/2#v16"]')!.textContent,
  ).toBe("1 Cor. 2:16");
});

test("Susanna uses its source heading once", () => {
  const daniel = manifest().books.find((book) => book.id === "DAG")!;
  const page = pages.find(
    (page) =>
      page.params.book === "dag" &&
      page.params.chapter === daniel.chapters[0].number,
  )!;
  expect(page.params.title).toBe("Susanna");
  const fragment = JSDOM.fragment(page.content);
  expect(fragment.querySelector("h1")!.textContent).toBe("Susanna");
  expect(fragment.querySelector(".s1")).toBeNull();
});

test("generated quotation lists link each passage independently", () => {
  const page = pages.find(
    (p) => p.params.book === "mrk" && p.params.chapter === "10",
  )!;
  const note = [
    ...JSDOM.fragment(page.content).querySelectorAll(".notes li"),
  ].find((n) => n.textContent.startsWith("10:19 Ex. 20:12"))!;
  expect(
    [...note.querySelectorAll(".xt a")].map((a) => [
      a.textContent,
      a.getAttribute("href"),
    ]),
  ).toEqual([
    ["Ex. 20:12", "/read/exo/20#v12"],
    ["13–17", "/read/exo/20#v13"],
    ["Deut. 5:16", "/read/deu/5#v16"],
    ["17–21", "/read/deu/5#v17"],
  ]);
});
