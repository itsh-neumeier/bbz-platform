<script setup lang="ts">
/**
 * Arbeitsplatz — the landing view (MASTER_PROMPT §13.1). A compact status board:
 * open events by priority, the unaccepted high/critical alert, waiting calls,
 * line status. Everything links into the screen that acts on it. Read-only —
 * degrades to zeros when a feed is unavailable.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useSessionStore } from '@/stores/session';
import { eventsApi, PRIORITY_RANK, type EventListItem, type EventPriority } from '@/lib/events';
import { telephonyApi } from '@/lib/telephony';

const { t } = useI18n();
const session = useSessionStore();

const queue = ref<EventListItem[]>([]);
const alertCount = ref(0);
const ringing = ref(0);
const linesUp = ref(0);
const linesTotal = ref(0);

const PRIORITIES: EventPriority[] = ['critical', 'high', 'medium', 'low'];
const byPriority = computed(() => {
  const m: Record<EventPriority, number> = { critical: 0, high: 0, medium: 0, low: 0 };
  for (const e of queue.value) m[e.priority] += 1;
  return m;
});
const openTotal = computed(() => queue.value.length);
const unassigned = computed(() => queue.value.filter((e) => !e.assignee_id).length);
const worst = computed<EventPriority | null>(() => {
  const present = PRIORITIES.filter((p) => byPriority.value[p] > 0);
  return present.sort((a, b) => PRIORITY_RANK[a] - PRIORITY_RANK[b])[0] ?? null;
});

async function load(): Promise<void> {
  const [q, alert, calls, lines] = await Promise.all([
    eventsApi.workQueue().catch(() => ({ items: [] as EventListItem[] })),
    eventsApi.priorityAlert().catch(() => ({ active: false, events: [] })),
    telephonyApi.ringing().catch(() => ({ items: [], next_cursor: null })),
    telephonyApi.lines().catch(() => ({ lines: [] })),
  ]);
  queue.value = q.items;
  alertCount.value = alert.events.length;
  ringing.value = calls.items.length;
  linesTotal.value = lines.lines.length;
  linesUp.value = lines.lines.filter((l) => l.state === 'in_service').length;
}

let poll: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  void load();
  poll = setInterval(() => void load(), 15_000);
});
onBeforeUnmount(() => clearInterval(poll));
</script>

<template>
  <section class="wp">
    <header class="wp__head">
      <h1>{{ t('nav.workplace') }}</h1>
      <p
        v-if="session.user"
        class="wp__hello"
      >
        {{ t('wp.hello', { name: session.user.display_name }) }}
      </p>
    </header>

    <p
      v-if="alertCount"
      class="wp__alert"
      :class="worst ? 'wp__alert--' + worst : ''"
      role="alert"
    >
      <RouterLink to="/ereignisse">
        {{ t('wp.alert', alertCount) }}
      </RouterLink>
    </p>

    <div class="wp__grid">
      <RouterLink
        to="/ereignisse"
        class="wp__card"
      >
        <span class="wp__n">{{ openTotal }}</span>
        <span class="wp__label">{{ t('wp.openEvents') }}</span>
        <span class="wp__sub">{{ t('wp.unassigned', { n: unassigned }) }}</span>
      </RouterLink>

      <div class="wp__card wp__card--prio">
        <span class="wp__label">{{ t('wp.byPriority') }}</span>
        <ul>
          <li
            v-for="p in PRIORITIES"
            :key="p"
          >
            <span
              class="wp__dot"
              :class="'wp__dot--' + p"
            />
            {{ t('event.priority.' + p) }}
            <b>{{ byPriority[p] }}</b>
          </li>
        </ul>
      </div>

      <RouterLink
        to="/telefonbuch"
        class="wp__card"
      >
        <span class="wp__n">{{ ringing }}</span>
        <span class="wp__label">{{ t('wp.waitingCalls') }}</span>
        <span class="wp__sub">{{ t('wp.lines', { up: linesUp, total: linesTotal }) }}</span>
      </RouterLink>

      <RouterLink
        to="/wetterlage"
        class="wp__card wp__card--link"
      >
        <span class="wp__label">{{ t('nav.weather') }}</span>
        <span class="wp__sub">{{ t('wp.openWeather') }}</span>
      </RouterLink>

      <RouterLink
        to="/monitore"
        class="wp__card wp__card--link"
      >
        <span class="wp__label">{{ t('nav.monitors') }}</span>
        <span class="wp__sub">{{ t('wp.openMonitors') }}</span>
      </RouterLink>

      <RouterLink
        to="/archiv"
        class="wp__card wp__card--link"
      >
        <span class="wp__label">{{ t('nav.archive') }}</span>
        <span class="wp__sub">{{ t('wp.openArchive') }}</span>
      </RouterLink>
    </div>

    <p
      v-if="session.meta"
      class="wp__meta"
    >
      {{ t('wp.node') }}: {{ session.meta.node_id }}
      <span v-if="session.meta.version">· v{{ session.meta.version }}</span>
    </p>
  </section>
</template>

<style scoped>
.wp__head {
  display: flex;
  align-items: baseline;
  gap: 1rem;
  flex-wrap: wrap;
}
.wp h1 {
  margin: 0 0 0.25rem;
  font-size: 1.25rem;
}
.wp__hello {
  color: var(--bbz-text-muted);
  margin: 0;
}
.wp__alert {
  margin: 0.75rem 0;
  padding: 0.5rem 0.8rem;
  border-radius: var(--bbz-radius);
  border-left: 4px solid var(--bbz-prio-high);
  background: var(--bbz-surface-alt);
}
.wp__alert--critical {
  border-left-color: var(--bbz-prio-critical);
}
.wp__alert--high {
  border-left-color: var(--bbz-prio-high);
}
.wp__alert a {
  color: var(--bbz-text);
  font-weight: 600;
}
.wp__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
  gap: 0.75rem;
  margin-top: 1rem;
}
.wp__card {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  padding: 0.9rem 1rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-surface);
  color: var(--bbz-text);
  text-decoration: none;
}
a.wp__card:hover,
a.wp__card:focus-visible {
  border-color: var(--bbz-accent);
  outline: none;
}
.wp__n {
  font-size: 2rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.wp__label {
  font-weight: 600;
}
.wp__sub {
  color: var(--bbz-text-muted);
  font-size: 0.85rem;
}
.wp__card--prio ul {
  list-style: none;
  margin: 0.4rem 0 0;
  padding: 0;
  display: grid;
  gap: 0.2rem;
  font-size: 0.9rem;
}
.wp__card--prio li {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
.wp__card--prio b {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}
.wp__dot {
  width: 0.7rem;
  height: 0.7rem;
  border-radius: 50%;
  flex: none;
}
.wp__dot--critical {
  background: var(--bbz-prio-critical);
}
.wp__dot--high {
  background: var(--bbz-prio-high);
}
.wp__dot--medium {
  background: var(--bbz-prio-medium);
}
.wp__dot--low {
  background: var(--bbz-prio-low);
}
.wp__card--link {
  justify-content: center;
}
.wp__meta {
  margin-top: 1.25rem;
  color: var(--bbz-text-muted);
  font-size: 0.8rem;
}
</style>
