import { describe, expect, test } from "vitest";
import { JSDOM } from "jsdom";
import {
  escape,
  renderChapter,
  renderMatter,
  renderProse,
  renderVariants,
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
      "cl",
      "qd",
      "lit",
      "po",
      "ip",
      "im",
      "imi",
      "iex",
    ].map((marker) => [marker, "P"]),
    ["s1", "H2"],
    ["s2", "H3"],
    ["s3", "H4"],
    ["ms1", "H2"],
    ["ms2", "H3"],
    ["pm", "BLOCKQUOTE"],
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
    ["wg", "SPAN"],
    ["wh", "SPAN"],
    ["qs", "SPAN"],
  ])("renders character marker %s as %s", (marker, tag) => {
    const element = dom(
      chapter(para("p", char(marker, "words"))),
    ).querySelector(`.${marker}`)!;
    expect(element.tagName).toBe(tag);
    expect(element.textContent).toBe("words");
  });

  test.each([
    ["wg", "grc"],
    ["wh", "he"],
  ])("marks the language of a %s run", (marker, lang) => {
    const element = dom(
      chapter(para("p", "Gr. ", char(marker, "λόγος"), ",")),
    ).querySelector(`.${marker}`)!;
    expect(element.getAttribute("lang")).toBe(lang);
    expect(element.parentElement!.textContent).toBe("Gr. λόγος,");
  });

  test("gives no other character style a language", () => {
    expect(
      dom(chapter(para("p", char("it", "words")))).querySelector("[lang]"),
    ).toBeNull();
  });

  test("links a semantic reference inside ordinary footnote text", () => {
    const fragment = dom(
      chapter(
        para("p", "Words", {
          type: "note",
          marker: "f",
          content: [
            char("ft", "See ", {
              type: "ref",
              loc: "GEN 1:2",
              content: ["Gen. 1:2"],
            }),
          ],
        }),
      ),
    );
    const link = fragment.querySelector('.ft a[href="/read/gen/1#v2"]')!;
    expect(link.textContent).toBe("Gen. 1:2");
    expect(fragment.querySelector(".xt")).toBeNull();
  });
  test("preserves nested character styles", () => {
    const fragment = dom(
      chapter(para("p", char("it", "First ", char("bd", "last")))),
    );
    expect(fragment.querySelector("i > b")!.textContent).toBe("last");
    expect(fragment.querySelector("i")!.textContent).toBe("First last");
  });
  test("renders sibling list entries as one list", () => {
    const fragment = dom(
      chapter(
        para("ip", "Before"),
        para("li1", "Term and its description"),
        para("li1", "Other and its description"),
        para("ip", "After"),
      ),
    );
    expect(fragment.querySelectorAll("ul")).toHaveLength(1);
    expect(
      [...fragment.querySelectorAll("ul > *")].map(
        (e) => `${e.tagName.toLowerCase()}.${e.className}`,
      ),
    ).toEqual(["li.li1", "li.li1"]);
  });
  test("renders a blank paragraph as a stanza break", () => {
    expect(
      dom(chapter(para("b")))
        .querySelector(".stanza")!
        .getAttribute("aria-hidden"),
    ).toBe("true");
  });
  test("renders a division as a horizontal rule", () => {
    expect(dom(chapter(para("sd2"))).querySelector("hr")).not.toBeNull();
  });
  test("keeps a source colophon separate from scripture", () => {
    const fragment = dom(
      chapter(para("p", { type: "verse", number: "1" }, "Amen."), {
        type: "sidebar",
        marker: "esb",
        category: "colophon",
        content: [para("p", "Written from Rome.")],
      }),
    );
    expect(
      fragment.querySelector("aside.colophon")!.getAttribute("aria-label"),
    ).toBe("Source colophon");
    expect(fragment.querySelector("aside")!.textContent).toBe(
      "Written from Rome.",
    );
    expect(fragment.querySelectorAll(".verse")).toHaveLength(1);
  });
  test("labels the closing notice", () => {
    const fragment = dom(
      chapter(para("p", { type: "verse", number: "21" }, "Amen."), {
        type: "sidebar",
        marker: "esb",
        category: "closing",
        content: [para("p", "The end of the Holy Bible")],
      }),
    );
    expect(
      fragment.querySelector("aside.closing")!.getAttribute("aria-label"),
    ).toBe("Closing notice");
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
  test("keeps an unnumbered verse's anchor without a label", () => {
    const doc = chapter(
      para("p", { type: "verse", number: "0", pubnumber: "​" }, "title"),
    );
    expect(renderChapter(doc).verses).toEqual(["0"]);
    const page = dom(doc);
    expect(page.querySelector("#v0")!.textContent).toBe("");
    expect(page.querySelectorAll(".verse a")).toHaveLength(0);
  });
  test("takes a title as a titled chapter's heading", () => {
    const doc = chapter(para("cl", "The Prologue"), para("p", "words"));
    expect(renderChapter(doc, true).html).not.toContain("The Prologue");
  });
  test.each(["f", "x"])("links %s note callers and backlinks", (marker) => {
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
  });
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
    const doc = chapter(para("cl", "Susanna"), para("p", "words"));
    expect(dom(doc, true).querySelector(".cl")).toBeNull();
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
        [{ type: "table", content: ["row"] }, "Unexpected table content"],
        [
          { type: "table", content: [{ type: "table:row", content: ["x"] }] },
          "Unexpected row content",
        ],
        [
          {
            type: "table",
            content: [
              {
                type: "table:row",
                content: [{ type: "table:cell", marker: "tc9" }],
              },
            ],
          },
          "Unknown cell marker tc9",
        ],
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

describe("variants renderer", () => {
  type Variant = Parameters<typeof renderVariants>[1][number];
  type Lane = Variant["lanes"][number];
  const greek = (...segments: Lane["segments"]): Lane => ({
    from: "TR",
    to: "RP26",
    language: "grc",
    segments,
  });
  const english = (...segments: Lane["segments"]): Lane => ({
    from: "KJV",
    to: "OLEB",
    language: "en",
    segments,
  });
  const entry = (
    chapter: string,
    verse: string,
    ...lanes: Lane[]
  ): Variant => ({
    chapter,
    verse,
    lanes: lanes.length ? lanes : [greek({ from: "ἀλλά", to: "δέ" })],
  });
  const hasVerse = (chapter: string, verse: string) =>
    chapter === "5" && verse === "39";
  const terms = { kjv: "KJV", apparatus: "apparatus" };
  const render = (...entries: Variant[]) =>
    JSDOM.fragment(renderVariants("MAT", entries, hasVerse, terms));
  const texts = (root: ParentNode, selector: string) =>
    [...root.querySelectorAll(selector)].map((e) => e.textContent);

  test("anchors each entry by its verse and links its reference to the verse", () => {
    const fragment = render(entry("5", "39"), entry("17", "36"));
    const sections = fragment.querySelectorAll("tbody.variant");
    expect([...sections].map((s) => s.id)).toEqual(["c5v39", "c17v36"]);
    const links = [...fragment.querySelectorAll(".ref .variant-link")];
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "/read/mat/5#v39",
      "/read/mat/17",
    ]);
    expect(links.map((a) => a.textContent)).toEqual(["5:39", "17:36"]);
    expect(
      fragment.querySelector(".scripture")!.classList.contains("variants"),
    ).toBe(true);
    expect(texts(fragment, "thead th")).toEqual(["Verse", "Source", "Adopted"]);
  });

  test("sets each witness's own words in its column, the readings marked", () => {
    const fragment = render(
      entry(
        "19",
        "26",
        greek(
          { gap: true },
          " Παρὰ ἀνθρώποις τοῦτο ἀδύνατόν ",
          { from: "ἐστι", to: "ἐστιν" },
          ", παρὰ δὲ Θεῷ πάντα δυνατά ",
          { from: "ἐστι" },
          ".",
        ),
      ),
    );
    const [source, adopted] = fragment.querySelectorAll(".pair.grc .cell");
    expect(texts(fragment, ".pair .cell")).toHaveLength(2);
    expect(source!.querySelector(".tag")!.textContent).toBe("TR");
    expect(adopted!.querySelector(".tag")!.textContent).toBe("RP26");
    expect(source!.querySelector("[lang]")!.textContent).toBe(
      "… Παρὰ ἀνθρώποις τοῦτο ἀδύνατόν ἐστι, παρὰ δὲ Θεῷ πάντα δυνατά ἐστι.",
    );
    expect(adopted!.querySelector("[lang]")!.textContent).toBe(
      "… Παρὰ ἀνθρώποις τοῦτο ἀδύνατόν ἐστιν, παρὰ δὲ Θεῷ πάντα δυνατά ⌀.",
    );
    expect(texts(source!, ".del")).toEqual(["ἐστι", "ἐστι"]);
    expect(texts(adopted!, ".ins")).toEqual(["ἐστιν"]);
    for (const p of fragment.querySelectorAll(".pair.grc [lang]")) {
      expect(p.getAttribute("lang")).toBe("grc");
    }
    expect(fragment.querySelector(".pair.en")).toBeNull();
  });

  test("keeps a reading's space where the adopted text adds to a word", () => {
    const fragment = render(
      entry(
        "20",
        "21",
        greek("εὐωνύμων", { from: ",", to: " σου," }, " ἐν"),
        english("on ", { from: "the", to: "thy" }, " left"),
      ),
    );
    expect(texts(fragment, ".pair.grc [lang]")).toEqual([
      "εὐωνύμων, ἐν",
      "εὐωνύμων σου, ἐν",
    ]);
    const under = fragment.querySelector(".pair.en")!;
    expect(texts(under, ".tag")).toEqual(["KJV", "OLEB"]);
    expect(texts(under, "[lang]")).toEqual(["on the left", "on thy left"]);
    expect(under.querySelector("[lang]")!.getAttribute("lang")).toBe("en");
    expect(under.querySelector('[lang="grc"]')).toBeNull();
    expect(fragment.querySelector(".slot")).toBeNull();
  });

  test("labels a verse whose number the King James Bible gives otherwise, and each lane by its witness", () => {
    const fragment = render(
      {
        chapter: "14",
        verse: "24",
        kjv: "16:25",
        lanes: [
          { ...greek({ from: "ὁ", to: "ὅ" }), from: "Scrivener" },
          { ...greek({ from: "τὸ", to: "τῷ" }), apparatus: true },
        ],
      },
      entry("5", "39"),
    );
    const [labelled, plain] = fragment.querySelectorAll(".variant");
    expect(texts(labelled!, ".ref small")).toEqual(["KJV 16:25"]);
    expect(texts(plain!, ".ref small")).toEqual([]);
    expect(texts(labelled!, ".tag")).toEqual([
      "Scrivener",
      "RP26",
      "TR (apparatus)",
      "RP26 (apparatus)",
    ]);
  });

  test("prints a lane the witnesses agree in once, across both columns", () => {
    const fragment = render(
      entry(
        "23",
        "42",
        greek("ἐν τῇ βασιλείᾳ σου"),
        english("come ", { from: "into", to: "in" }, " thy kingdom"),
      ),
    );
    const same = fragment.querySelector(".pair.grc")!;
    expect(same.querySelector(".cell")!.getAttribute("colspan")).toBe("2");
    expect(texts(same, ".cell")).toHaveLength(1);
    expect(same.querySelector(".tag")!.textContent).toBe("TR and RP26");
    expect(same.querySelector("[lang]")!.textContent).toBe(
      "ἐν τῇ βασιλείᾳ σου",
    );
    expect(texts(fragment, ".pair.en .cell")).toHaveLength(2);
  });

  test("sets in bold the shared Greek a correction of the English is about", () => {
    const fragment = render(
      entry(
        "1",
        "13",
        greek("καὶ ", { about: "Ἰούδας Ἰακώβου" }, "."),
        english("Judas the ", { from: "brother", to: "son" }, " of James."),
      ),
    );
    const same = fragment.querySelector(".pair.grc")!;
    expect(same.querySelector(".cell")!.getAttribute("colspan")).toBe("2");
    expect(texts(same, "strong")).toEqual(["Ἰούδας Ἰακώβου"]);
    expect(same.querySelector("[lang]")!.textContent).toBe(
      "καὶ Ἰούδας Ἰακώβου.",
    );
  });

  test("shows an omitted verse as the source's words against nothing", () => {
    const fragment = render(
      entry(
        "17",
        "36",
        greek({ from: "δύο ἔσονται ἐν τῷ ἀγρῷ." }),
        english({ from: "Two men shall be in the field." }),
      ),
    );
    expect(texts(fragment, ".pair.grc [lang]")).toEqual([
      "δύο ἔσονται ἐν τῷ ἀγρῷ.",
      "⌀",
    ]);
    expect(texts(fragment, ".pair.en .slot")).toEqual(["⌀"]);
  });

  test("spaces an empty slot as the other witness's words are", () => {
    const fragment = render(
      entry(
        "3",
        "11",
        greek("ἐν πνεύματι ἁγίῳ", { from: " καὶ πυρί" }, "."),
        english("honour thy father ", { from: "and " }, "mother"),
      ),
    );
    expect(texts(fragment, ".pair [lang]")).toEqual([
      "ἐν πνεύματι ἁγίῳ καὶ πυρί.",
      "ἐν πνεύματι ἁγίῳ ⌀.",
      "honour thy father and mother",
      "honour thy father ⌀ mother",
    ]);
  });

  test("escapes the words", () => {
    const fragment = render(
      entry("1", "1", english("<b>", { from: "&", to: "{{ x }}" })),
    );
    expect(fragment.querySelector("b")).toBeNull();
    expect(texts(fragment, ".pair.en [lang]")).toEqual(["<b>&", "<b>{{ x }}"]);
  });
});

