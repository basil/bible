import { manifest, chapterURL, SECTIONS } from "../.vitepress/lib/library.ts";
export default {
  load() {
    const books = manifest().books;
    return Object.entries(SECTIONS).map(([section, title]) => ({
      title,
      books: books
        .filter((book) => book.section === section)
        .map((book) => ({
          ...book,
          chapters: book.chapters.map((c) => ({
            label: c.label,
            url: chapterURL(book, c),
          })),
        })),
    }));
  },
};
