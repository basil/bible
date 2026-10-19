import { expect, test } from "vitest";
import { JSDOM } from "jsdom";
import {
  chapters,
  chapterURL,
  manifest,
  matterRoutes,
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
function expectLinksResolved(content: string) {
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
  for (const link of fragment.querySelectorAll('a[href^="/read/"]')) {
    const href = link.getAttribute("href")!;
    expect(targets.has(href), `Unresolved citation ${href}`).toBe(true);
  }
}
test.each(pages)(
  "exported note links: $params.book $params.chapter",
  ({ content }) => expectLinksResolved(content),
);
test.each(matterRoutes())(
  "front matter note links: $params.unit",
  ({ content }) => expectLinksResolved(content),
);

test("Greek and Hebrew are set in the styles of their fonts", () => {
  const genesis = pages.find(
    (p) => p.params.book === "gen" && p.params.chapter === "1",
  )!;
  const greek = JSDOM.fragment(genesis.content).querySelector(".wg")!;
  expect(greek.getAttribute("lang")).toBe("grc");
  expect(greek.textContent).toMatch(/^εἰς/);
  const kingdoms = pages.find(
    (p) => p.params.book === "2sa" && p.params.chapter === "5",
  )!;
  const hebrew = JSDOM.fragment(kingdoms.content).querySelector(".wh")!;
  expect(hebrew.getAttribute("lang")).toBe("he");
  expect(hebrew.textContent).toBe("רפאים");
});

test("Exodus 4 links its note's citation to 1 Corinthians 2:16", () => {
  const page = pages.find(
    (p) => p.params.book === "exo" && p.params.chapter === "4",
  )!;
  const fragment = JSDOM.fragment(page.content);
  expect(
    fragment.querySelector('.ft a[href="/read/1co/2#v16"]')!.textContent,
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
  expect(fragment.querySelector(".cl")).toBeNull();
});

test("Sirach's Prologue is an introduction before chapter 1", () => {
  const sirach = manifest().books.find((book) => book.id === "SIR")!;
  expect(sirach.chapters[0]!.number).toBe("1");
  expect(sirach.chapters.some((chapter) => chapter.number === "0")).toBe(false);
  const prologue = pages.find(
    (page) => page.params.book === "sir" && page.params.chapter === "prologue",
  )!;
  expect(JSDOM.fragment(prologue.content).querySelector(".verse")).toBeNull();
  expect(prologue.params.next).toEqual({
    text: "Sirach 1",
    link: "/read/sir/1",
  });
  expect(
    pages.some(
      (page) => page.params.book === "sir" && page.params.chapter === "0",
    ),
  ).toBe(false);
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

test("Lamentations keeps acrostic headings separate from verse numbers", () => {
  const lamentations = pages.filter((p) => p.params.book === "lam");
  let labels = 0;
  for (const page of lamentations) {
    const rendered = JSDOM.fragment(page.content);
    for (const heading of rendered.querySelectorAll(".qa")) {
      expect(heading.querySelector(".verse")).toBeNull();
      expect(heading.nextElementSibling!.classList.contains("q1")).toBe(true);
      labels++;
    }
  }
  expect(labels).toBe(89);
});
