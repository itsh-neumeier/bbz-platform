<script setup lang="ts">
/**
 * Fixed left sidebar (MASTER_PROMPT §13.2, V10 mockup `.sidebar`): a
 * workspace-status header, the navigation with live badges, and the
 * logged-in-user card (with the theme + logout controls that the V10 topbar
 * does not carry).
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useSessionStore } from '@/stores/session';
import { useEventsStore } from '@/stores/events';
import { useCallsStore } from '@/stores/calls';
import { useTheme } from '@/composables/useTheme';
import { weatherApi } from '@/lib/weather';
import { canSeeAdmin } from '@/lib/admin';

const { t } = useI18n();
const router = useRouter();
const session = useSessionStore();
const events = useEventsStore();
const calls = useCallsStore();
const { theme, cycle } = useTheme();

const weatherWarnings = ref(0);

const openEvents = computed(() => events.sortedQueue.length);
const waitingCalls = computed(() => calls.ringing.length);

const links = computed(() => [
  { to: '/arbeitsplatz', key: 'nav.workplace', icon: '⌂' },
  { to: '/ereignisse', key: 'nav.events', icon: '◉', badge: openEvents.value },
  { to: '/telefonbuch', key: 'nav.phonebook', icon: '▤', badge: waitingCalls.value },
  { to: '/wetterlage', key: 'nav.weather', icon: '☁', badge: weatherWarnings.value },
  { to: '/monitore', key: 'nav.monitors', icon: '▦' },
  ...(canSeeAdmin(session.can) ? [{ to: '/admin', key: 'nav.admin', icon: '⚙' }] : []),
]);

const initials = computed(() => {
  const n = session.user?.display_name ?? '';
  return (
    n
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]!.toUpperCase())
      .join('') || '·'
  );
});

const themeLabel = computed(() =>
  theme.value === 'system'
    ? t('session.themeSystem')
    : theme.value === 'light'
      ? t('session.themeLight')
      : t('session.themeDark'),
);

async function loadWarnings(): Promise<void> {
  try {
    weatherWarnings.value = (await weatherApi.alerts()).alerts.length;
  } catch {
    /* leave the badge at 0 */
  }
}

async function logout(): Promise<void> {
  await session.logout();
  await router.replace({ name: 'login' });
}

let poll: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  void events.loadQueue();
  void loadWarnings();
  poll = setInterval(() => void loadWarnings(), 60_000);
});
onBeforeUnmount(() => clearInterval(poll));
watch(
  () => events.lastSeq,
  () => void events.loadQueue(),
);
</script>

<template>
  <nav
    class="sidebar"
    :aria-label="t('nav.label')"
  >
    <div class="sidebar__status">
      <span
        class="sidebar__orb"
        aria-hidden="true"
      />
      <div>
        <b>{{ t('app.workplaceActive') }}</b>
        <small>{{ session.instanceName }}</small>
        <span class="sidebar__ready">
          <span
            class="sidebar__ready-dot"
            aria-hidden="true"
          />
          {{ t('app.systemsReady') }}
        </span>
      </div>
    </div>

    <ul class="sidebar__nav">
      <li
        v-for="l in links"
        :key="l.to"
      >
        <RouterLink :to="l.to">
          <span
            class="sidebar__icon"
            aria-hidden="true"
          >{{ l.icon }}</span>
          <span class="sidebar__label">{{ t(l.key) }}</span>
          <span
            v-if="l.badge"
            class="sidebar__badge"
          >{{ l.badge }}</span>
        </RouterLink>
      </li>
    </ul>

    <div class="sidebar__user">
      <span
        class="sidebar__avatar"
        aria-hidden="true"
      >{{ initials }}</span>
      <div class="sidebar__user-copy">
        <b>{{ session.user?.display_name ?? '—' }}</b>
        <small>{{ session.instanceName }}</small>
        <span class="sidebar__user-actions">
          <button
            type="button"
            class="btn ghost sm"
            :aria-label="t('session.theme') + ': ' + themeLabel"
            @click="cycle"
          >
            {{ themeLabel }}
          </button>
          <button
            v-if="session.user"
            type="button"
            class="btn ghost sm"
            @click="logout"
          >
            {{ t('session.logout') }}
          </button>
        </span>
      </div>
    </div>
  </nav>
