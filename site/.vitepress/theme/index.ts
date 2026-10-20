import type { Theme } from "vitepress";
import DefaultTheme from "vitepress/theme-without-fonts";
import HomeLayout from "./HomeLayout.vue";
// The fonts the image installed for the edition, from build/web/fonts (see bible.web).
import "@edition-fonts/fonts.css";
import "./custom.css";
export default { extends: DefaultTheme, Layout: HomeLayout } satisfies Theme;
