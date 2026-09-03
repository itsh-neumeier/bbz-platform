<script setup lang="ts">
/**
 * Shared topbar over content + comms column (MASTER_PROMPT §13.1, V10 mockup
 * `.topbar`): breadcrumb + page title on the left; the unaccepted-priority
 * alert, the large clock with seconds, the available-lines readout and the
 * monitor-layout button on the right (§13.7 — the alert sits *before* the
 * clock). Theme + logout live in the sidebar user card.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import { telephonyApi } from '@/lib/telephony';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const session = useSessionStore();

/** route name → the sidebar section it belongs to, for the breadcrumb tail */
const SECTION: Record<string, string> = {
  workplace: 'nav.workplace',
  events: 'nav.events',
  'event-detail': 'nav.events',
  'archive-detail': 'nav.archive',
  weather: 'nav.weather',
  monitors: 'nav.monitors',
  phonebook: 'nav.phonebook',
  'workflow-admin': 'nav.admin',
  'admin-instance': 'nav.admin',
  'admin-users': 'nav.admin',
  'admin-directory': 'nav.admin',
  'admin-integrations': 'nav.admin',
  'admin-triggers': 'nav.admin',
  'admin-endpoints': 'nav.admin',
  'admin-system': 'nav.admin',
};

const now = ref(new Date());
let timer: number | undefined;
const linesFree = ref<number | null>(null);
const linesTotal = ref<number | null>(null);
let linesTimer: number | undefined;

async function loadLines(): Promise<void> {
  try {
    const { lines } = await telephonyApi.lines();
    linesTotal.value = lines.length;
    linesFree.value = lines.filter((l) => l.state === 'in_service').length;
  } catch {
    /* the readout just shows — */
  }
}

onMounted(() => {
  timer = window.setInterval(() => (now.value = new Date()), 1000);
  void loadLines();
  linesTimer = window.setInterval(loadLines, 30_000);
});
onUnmounted(() => {
  window.clearInterval(timer);
  window.clearInterval(linesTimer);
});

const dateText = computed(() =>
  now.value
    .toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' })
    .replace(',', ' ·'),
);
const timeText = computed(() =>
  now.value.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
);

const pageTitle = computed(() =>
  t('shell.pageTitle.' + String(route.name ?? 'workplace'), t('shell.pageTitle.workplace')),
);
const crumb = computed(
  () =>
    `${session.instanceShortName} · ${t(SECTION[String(route.name ?? 'workplace')] ?? 'nav.workplace')}`,
);
</script>

<template>
  <header class="topbar">
    <div class="topbar__left">
      <div class="topbar__crumb">
        {{ crumb }}
      </div>
      <div class="topbar__title">
        {{ pageTitle }}
      </div>
    </div>

    <div class="topbar__right">
      <div class="topbar__alert">
        <slot name="alert" />
      </div>
      <slot name="sync" />

      <div
        class="topbar__clock"
        :aria-label="dateText + ' ' + timeText"
      >
        <span class="topbar__date">{{ dateText }}</span>
        <span class="topbar__time">{{ timeText }}</span>
      </div>

      <span
        class="topbar__sep"
        aria-hidden="true"
      />

      <div
        class="topbar__lines"
        :aria-label="t('shell.availableLines')"
      >
        <span
          class="topbar__lines-icon"
          aria-hidden="true"
        >☎</span>
        <span>
          <small>{{ t('shell.availableLines') }}</small>
          <strong>{{ linesFree ?? '—' }}<span v-if="linesTotal !== null">/{{ linesTotal }}</span></strong>
        </span>
      </div>

      <button
        type="button"
        class="topbar__monitor"
        :aria-label="t('shell.monitorLayoutOpen')"
        @click="router.push('/monitore')"
      >
        <span aria-hidden="true">▦</span>
        <span>{{ t('shell.monitorLayout') }}</span>
      </button>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0 1rem 0 1.25rem;
  height: 100%;
  background: var(--bbz-surface);
  border-bottom: var(--bbz-border-width) solid var(--bbz-border);
  min-width: 0;
}
.topbar__left {
  min-width: 0;
}
.topbar__crumb {
  color: var(--bbz-text-subtle);
  font-size: 0.7rem;
  margin-bottom: 3px;
}
.topbar__title {
  font-family: var(--bbz-font-head);
  font-size: 1.3rem;
  font-weight: var(--bbz-weight-bold);
  letter-spacing: -0.02em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.topbar__right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.9rem;
  min-width: max-content;
}
.topbar__alert:empty {
  display: none;
}
.topbar__clock {
  text-align: right;
  line-height: 1.05;
  min-width: 9.5rem;
}
.topbar__date {
  display: block;
  font-size: 0.7rem;
  color: var(--bbz-text-muted);
  margin-bottom: 4px;
}
.topbar__time {
  display: block;
  font-family: var(--bbz-font-numeric);
  font-variant-numeric: tabular-nums;
  font-size: 1.55rem;
  font-weight: var(--bbz-weight-bold);
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.topbar__sep {
  width: 1px;
  height: 2.75rem;
  background: var(--bbz-border);
  flex: 0 0 1px;
}
.topbar__lines {
  min-width: 8rem;
  border: var(--bbz-border-width) solid var(--bbz-border);
  background: var(--bbz-surface-alt);
  border-radius: var(--bbz-radius);
  padding: 0.4rem 0.6rem;
  display: grid;
  grid-template-columns: 1.5rem 1fr;
  align-items: center;
  gap: 0.5rem;
}
.topbar__lines-icon {
  display: grid;
  place-items: center;
  font-size: 1rem;
}
.topbar__lines small {
  display: block;
  color: var(--bbz-text-muted);
  font-size: 0.62rem;
}
.topbar__lines strong {
  display: block;
  font-size: 1.15rem;
  font-variant-numeric: tabular-nums;
  margin-top: 1px;
}
.topbar__monitor {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  height: 3.1rem;
  min-width: 5rem;
  padding: 0 0.5rem;
  border-radius: var(--bbz-radius);
}
.topbar__monitor > span:first-child {
  font-size: 1.1rem;
}
.topbar__monitor > span:last-child {
  font-size: 0.68rem;
  color: var(--bbz-text-muted);
}
@media (max-width: 1280px) {
  .topbar__crumb {
    display: none;
  }
  .topbar__sep,
  .topbar__lines small {
    display: none;
  }
  .topbar__time {
    font-size: 1.3rem;
  }
}
@media (max-width: 1000px) {
  .topbar__date {
    display: none;
  }
}
</style>
