<script setup lang="ts">
import { onMounted, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useSessionStore } from '@/stores/session';
import { useTheme } from '@/composables/useTheme';

const session = useSessionStore();
const route = useRoute();
const { t } = useI18n();
useTheme(); // applies the persisted light/dark/system choice

onMounted(() => {
  session.loadMeta();
});

// document title = "<page> · <instance name>" (#721) — the BBZ name an operator
// sets in Administration → Instanz shows in the browser tab too.
watch(
  [() => route.name, () => session.instanceName],
  ([name]) => {
    const page = name ? t('shell.pageTitle.' + String(name), '') : '';
    document.title = page ? `${page} · ${session.instanceName}` : session.instanceName;
  },
  { immediate: true },
);
</script>

<template>
  <RouterView />
</template>
