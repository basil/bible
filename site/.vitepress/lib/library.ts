import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  renderChapter,
  renderMatter,
  renderProse,
  renderVariants,
  heading,
  chapterPath,
  type Document,
  type Node,
  type Variant,
} from "./usj.ts";
export type Chapter = {
  number: string;
  label: string;
  titled: boolean;
  verses: string[];
};
export type Book = {
  id: string;
  section: string;
  title: string;
  short: string;
  // The name one of its chapters is cited by.
  cited: string;
  chapters: Chapter[];
  introduction?: { title: string; slug: string };
};
export const directory = fileURLToPath(
  new URL("../../../build/web/", import.meta.url),
);
// A unit of reader front matter, under the section it opens.
export type Matter = {
  id: string;
  section: string;
  title: string;
  short: string;
};
type Manifest = { books: Book[]; matter: Matter[] };
// The reader's sections in the book's order: the edition's own pages,
// untitled, before the testaments, then each testament's front matter
// and books.
const SECTIONS: Record<string, string> = {
  front: "",
  old_testament: "Old Testament",
  new_testament: "New Testament",
};
// A file make web writes, explaining how to prepare it where it is missing
// or malformed.
function readPrepared<T>(name: string, what: string): T {
  try {
    return JSON.parse(readFileSync(`${directory}/${name}`, "utf8")) as T;
  } catch (error) {
    throw new Error(
      `Cannot read the prepared ${what}; run make web before building or serving the site.`,
      { cause: error },
    );
  }
}
// Read once: every chapter page and the navigation ask for it.
let prepared: Manifest | undefined;
export function manifest(): Manifest {
  prepared ??= readPrepared<Manifest>("manifest.json", "Bible");
  return prepared;
}
// The variants: the page's title and opening prose,
// and its entries by book, whose names the manifest carries.
type VariantsBook = { id: string; entries: Variant[] };
type Terms = { kjv: string; apparatus: string };
type Variants = {
  title: string;
  intro: Node[];
  terms: Terms;
  books: VariantsBook[];
};
let listed: Variants | undefined;
export function variants(): Variants {
  listed ??= readPrepared<Variants>("variants.json", "variants");
  return listed;
}
// Each book's variants, with the book as the manifest has it.
export const variantsBooks = () =>
  variants().books.map(({ id, entries }) => {
    const book = manifest().books.find((b) => b.id === id);
    if (!book) {
      throw new Error(`Variants of a book the edition lacks: ${id}`);
    }
    return { book, entries };
  });
export const variantsURL = (book: { id: string }) =>
  `/variants/${book.id.toLowerCase()}`;
export const variantsLink = (book: Book): Link => ({
  text: book.short,
  link: variantsURL(book),
});
export const document = (book: Book, chapter: Chapter) =>
  readPrepared<Document>(
    `books/${book.id}/${chapter.number}.json`,
    `chapter ${book.id} ${chapter.number}`,
  );
export const chapterURL = (book: Book, chapter: Chapter) =>
  chapterPath(book.id, chapter.number);
export const introductionLink = (book: Book) =>
  book.introduction
    ? {
        text: book.introduction.title,
        link: chapterPath(book.id, book.introduction.slug),
      }
    : undefined;
export const bookLinks = (book: Book) => {
  const introduction = introductionLink(book);
  return [
    ...(introduction ? [introduction] : []),
    ...book.chapters.map((chapter) => ({
      text: chapter.label,
      link: chapterURL(book, chapter),
    })),
  ];
};
export const matterURL = (unit: Matter) => `/read/${unit.id.toLowerCase()}`;
export const matterLink = (unit: Matter) => ({
  text: unit.short,
  link: matterURL(unit),
});
// The reader's sections in the book's order, each with its front matter
// before its books.
export const sections = () =>
  Object.entries(SECTIONS).map(([section, title]) => ({
    section,
    title,
    matter: manifest().matter.filter((unit) => unit.section === section),
    books: manifest().books.filter((b) => b.section === section),
  }));
// Every chapter of the edition, in order.
export const chapters = () =>
  manifest().books.flatMap((book) =>
    book.chapters.map((chapter) => ({ book, chapter })),
  );
// A chapter's title and scripture, its verse anchors checked against the inventory.
function page(book: Book, chapter: Chapter) {
  const { html, verses } = renderChapter(
    document(book, chapter),
    chapter.titled,
  );
  if (
    JSON.stringify(verses) !== JSON.stringify(chapter.verses) ||
    new Set(verses).size !== verses.length
  ) {
    throw new Error(
      `Verse anchors disagree with inventory: ${book.id} ${chapter.number}`,
    );
  }
  return {
    title: chapter.titled ? chapter.label : chapterLink(book, chapter).text,
    html,
  };
}
// Every chapter page, rendered once: the paths loader, the pager, and the
// search index all read it.
type Page = { book: Book; chapter: Chapter; title: string; html: string };
let rendered: Page[] | undefined;
export function pages(): Page[] {
  rendered ??= chapters().map(({ book, chapter }) => ({
    book,
    chapter,
    ...page(book, chapter),
  }));
  return rendered;
}
export const chapterLink = (book: Book, chapter: Chapter) => ({
  text: `${book.cited} ${chapter.label}`,
  link: chapterURL(book, chapter),
});

