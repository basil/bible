import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderChapter, escape, type Document } from "./usj.ts";
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
  chapters: Chapter[];
};
export const directory = fileURLToPath(
  new URL("../../../build/web/", import.meta.url),
);
type Manifest = { books: Book[] };
export const SECTIONS: Record<string, string> = {
  old_testament: "Old Testament",
  new_testament: "New Testament",
};
// Read once: every chapter page and the navigation ask for it.
let prepared: Manifest | undefined;
export function manifest(): Manifest {
  if (!prepared) {
    try {
      prepared = JSON.parse(
        readFileSync(`${directory}/manifest.json`, "utf8"),
      ) as Manifest;
    } catch (error) {
      throw new Error(
        "Cannot read the prepared Bible; run make web before building or serving the site.",
        { cause: error },
      );
    }
  }
  return prepared;
}
export const document = (book: Book, chapter: Chapter) =>
  JSON.parse(
    readFileSync(
      `${directory}/books/${book.id}/${chapter.number}.json`,
      "utf8",
    ),
  ) as Document;
export const chapterURL = (book: Book, chapter: Chapter) =>
  `/read/${book.id.toLowerCase()}/${chapter.number}`;
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
    title: chapter.titled ? chapter.label : `${book.short} ${chapter.label}`,
    html,
  };
}
// Every chapter page, rendered once: the paths loader, the pager and the
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
  text: `${book.short} ${chapter.label}`,
  link: chapterURL(book, chapter),
});
export function chapterSearchContent(relativePath: string): string | undefined {
  const url = `/${relativePath.replace(/\.md$/, "")}`;
  const found = pages().find((p) => chapterURL(p.book, p.chapter) === url);
  return found && `# ${found.title} {#chapter}\n\n${found.html}`;
}
// The pager runs through the whole Bible, while the sidebar opens one book.
export function readerPages() {
  const all = pages();
  const neighbour = (p?: Page) => (p ? chapterLink(p.book, p.chapter) : false);
  return all.map(({ book, chapter, title, html }, i) => ({
    params: {
      book: book.id.toLowerCase(),
      chapter: chapter.number,
      title,
      prev: neighbour(all[i - 1]),
      next: neighbour(all[i + 1]),
    },
    content: `<h1 id="chapter">${escape(title)}</h1>\n\n${html}`,
  }));
}
