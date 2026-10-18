import { chapterURL, matterLink, sections } from "../.vitepress/lib/library.ts";
// Each section with its front matter and its books, as the book has them.
const loader = {
  load: () =>
    sections().map(({ section, title, matter, books }) => ({
      section,
      title,
      matter: matter.map((unit) => ({
        ...matterLink(unit),
        title: unit.title,
      })),
      books: books.map((book) => ({
        ...book,
        chapters: book.chapters.map((c) => ({
          label: c.label,
          url: chapterURL(book, c),
        })),
      })),
    })),
};
declare const data: ReturnType<typeof loader.load>;
export { data };
export default loader;
