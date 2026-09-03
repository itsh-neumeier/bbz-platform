<script setup lang="ts">
import { onMounted } from 'vue';
import { useSessionStore } from '@/stores/session';
import { useTheme } from '@/composables/useTheme';

const session = useSessionStore();
useTheme(); // applies the persisted light/dark/system choice

onMounted(() => {
  session.loadMeta();
});
</script>

<template>
  <RouterView />
</template>
