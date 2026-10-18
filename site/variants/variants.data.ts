import { variantsBooks, variantsURL } from "../.vitepress/lib/library.ts";
// Each book with its variants for the index.
const loader = {
  load: () => ({
    books: variantsBooks().map(({ book, entries }) => ({
      id: book.id,
      short: book.short,
      title: book.title,
      count: entries.length,
      url: variantsURL(book),
    })),
  }),
};
declare const data: ReturnType<typeof loader.load>;
export { data };
export default loader;