</template>

<style scoped>
.sidebar {
  display: grid;
  grid-template-rows: auto 1fr auto;
  height: 100%;
  min-height: 0;
  background: var(--bbz-bg);
  border-right: var(--bbz-border-width) solid var(--bbz-border);
}
.sidebar__status {
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  padding: 0.85rem 0.9rem;
  border-bottom: var(--bbz-border-width) solid var(--bbz-border);
}
.sidebar__orb {
  width: 0.7rem;
  height: 0.7rem;
  margin-top: 0.15rem;
  border-radius: 50%;
  flex: none;
  background: var(--bbz-success);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--bbz-success) 18%, transparent);
}
.sidebar__status b {
  display: block;
  font-size: 0.8rem;
}
.sidebar__status small {
  display: block;
  color: var(--bbz-text-muted);
  font-size: 0.68rem;
  margin-top: 2px;
}
.sidebar__ready {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 5px;
  color: var(--bbz-success-text);
  font-size: 0.66rem;
  font-weight: var(--bbz-weight-semibold);
}
.sidebar__ready-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bbz-success);
}
.sidebar__nav {
  list-style: none;
  margin: 0;
  padding: 0.6rem 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 3px;
  overflow: auto;
}
.sidebar__nav a {
  display: grid;
  grid-template-columns: 1.4rem 1fr auto;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 0.6rem;
  border-radius: var(--bbz-radius);
  border-left: 3px solid transparent;
  color: var(--bbz-text-muted);
  text-decoration: none;
  font-weight: var(--bbz-weight-medium);
  transition: background-color var(--bbz-transition);
}
.sidebar__nav a:hover {
  background: var(--bbz-surface-alt);
  color: var(--bbz-text);
}
.sidebar__nav a.router-link-active {
  background: var(--bbz-surface);
  border-left-color: var(--bbz-info);
  color: var(--bbz-text);
  font-weight: var(--bbz-weight-semibold);
}
.sidebar__icon {
  text-align: center;
  font-size: 1.05rem;
  opacity: 0.9;
}
.sidebar__badge {
  min-width: 1.35rem;
  height: 1.35rem;
  padding: 0 0.35rem;
  border-radius: 0.7rem;
  background: var(--bbz-db-red);
  color: #fff;
  font-size: 0.66rem;
  font-weight: var(--bbz-weight-bold);
  display: grid;
  place-items: center;
  font-variant-numeric: tabular-nums;
}
.sidebar__user {
  display: flex;
  gap: 0.6rem;
  align-items: flex-start;
  padding: 0.8rem 0.85rem;
  border-top: var(--bbz-border-width) solid var(--bbz-border);
  background: var(--bbz-surface);
}
.sidebar__avatar {
  width: 2.4rem;
  height: 2.4rem;
  border-radius: 50%;
  flex: none;
  display: grid;
  place-items: center;
  background: var(--bbz-surface-alt);
  border: var(--bbz-border-width) solid var(--bbz-border-strong);
  font-family: var(--bbz-font-head);
  font-weight: var(--bbz-weight-bold);
  font-size: 0.8rem;
}
.sidebar__user-copy {
  min-width: 0;
}
.sidebar__user-copy b {
  display: block;
  font-size: 0.8rem;
}
.sidebar__user-copy small {
  display: block;
  color: var(--bbz-text-muted);
  font-size: 0.66rem;
  margin-top: 2px;
}
.sidebar__user-actions {
  display: flex;
  gap: 0.3rem;
  margin-top: 0.5rem;
  flex-wrap: wrap;
}
</style>
