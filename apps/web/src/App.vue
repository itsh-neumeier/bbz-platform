<script setup lang="ts">
import { onMounted } from 'vue';
import { useSessionStore } from '@/stores/session';
import AppShell from '@/app/AppShell.vue';

const session = useSessionStore();

onMounted(() => {
  // Best-effort; the shell renders regardless of backend availability.
  session.loadMeta().catch(() => undefined);
});
</script>

<template>
  <AppShell />
</template>
