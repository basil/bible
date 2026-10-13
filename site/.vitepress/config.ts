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
  ["About the OLEB", "/about/"],
  ["Compare Translations", "/about/compare"],
  ["Endorsements", "/about/endorsements"],
  ["Licensing", "/about/licensing"],
  ["Contact", "/about/contact"],
].map(([text, link]) => ({ text, link }));
const resources = [
  {
    text: "Apology for the Septuagint",
    link: "/resources/apology-for-the-septuagint",
  },
  { text: "Improvements to the KJV", link: "/resources/improvements-kjv" },
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
      { text: "Read Online", link: "/read/", activeMatch: "^/read/" },
      { text: "Download PDF", link: "/bible.pdf" },
      { text: "About OLEB", items: about },
      { text: "Resources", items: resources },
    ],
    sidebar: {
      "/about/": about,
      "/resources/": resources,
      // Every page lists the whole Bible by section and book, and opens only
      // the chapters of the book it is in: the chapters of every book would
      // be prerendered into every page.
      "/read/": contents(),
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
