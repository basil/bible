import { bookLinks, matterLink, sections } from "../.vitepress/lib/library.ts";
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
        chapters: bookLinks(book).map((link) => ({
          label: link.text,
          url: link.link,
        })),
      })),
    })),
};
declare const data: ReturnType<typeof loader.load>;
export { data };
export default loader;