describe("front matter renderer", () => {
  const table: Node = {
    type: "table",
    content: [
      {
        type: "table:row",
        marker: "tr",
        content: [
          { type: "table:cell", marker: "th1", content: ["KJV"] },
          { type: "table:cell", marker: "th2", content: ["OLEB"] },
        ],
      },
      {
        type: "table:row",
        marker: "tr",
        content: [
          { type: "table:cell", marker: "tc1", content: ["1:1"] },
          {
            type: "table:cell",
            marker: "tc2",
            content: [char("it", "missing")],
          },
        ],
      },
    ],
  };
  const unit = (...blocks: Node[]): Document => ({
    content: [
      { type: "book", marker: "id", content: ["XXA"] },
      { type: "periph", id: "preface", alt: "Preface", content: blocks },
    ],
  });
  test("sets the printed title as the heading, with the lines about it", () => {
    const fragment = JSDOM.fragment(
      renderMatter(
        unit(
          para("mt2", "To the Prince"),
          para("mt1", "James,"),
          para("ip", "Great"),
        ),
      ).html,
    );
    expect(fragment.querySelector(".scripture.matter")).not.toBeNull();
    expect(fragment.querySelector("h1.mt1")!.id).toBe("matter");
    expect(
      [...fragment.querySelectorAll(".matter > *")].map(
        (e) => `${e.tagName.toLowerCase()}.${e.className}`,
      ),
    ).toEqual(["p.mt2", "h1.mt1", "p.ip"]);
    expect(fragment.textContent).toBe("To the Prince\nJames,\nGreat");
  });
  test("joins the lines that continue an opening title into its heading", () => {
    const fragment = JSDOM.fragment(
      renderMatter(
        unit(
          para("mt1", "Chapters and Verses"),
          para("mt2", "in the King James Bible"),
          para("ip", "Table"),
        ),
      ).html,
    );
    expect(
      [...fragment.querySelectorAll(".matter > *")].map(
        (e) => `${e.tagName.toLowerCase()}.${e.className}`,
      ),
    ).toEqual(["h1.mt1", "p.ip"]);
    expect(fragment.querySelector("h1#matter")!.textContent).toBe(
      "Chapters and Verses in the King James Bible",
    );
  });
  test("renders a table with its header and body cells", () => {
    const fragment = JSDOM.fragment(renderMatter(unit(table)).html);
    expect(
      [...fragment.querySelectorAll("table > tbody > tr > *")].map(
        (e) => `${e.tagName.toLowerCase()}.${e.className}`,
      ),
    ).toEqual(["th.th1", "th.th2", "td.tc1", "td.tc2"]);
    expect(fragment.querySelector("td.tc2 i.it")!.textContent).toBe("missing");
  });
  test("sets sibling list entries as one list", () => {
    const { html, body } = renderMatter(
      unit(
        para("mt1", "Introduction"),
        para("li1", "Term and its description"),
        para("li1", "Other and its description"),
        para("ip", "After"),
      ),
    );
    const tags = (shown: string) =>
      [...JSDOM.fragment(shown).querySelectorAll(".matter > *")].map((e) =>
        e.tagName.toLowerCase(),
      );
    expect(tags(html)).toEqual(["h1", "ul", "p"]);
    expect(tags(body)).toEqual(["ul", "p"]);
  });
  test("refuses a verse milestone in front matter", () => {
    expect(() =>
      renderMatter(unit(para("ip", { type: "verse", number: "1" }))),
    ).toThrow("Verse milestone in prose");
  });
});

