<script setup lang="ts">
import { data } from "./compare.data.ts";
</script>

<template>
  <div class="comparisons">
    <details
      v-for="(entry, index) in data"
      :key="entry.reference"
      class="comparison"
      :open="index === 0"
    >
      <summary class="comparison-toggle">
        <span>{{ entry.reference }}</span>
        <span class="comparison-chevron" aria-hidden="true"></span>
      </summary>
      <dl>
        <div class="comparison-reading comparison-old">
          <dt>
            <span class="comparison-label">KJV</span> {{ entry.kjvReference }}
          </dt>
          <dd>
            <span
              v-for="(span, part) in entry.kjv"
              :key="part"
              :class="{ 'comparison-changed': span.changed }"
              >{{ span.text }}</span
            >
          </dd>
        </div>
        <div v-if="entry.osb" class="comparison-reading comparison-old">
          <dt>
            <span class="comparison-label">OSB</span> {{ entry.kjvReference }}
          </dt>
          <dd>
            <span
              v-for="(span, part) in entry.osb"
              :key="part"
              :class="{ 'comparison-changed': span.changed }"
              >{{ span.text }}</span
            >
          </dd>
        </div>
        <div class="comparison-reading comparison-new">
          <dt>
            <span class="comparison-label">OLEB</span> {{ entry.reference }}
          </dt>
          <dd>
            <span
              v-for="(span, part) in entry.oleb"
              :key="part"
              :class="{ 'comparison-changed': span.changed }"
              >{{ span.text }}</span
            >
          </dd>
        </div>
      </dl>
    </details>
  </div>
</template>
