import { defineConfig } from "vitepress";
import { resolve } from "node:path";
import {
  manifest,
  chapterURL,
  chapterSearchContent,
  directory,
  SECTIONS,
  type Book,
} from "./lib/library.ts";
const books = manifest().books;
function contents(current?: Book) {
  return Object.entries(SECTIONS).map(([section, text]) => ({
    text,
    collapsed: current !== undefined && current.section !== section,
    items: books
      .filter((b) => b.section === section)
      .map((b) =>
        b === current
          ? {
              text: b.short,
              items: b.chapters.map((c) => ({
                text: c.label,
                link: chapterURL(b, c),
              })),
            }
          : { text: b.short, link: chapterURL(b, b.chapters[0]) },
      ),
  }));
}
const about = [
  ["Overview", "/about/"],
  ["Compare Translations", "/about/compare"],
  ["Endorsements", "/about/endorsements"],
  ["Report an Issue", "/about/contact"],
  ["Licensing", "/about/licensing"],
].map(([text, link]) => ({ text, link }));
const resources = [
  {
    text: "Apology for the Septuagint",
    link: "/resources/apology-for-the-septuagint",
  },
  { text: "Pierpont’s KJV Improvements", link: "/resources/improvements-kjv" },
  { text: "On Liturgical English", link: "/resources/liturgical-english" },
];
export default defineConfig({
  vite: {
    resolve: { alias: { "@edition-fonts": resolve(directory, "fonts") } },
    server: {
      fs: {
        allow: [resolve(directory, "../../site"), resolve(directory, "fonts")],
      },
    },
    build: { assetsInlineLimit: 0 },
  },
  cleanUrls: true,
  title: "Orthodox Liturgical English Bible",
  description:
    "Brenton’s Septuagint and the King James New Testament conformed to the Byzantine text, in one volume.",
  head: [
    ["link", { rel: "icon", href: "/favicon.svg", type: "image/svg+xml" }],
  ],
  transformPageData(page) {
    if (page.params?.title) {
      page.title = String(page.params.title);
      page.frontmatter.prev = page.params.prev;
      page.frontmatter.next = page.params.next;
    }
  },
  markdown: {
    typographer: true,
  },
  themeConfig: {
    siteTitle: "OLEB",
    sidebarMenuLabel: "Contents",
    nav: [
      { text: "Home", link: "/" },
      { text: "Read", link: "/read/", activeMatch: "^/read/" },
      { text: "Download", link: "/bible.pdf" },
      { text: "About", items: about },
      { text: "Resources", items: resources },
    ],
    sidebar: {
      "/": [
        {
          text: "OLEB",
          items: [
            { text: "Read Online", link: "/read/" },
            { text: "Download PDF", link: "/bible.pdf" },
          ],
        },
        { text: "About", items: about },
        { text: "Resources", items: resources },
      ],
      "/read/": contents(),
      // Include chapter links only for the current book to keep pages small.
      ...Object.fromEntries(
        books.map((b) => [`/read/${b.id.toLowerCase()}/`, contents(b)]),
      ),
    },
    socialLinks: [{ icon: "github", link: "https://github.com/basil/bible" }],
    search: {
      provider: "local",
      options: {
        async _render(src, env, md) {
          // Local search reads files directly; generated pages have no file.
          const html = await md.renderAsync(
            chapterSearchContent(env.relativePath) ?? src,
            env,
          );
          return env.frontmatter?.search === false ? "" : html;
        },
      },
    },
    footer: {
      copyright:
        "Copyright © 2026 Basil Crow, under a Creative Commons BY-NC-ND 4.0 license.",
    },
  },
});
