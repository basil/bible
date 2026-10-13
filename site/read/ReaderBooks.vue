<script setup lang="ts">
import { data as sections } from "./books.data.ts";
</script>

<template>
  <section v-for="section in sections" :key="section.title">
    <h2>{{ section.title }}</h2>
    <div class="book-grid">
      <article v-for="book in section.books" :key="book.id" class="book-card">
        <h3>{{ book.short }}</h3>
        <p>{{ book.title }}</p>
        <nav class="chapters" :aria-label="'Chapters of ' + book.short">
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
