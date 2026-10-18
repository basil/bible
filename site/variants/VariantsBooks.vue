<script setup lang="ts">
import CardHeading from "../.vitepress/theme/CardHeading.vue";
import { data } from "./variants.data.ts";
</script>

<template>
  <div class="book-grid">
    <article v-for="book in data.books" :key="book.id" class="book-card">
      <CardHeading
        :id="book.id.toLowerCase()"
        :text="book.short"
        :href="book.url"
      />
      <p>{{ book.title }}</p>
      <p>{{ book.count }} {{ book.count === 1 ? "verse" : "verses" }}</p>
    </article>
  </div>
</template>
