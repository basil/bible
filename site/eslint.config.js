import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import vue from "eslint-plugin-vue";
import { defineConfig, globalIgnores } from "eslint/config";
import tseslint from "typescript-eslint";

export default defineConfig(
  globalIgnores([".vitepress/dist/", ".vitepress/cache/", ".vitepress/.temp/"]),
  {
    files: ["**/*.{js,ts,vue}"],
    extends: [js.configs.recommended, tseslint.configs.recommended],
  },
  {
    files: ["**/*.vue"],
    extends: [vue.configs["flat/recommended"]],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
    // The components' scripts are TypeScript: leave names to vue-tsc, as
    // typescript-eslint does for .ts files.
    rules: tseslint.configs.eslintRecommended.rules,
  },
  prettier,
  // After Prettier's config, which turns these off; ESLint runs before
  // Prettier, so it still sees an unexpected line break.
  { rules: { curly: "error", "no-unexpected-multiline": "error" } },
);
