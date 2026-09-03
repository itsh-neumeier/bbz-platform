<script setup lang="ts">
/**
 * `/ereignisse/:id` and `/archiv/:id` — a thin route wrapper around
 * `EventProcessingPanel` (the same view is rendered inline under the
 * Ereignisspeicher on the Arbeitsplatz, #716). Deep-link entry point.
 */
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import EventProcessingPanel from '@/components/events/EventProcessingPanel.vue';

const route = useRoute();
const id = computed(() => String(route.params.id));
</script>

<template>
  <EventProcessingPanel
    :key="id"
    :event-id="id"
    standalone
  />
</template>
