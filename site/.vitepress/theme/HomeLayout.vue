<script setup lang="ts">
import DefaultTheme from "vitepress/theme-without-fonts";
import HeroQuote from "./HeroQuote.vue";

const { Layout } = DefaultTheme;
</script>

<!-- The quote stands beside the hero, or after the features on narrow screens. -->
<template>
  <Layout>
    <template #home-hero-image>
      <HeroQuote />
    </template>
    <template #home-features-after>
      <div class="features-quote">
        <HeroQuote />
      </div>
    </template>
  </Layout>
</template>
