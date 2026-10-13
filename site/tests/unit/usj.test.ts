import { describe, expect, test } from "vitest";
import { JSDOM } from "jsdom";
import {
  escape,
  renderChapter,
  type Document,
  type Node,
} from "../../.vitepress/lib/usj.ts";

const chapter = (...blocks: Node[]): Document => ({
  content: [{ type: "chapter", number: "1" }, ...blocks],
});
const para = (marker: string, ...content: (string | Node)[]): Node => ({
  type: "para",
  marker,
  content,
});
const char = (marker: string, ...content: (string | Node)[]): Node => ({
  type: "char",
  marker,
  content,
});
const dom = (doc: Document, titled = false) =>
  JSDOM.fragment(renderChapter(doc, titled).html);

describe("chapter renderer", () => {
  test("escapes source text and attribute values", () => {
    expect(escape("&<>\"'")).toBe("&amp;&lt;&gt;&quot;&#39;");
    const fragment = dom(
      chapter(
        para("p", '<script> & "quoted"', {
          type: "verse",
          number: '1"<&',
          pubnumber: "<label>",
        }),
      ),
    );
    expect(fragment.querySelector("script")).toBeNull();
    expect(fragment.querySelector("p")!.textContent).toContain(
      '<script> & "quoted"',
    );
    expect(fragment.querySelector("sup")!.id).toBe('v1"<&');
    expect(fragment.querySelector("a")!.getAttribute("href")).toBe('#v1"<&');
    expect(fragment.querySelector("a")!.textContent).toBe("<label>");
  });

  test.each([
    ...[
      "p",
      "m",
      "mi",
      "nb",
      "q1",
      "q2",
      "qr",
      "qa",
      "qc",
      "d",
      "ip",
      "im",
      "imi",
      "iex",
    ].map((marker) => [marker, "P"]),
    ["s1", "H2"],
    ["s2", "H3"],
    ["s3", "H4"],
    ["ms1", "H2"],
    ["is1", "H2"],
    ["is2", "H3"],
  ])("renders paragraph %s as %s", (marker, tag) => {
    const element = dom(chapter(para(marker, "words"))).querySelector(
      `.${marker}`,
    )!;
    expect(element.tagName).toBe(tag);
    expect(element.textContent).toBe("words");
  });

  test.each([
    ["add", "SPAN"],
    ["sc", "SPAN"],
    ["it", "I"],
    ["bd", "B"],
    ["fv", "SPAN"],
    ["vp", "SPAN"],
  ])("renders character marker %s as %s", (marker, tag) => {
    const element = dom(
      chapter(para("p", char(marker, "words"))),
    ).querySelector(`.${marker}`)!;
    expect(element.tagName).toBe(tag);
    expect(element.textContent).toBe("words");
  });

  test("preserves nested character styles", () => {
    const fragment = dom(
      chapter(para("p", char("it", "First ", char("bd", "last")))),
    );
    expect(fragment.querySelector("i > b")!.textContent).toBe("last");
    expect(fragment.querySelector("i")!.textContent).toBe("First last");
  });
  test.each(["b", "ib"])("renders %s as a stanza break", (marker) => {
    expect(
      dom(chapter(para(marker)))
        .querySelector(".stanza")!
        .getAttribute("aria-hidden"),
    ).toBe("true");
  });
  test("renders a division as a horizontal rule", () => {
    expect(dom(chapter(para("sd2"))).querySelector("hr")).not.toBeNull();
  });
  test("omits the book", () => {
    const doc = chapter(para("p", "scripture"));
    doc.content.unshift({ type: "book", content: ["book"] });
    expect(dom(doc).textContent).toBe("scripture");
  });
  test("keeps verse anchors separate from displayed labels", () => {
    const doc = chapter(
      para("p", { type: "verse", number: "22f", pubnumber: "23" }, "words", {
        type: "verse",
        number: "24",
      }),
    );
    expect(renderChapter(doc).verses).toEqual(["22f", "24"]);
    const links = dom(doc).querySelectorAll(".verse a");
    expect(
      Array.from(links, (link) => [
        link.getAttribute("href"),
        link.textContent,
      ]),
    ).toEqual([
      ["#v22f", "23"],
      ["#v24", "24"],
    ]);
  });
  test.each(["f", "ef", "x"])(
    "links %s note callers and backlinks",
    (marker) => {
      const note: Node = {
        type: "note",
        marker,
        content: [char("ft", "first")],
      };
      const fragment = dom(
        chapter(
          para("p", "words", note, {
            ...note,
            content: [char("ft", "second")],
          }),
        ),
      );
      expect(
        Array.from(fragment.querySelectorAll(".note a"), (link) => [
          link.getAttribute("href"),
          link.getAttribute("aria-label"),
        ]),
      ).toEqual([
        ["#n1", "Note 1"],
        ["#n2", "Note 2"],
      ]);
      expect(
        Array.from(fragment.querySelectorAll(".notes li"), (li) => li.id),
      ).toEqual(["n1", "n2"]);
      expect(
        Array.from(fragment.querySelectorAll(".notes a"), (link) =>
          link.getAttribute("href"),
        ),
      ).toEqual(["#caller1", "#caller2"]);
      expect(fragment.querySelector("#n1")!.textContent).toContain("first");
      expect(fragment.querySelector("#n2")!.textContent).toContain("second");
    },
  );
  test.each([
    ["fr", "B"],
    ["fq", "SPAN"],
    ["fqa", "I"],
    ["ft", "SPAN"],
    ["fl", "SPAN"],
    ["xo", "B"],
    ["xt", "SPAN"],
    ["xta", "SPAN"],
  ])("renders note field %s as %s", (marker, tag) => {
    const fragment = dom(
      chapter(
        para("p", {
          type: "note",
          marker: "f",
          content: [char(marker, "words")],
        }),
      ),
    );
    expect(fragment.querySelector(`.${marker}`)!.tagName).toBe(tag);
  });
  test("uses an unnumbered chapter heading only as its title", () => {
    const doc = chapter(para("s1", "Susanna"), para("p", "words"));
    expect(dom(doc, true).querySelector(".s1")).toBeNull();
    expect(dom(doc, true).textContent!.trim()).toBe("words");
  });
  test("retains numbered chapter headings", () => {
    const doc = chapter(para("s1", "Heading"));
    expect(dom(doc).querySelector(".s1")!.textContent).toBe("Heading");
  });
  test.each(
    (
      [
        [para("unknown"), "Unknown paragraph marker unknown"],
        [{ type: "unknown" }, "Unknown block unknown"],
        [para("p", char("unknown")), "Unknown character marker unknown"],
        [para("p", { type: "unknown" }), "Unknown inline node unknown/"],
        [para("p", char("ft", "words")), "Note field outside note: ft"],
        [para("p", { type: "verse" }), "Unexpected verse milestone"],
        [
          para("p", { type: "note", marker: "unknown" }),
          "Unexpected note unknown",
        ],
        [
          para("p", {
            type: "note",
            marker: "f",
            content: [{ type: "note", marker: "f" }],
          }),
          "Unexpected note f",
        ],
        [
          para("p", {
            type: "note",
            marker: "f",
            content: [{ type: "verse", number: "1" }],
          }),
          "Unexpected verse milestone",
        ],
      ] satisfies [Node, string][]
    ).map(([node, message]) => ({ node, message })),
  )("rejects $message (case $#)", ({ node, message }) => {
    expect(() => renderChapter(chapter(node))).toThrow(message);
  });
});
