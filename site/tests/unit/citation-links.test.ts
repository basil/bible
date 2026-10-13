import { expect, test } from "vitest";
import { JSDOM } from "jsdom";
import { renderChapter, type Node } from "../../.vitepress/lib/usj.ts";

const render = (fields: Node[]) =>
  renderChapter({
    content: [
      {
        type: "para",
        marker: "p",
        content: [{ type: "note", marker: "f", content: fields }],
      },
    ],
  }).html;
const ref = (loc: string, ...content: (string | Node)[]): Node => ({
  type: "ref",
  loc,
  content,
});

test("exported references control citations regardless of their wording", () => {
  const html = render([
    { type: "char", marker: "fr", content: ["1:1 "] },
    { type: "char", marker: "ft", content: ["Compare 1 Cor. 2:16: "] },
    { type: "char", marker: "xt", content: [ref("EXO 4:9", "3:9–4:4")] },
    { type: "char", marker: "xt", content: ["; verse 99"] },
  ]);
  const dom = JSDOM.fragment(html);
  expect(dom.querySelector(".fr")!.tagName).toBe("B");
  expect(dom.querySelector(".ft a")).toBeNull();
  expect(dom.querySelector(".xt a")!.getAttribute("href")).toBe(
    "/read/exo/4#v9",
  );
  expect(dom.querySelector(".xt a")!.textContent).toBe("3:9–4:4");
  expect(dom.querySelectorAll(".xt a")).toHaveLength(1);
  expect(
    dom
      .querySelector('#n1 a[aria-label="Back to note 1"]')!
      .getAttribute("href"),
  ).toBe("#caller1");
});

test("routes chapters and lettered verses", () => {
  const dom = JSDOM.fragment(
    render([
      {
        type: "char",
        marker: "xt",
        content: [ref("PSA 2", "Ps. 2"), "; ", ref("PRO 22:8a", "22:8a")],
      },
    ]),
  );
  expect(
    [...dom.querySelectorAll(".xt a")].map((a) => a.getAttribute("href")),
  ).toEqual(["/read/psa/2", "/read/pro/22#v8a"]);
});

test("refuses a reference it cannot route", () => {
  expect(() =>
    render([
      { type: "char", marker: "xt", content: [ref('PSA 2?x="&', "Ps. 2")] },
    ]),
  ).toThrow("Unknown reference");
});

test("retains styles and citation edge spaces", () => {
  const html = render([
    { type: "char", marker: "ft", content: ["see"] },
    {
      type: "char",
      marker: "xt",
      content: [
        " ",
        ref("PSA 2", { type: "char", marker: "it", content: ["Ps. 2"] }),
        " ",
      ],
    },
  ]);
  expect(html).toContain(
    '</span> <span class="xt"><a href="/read/psa/2"><i class="it">Ps. 2</i></a></span> ',
  );
});

test("retains list separators and whitespace-only citation fields", () => {
  const dom = JSDOM.fragment(
    render([
      {
        type: "char",
        marker: "xt",
        content: [ref("EXO 4:9", "Ex. 4:9"), ", ", ref("EXO 4:16", "16")],
      },
      { type: "char", marker: "xt", content: [" "] },
      { type: "char", marker: "ft", content: ["TR"] },
    ]),
  );
  expect(dom.querySelector("#n1")!.textContent).toBe("Ex. 4:9, 16 TR ↩");
  expect(
    [...dom.querySelectorAll(".xt a")].map((a) => a.getAttribute("href")),
  ).toEqual(["/read/exo/4#v9", "/read/exo/4#v16"]);
});
