import {
  bookLinks,
  manifest,
  matterLink,
  sections,
} from "../.vitepress/lib/library.ts";
// The front matter, then each section with its books, as the book has them.
const loader = {
  load: () => ({
    matter: manifest().matter.map((unit) => ({
      ...matterLink(unit),
      title: unit.title,
    })),
    sections: sections().map(({ section, title, books }) => ({
      section,
      title,
      books: books.map((book) => ({
        ...book,
        chapters: bookLinks(book).map((link) => ({
          label: link.text,
          url: link.link,
        })),
      })),
    })),
  }),
};
declare const data: ReturnType<typeof loader.load>;
export { data };
export default loader;
