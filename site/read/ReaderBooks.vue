<script setup lang="ts">
import CardHeading from "../.vitepress/theme/CardHeading.vue";
import { data } from "./books.data.ts";
</script>

<template>
  <div class="book-grid">
    <article
      v-for="page in data.matter"
      :key="page.link"
      class="book-card matter-card"
    >
      <CardHeading
        :id="page.link.split('/').at(-1)!"
        :text="page.text"
        :href="page.link"
      />
      <p v-if="page.title !== page.text">{{ page.title }}</p>
    </article>
  </div>
  <section v-for="section in data.sections" :key="section.section">
    <CardHeading :id="section.section" tag="h2" :text="section.title" />
    <div class="book-grid">
      <article v-for="book in section.books" :key="book.id" class="book-card">
        <CardHeading :id="book.id.toLowerCase()" :text="book.short" />
        <p>{{ book.title }}</p>
        <nav class="chapters" :aria-label="'Contents of ' + book.short">
          <a
            v-for="chapter in book.chapters"
            :key="chapter.url"
            :href="chapter.url"
            >{{ chapter.label }}</a
          >
        </nav>
      </article>
    </div>
  </section>
  <div class="book-grid">
    <article
      v-for="page in data.back"
      :key="page.link"
      class="book-card matter-card back-card"
    >
      <CardHeading
        :id="page.link.split('/').at(-1)!"
        :text="page.text"
        :href="page.link"
      />
      <p v-if="page.title !== page.text">{{ page.title }}</p>
    </article>
  </div>
</template>
