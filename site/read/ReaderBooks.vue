<script setup lang="ts">
import CardHeading from "../.vitepress/theme/CardHeading.vue";
import { data as sections } from "./books.data.ts";
</script>

<template>
  <section v-for="section in sections" :key="section.section">
    <CardHeading
      v-if="section.title"
      :id="section.section"
      tag="h2"
      :text="section.title"
    />
    <div class="book-grid">
      <article
        v-for="page in section.matter"
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
</template>
