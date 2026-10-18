<script setup lang="ts">
// A heading of the index pages, with the default theme's permalink, and
// linked where its card opens a page.
defineProps<{ id: string; text: string; tag?: "h2" | "h3"; href?: string }>();
</script>

<template>
  <component :is="tag ?? 'h3'" :id="id" tabindex="-1">
    <a v-if="href" :href="href">{{ text }}</a
    ><template v-else>{{ text }}</template
    ><a
      class="header-anchor"
      :href="`#${id}`"
      :aria-label="`Permalink to “${text}”`"
    />
  </component>
</template>