describe("prose renderer", () => {
  test("renders paragraphs with their notes below", () => {
    const fragment = JSDOM.fragment(
      renderProse([
        para("ip", "Words", {
          type: "note",
          marker: "f",
          content: [char("ft", "A note")],
        }),
      ]),
    );
    expect(fragment.querySelector(".ip")!.textContent).toBe("Words[1]");
    expect(fragment.querySelector(".notes li")!.textContent).toContain(
      "A note",
    );
  });

  test("refuses a verse milestone in prose", () => {
    expect(() =>
      renderProse([para("p", { type: "verse", number: "1" })]),
    ).toThrow("Verse milestone in prose");
  });
});

test("acrostic headings stand alone with their verse number on the next line", () => {
  const doc = chapter(
    para("qa", { type: "verse", number: "5" }, "Beth"),
    para("q1", "The words of the poem."),
    para("qa", "Gimel"),
    para("q1", "Continuing the same verse."),
  );
  const before = JSON.stringify(doc);
  const rendered = renderChapter(doc);
  const page = JSDOM.fragment(rendered.html);
  expect(page.querySelector(".qa")!.textContent).toBe("Beth");
  expect(page.querySelectorAll(".qa .verse")).toHaveLength(0);
  expect(page.querySelector(".qa + .q1 > .verse")!.id).toBe("v5");
  expect(rendered.verses).toEqual(["5"]);
  expect(JSON.stringify(doc)).toBe(before);
});

test("list keys retain their role and punctuation", () => {
  const fragment = JSDOM.fragment(
    renderProse([para("li1", char("lik", "Label:"), " Description.")]),
  );
  expect(fragment.querySelector("li > i.lik")?.textContent).toBe("Label:");
  expect(fragment.querySelector("li")?.textContent).toBe("Label: Description.");
});
