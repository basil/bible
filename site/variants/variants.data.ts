import { variantsBooks, variantsURL } from "../.vitepress/lib/library.ts";
// Each book with its variants for the index, counted by verse: an entry of
// the verses one reading changes counts each of them.
const loader = {
  load: () => ({
    books: variantsBooks().map(({ book, entries }) => ({
      id: book.id,
      short: book.short,
      title: book.title,
      count: entries.reduce(
        (n, e) =>
          n +
          (e.through ? parseInt(e.through, 10) - parseInt(e.verse, 10) + 1 : 1),
        0,
      ),
      url: variantsURL(book),
    })),
  }),
};
declare const data: ReturnType<typeof loader.load>;
export { data };
export default loader;
