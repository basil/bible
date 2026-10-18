import { defineConfig, type DefaultTheme } from "vitepress";
import { resolve } from "node:path";
import {
  manifest,
  chapterURL,
  matterLink,
  searchContent,
  directory,
  variants,
  variantsLinks,
  sections,
  type Book,
} from "./lib/library.ts";
const books = manifest().books;
const listed = variants();
// The edition's own pages stand at the top, under no heading.
function contents(current?: Book): DefaultTheme.SidebarItem[] {
  return sections().flatMap((s) => {
    const items: DefaultTheme.SidebarItem[] = [
      // A section's front matter precedes its books, as in the book.
      ...s.matter.map(matterLink),
      ...s.books.map((b) =>
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
    ];
    return s.title
      ? [
          {
            text: s.title,
            collapsed: current !== undefined && current.section !== s.section,
            items,
          },
        ]
      : items;
  });
}
const about = [
  ["Overview", "/about/"],
  ["Compare Translations", "/about/compare"],
  ["Endorsements", "/about/endorsements"],
  ["Contact", "/about/contact"],
  ["License", "/about/license"],
].map(([text, link]) => ({ text, link }));
const resources = [
  {
    text: "Apology for the Septuagint",
    link: "/resources/apology-for-the-septuagint",
  },
  { text: "Pierpont’s KJV Improvements", link: "/resources/improvements-kjv" },
  { text: "On Liturgical English", link: "/resources/liturgical-english" },
  {
    text: "Byzantine Music",
    link: "https://byzantinemusic.org",
    rel: "noopener",
    target: "_blank",
  },
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
      { text: "Variants", link: "/variants/", activeMatch: "^/variants/" },
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
            { text: listed.title, link: "/variants/" },
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
      "/variants/": [{ text: listed.title, items: variantsLinks() }],
    },
    socialLinks: [{ icon: "github", link: "https://github.com/basil/bible" }],
    search: {
      provider: "local",
      options: {
        async _render(src, env, md) {
          // Local search reads files directly; generated pages have no file.
          const html = await md.renderAsync(
            searchContent(env.relativePath) ?? src,
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