// Book introductions have no chapter or verse identity. Rendered once: the
// paths loader and the search index both read them.
type IntroductionPage = {
  book: Book;
  title: string;
  link: string;
  html: string;
};
let renderedIntroductions: IntroductionPage[] | undefined;
export function introductionPages(): IntroductionPage[] {
  renderedIntroductions ??= manifest().books.flatMap((book) => {
    if (!book.introduction) {
      return [];
    }
    const doc = readPrepared<Document>(
      `books/${book.id}/${book.introduction.slug}.json`,
      `introduction to ${book.id}`,
    );
    const blocks = doc.content.filter(
      (node) => node.type !== "book" && node.marker !== "imt1",
    );
    const html = renderProse(blocks, "introduction");
    return [
      {
        book,
        title: book.introduction.title,
        link: introductionLink(book)!.link,
        html,
      },
    ];
  });
  return renderedIntroductions;
}
// Every unit of front matter, rendered once under its printed title, and
// without it for the search index.
type MatterPage = { unit: Matter; html: string; body: string };
let renderedMatter: MatterPage[] | undefined;
export function matterPages(): MatterPage[] {
  renderedMatter ??= manifest().matter.map((unit) => ({
    unit,
    ...renderMatter(
      readPrepared<Document>(
        `matter/${unit.id}.json`,
        `front matter ${unit.id}`,
      ),
    ),
  }));
  return renderedMatter;
}
type Link = { text: string; link: string };
// The previous and next of a run of pages, by each page's link.
function pager(links: Link[]) {
  const positions = new Map(links.map((p, i) => [p.link, i]));
  return (link: string) => {
    const at = positions.get(link);
    if (at === undefined) {
      throw new Error(`Page in no section of the contents: ${link}`);
    }
    return { prev: links[at - 1] ?? false, next: links[at + 1] ?? false };
  };
}
// Every page of the reader in the book's order: each section's front
// matter, then its chapters. The pager runs through them, while the
// sidebar opens one book. Read from the manifest alone, so that no page
// is rendered to place another.
let readerPager: ReturnType<typeof pager> | undefined;
const neighbours = (link: string) =>
  (readerPager ??= pager(
    sections().flatMap(({ matter, books }) => [
      ...matter.map(matterLink),
      ...books.flatMap((b) => [
        ...(introductionLink(b) ? [introductionLink(b)!] : []),
        ...b.chapters.map((c) => chapterLink(b, c)),
      ]),
    ]),
  ))(link);
// The variants introduction and books, rendered once, each by its link.
// Each entry is anchored by its verse and linked to it where the edition
// has it.
type VariantsPage = { link: string; title: string; html: string };
let renderedVariants: VariantsPage[] | undefined;
const INTRODUCTION: Link = {
  text: "Introduction",
  link: "/variants/introduction",
};
// The sidebar and pager share the introduction followed by the books, read
// from the manifest alone, so that no page is rendered to place another.
export const variantsLinks = (): Link[] => [
  INTRODUCTION,
  ...variantsBooks().map(({ book }) => variantsLink(book)),
];
export function variantsPages(): VariantsPage[] {
  renderedVariants ??= [
    {
      link: INTRODUCTION.link,
      title: INTRODUCTION.text,
      html: variantsIntro(),
    },
    ...variantsBooks().map(({ book, entries }) => {
      const verses = new Map(
        book.chapters.map((c) => [c.number, new Set(c.verses)]),
      );
      return {
        link: variantsURL(book),
        title: `${book.short}: ${variants().title}`,
        html: renderVariants(
          book.id,
          entries,
          (chapter, verse) => verses.get(chapter)?.has(verse) ?? false,
          variants().terms,
        ),
      };
    }),
  ];
  return renderedVariants;
}
// The prose that opens the variants, under the page's title.
export const variantsIntro = () => renderProse(variants().intro, "variants");
// Each generated page's content for the local search index, which reads
// files and so finds nothing of its own for a chapter, a unit of front
// matter or a book's variants; by the page's URL.
let searchable: Map<string, string> | undefined;
const searched = (
  link: string,
  title: string,
  id: string,
  html: string,
): [string, string] => [link, `# ${title} {#${id}}\n\n${html}`];
export function searchContent(relativePath: string): string | undefined {
  searchable ??= new Map([
    ...pages().map((p) =>
      searched(chapterURL(p.book, p.chapter), p.title, "chapter", p.html),
    ),
    ...introductionPages().map((p) =>
      searched(p.link, p.title, "introduction", p.html),
    ),
    ...matterPages().map((p) =>
      searched(matterURL(p.unit), p.unit.title, "matter", p.body),
    ),
    ...variantsPages().map((p) =>
      searched(p.link, p.title, "variants", p.html),
    ),
  ]);
  return searchable.get(`/${relativePath.replace(/\.md$/, "")}`);
}
// The pager runs from the introduction through the books' variants; the
// index is a page of its own, which it does not reach.
export function variantsRoutes() {
  const around = pager(variantsLinks());
  return variantsPages().map(({ link, title, html }) => ({
    params: { book: link.split("/").at(-1)!, title, ...around(link) },
    content: `${heading("variants", title)}\n\n${html}`,
  }));
}
// A unit of front matter's page: its printed title is its heading.
export function matterRoutes() {
  return matterPages().map(({ unit, html }) => ({
    params: {
      unit: unit.id.toLowerCase(),
      title: unit.title,
      ...neighbours(matterURL(unit)),
    },
    content: html,
  }));
}
export function readerPages() {
  const introductions = introductionPages();
  return manifest().books.flatMap((book) => [
    ...introductions
      .filter((p) => p.book === book)
      .map((p) => ({
        params: {
          book: book.id.toLowerCase(),
          chapter: book.introduction!.slug,
          title: p.title,
          ...neighbours(p.link),
        },
        content: `${heading("introduction", p.title)}\n\n${p.html}`,
      })),
    ...pages()
      .filter((p) => p.book === book)
      .map(({ chapter, title, html }) => ({
        params: {
          book: book.id.toLowerCase(),
          chapter: chapter.number,
          title,
          ...neighbours(chapterURL(book, chapter)),
        },
        content: `${heading("chapter", title)}\n\n${html}`,
      })),
  ]);
}
