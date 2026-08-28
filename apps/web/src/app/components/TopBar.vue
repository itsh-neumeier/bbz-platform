<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';

const { t } = useI18n();

// Large clock with seconds (mockup §13.1).
const now = ref(new Date());
let timer: number | undefined;
onMounted(() => {
  timer = window.setInterval(() => (now.value = new Date()), 1000);
});
onUnmounted(() => window.clearInterval(timer));

const clock = computed(() =>
  now.value.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
);
</script>

<template>
  <header class="topbar">
    <!--
      The global unaccepted high/critical event alert (mockup §13.7) renders here,
      before the clock, on every page except the workplace page. Added in Phase 1.
    -->
    <div class="topbar__spacer" />
    <time class="topbar__clock" :aria-label="t('comms.availableLines')">{{ clock }}</time>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 1.25rem;
  border-bottom: 1px solid var(--bbz-border);
  background: var(--bbz-surface);
}
.topbar__spacer {
  flex: 1;
}
.topbar__clock {
  font-variant-numeric: tabular-nums;
  font-size: 1.6rem;
  font-weight: 600;
}
</style>
