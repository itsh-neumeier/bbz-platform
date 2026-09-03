<script setup lang="ts">
import { RouterLink } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const session = useSessionStore();

const links = [
  { to: '/arbeitsplatz', key: 'nav.workplace' },
  { to: '/ereignisse', key: 'nav.events' },
  { to: '/archiv', key: 'nav.archive' },
  { to: '/wetterlage', key: 'nav.weather' },
  { to: '/monitore', key: 'nav.monitors' },
  { to: '/telefonbuch', key: 'nav.phonebook' },
];
</script>

<template>
  <nav
    class="sidebar"
    :aria-label="t('app.title')"
  >
    <div class="sidebar__brand">
      <span
        class="sidebar__db"
        aria-hidden="true"
      >DB</span>
      <span>{{ t('app.title') }}</span>
    </div>

    <ul class="sidebar__nav">
      <li
        v-for="l in links"
        :key="l.to"
      >
        <RouterLink :to="l.to">
          {{ t(l.key) }}
        </RouterLink>
      </li>
    </ul>

    <div class="sidebar__foot">
      <p>{{ t('app.workplaceActive') }}</p>
      <p v-if="session.meta">
        node: {{ session.meta.node_id }} · v{{ session.meta.version }}
      </p>
    </div>
  </nav>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1rem;
  height: 100%;
}
.sidebar__brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 700;
}
.sidebar__db {
  background: var(--bbz-db-red);
  color: #fff;
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  font-size: 0.8rem;
}
.sidebar__nav {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.sidebar__nav a {
  display: block;
  padding: 0.5rem 0.6rem;
  border-radius: 4px;
  color: var(--bbz-text);
  text-decoration: none;
}
.sidebar__nav a.router-link-active {
  background: color-mix(in srgb, var(--bbz-accent) 15%, transparent);
  font-weight: 600;
}
.sidebar__nav a:focus-visible {
  outline: 2px solid var(--bbz-accent);
  outline-offset: 2px;
}
.sidebar__foot {
  margin-top: auto;
  font-size: 0.8rem;
  color: var(--bbz-text-muted);
}
</style>
