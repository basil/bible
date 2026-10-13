import { expect, test } from "vitest";
import { JSDOM } from "jsdom";
import { manifest, readerPages } from "../../.vitepress/lib/library.ts";

// readerPages refuses verse anchors that disagree with the inventory.
const pages = readerPages();
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
  },
);

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
