<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { useSessionStore } from '@/stores/session';
import { useTheme } from '@/composables/useTheme';

const { t } = useI18n();
const router = useRouter();
const session = useSessionStore();
const { theme, cycle } = useTheme();

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

const themeLabel = computed(() =>
  theme.value === 'system'
    ? t('session.themeSystem')
    : theme.value === 'light'
      ? t('session.themeLight')
      : t('session.themeDark'),
);

async function logout(): Promise<void> {
  await session.logout();
  await router.replace({ name: 'login' });
}
</script>

<template>
  <header class="topbar">
    <!-- Global unaccepted high/critical event alert (E07-13) mounts here. -->
    <div class="topbar__alert">
      <slot name="alert" />
    </div>
    <div class="topbar__spacer" />
    <slot name="sync" />
    <button
      type="button"
      class="topbar__btn"
      :aria-label="t('session.theme') + ': ' + themeLabel"
      @click="cycle"
    >
      {{ themeLabel }}
    </button>
    <time
      class="topbar__clock"
      :aria-label="t('comms.availableLines')"
    >{{ clock }}</time>
    <button
      v-if="session.user"
      type="button"
      class="topbar__btn"
      @click="logout"
    >
      {{ t('session.logout') }}
    </button>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: var(--bbz-space-md);
  padding: var(--bbz-space-2xs) var(--bbz-space-xl);
  border-bottom: var(--bbz-border-width) solid var(--bbz-border);
  background: var(--bbz-surface);
  min-height: 3.25rem;
}
.topbar__spacer {
  flex: 1;
}
.topbar__alert:empty {
  display: none;
}
.topbar__clock {
  font-family: var(--bbz-font-head);
  font-variant-numeric: tabular-nums;
  font-size: 1.65rem;
  font-weight: var(--bbz-weight-bold);
  letter-spacing: 0.01em;
  color: var(--bbz-text);
}
.topbar__btn {
  padding: 0.4rem 0.8rem;
  border: var(--bbz-border-width) solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-bg);
  color: var(--bbz-text);
  font-size: var(--bbz-text-sm);
  font-weight: var(--bbz-weight-medium);
  cursor: pointer;
  transition: background-color var(--bbz-transition);
}
.topbar__btn:hover {
  background: var(--bbz-surface-alt);
}
.topbar__btn:focus-visible {
  outline: var(--bbz-focus-width) solid var(--bbz-focus-color);
  outline-offset: 2px;
}
</style>
