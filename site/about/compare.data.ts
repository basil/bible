import { readFileSync } from "node:fs";
import { directory } from "../.vitepress/lib/library.ts";
// The passages, their quotations and highlights, as the build compares them.
const loader = {
  load: () =>
    JSON.parse(readFileSync(`${directory}/comparisons.json`, "utf8")) as {
      reference: string;
      kjvReference: string;
      kjv: { text: string; changed: boolean }[];
      oleb: { text: string; changed: boolean }[];
      osb?: { text: string; changed: boolean }[];
    }[],
};
declare const data: ReturnType<typeof loader.load>;
export { data };
export default loader;
