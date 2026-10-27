import {
  bookLinks,
  manifest,
  matterLink,
  sections,
  type Matter,
} from "../.vitepress/lib/library.ts";
// The front matter, then each section with its books, then the back
// matter, as the book has them.
const card = (unit: Matter) => ({ ...matterLink(unit), title: unit.title });
const loader = {
  load: () => ({
    matter: manifest().matter.map(card),
    back: manifest().back.map(card),
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
