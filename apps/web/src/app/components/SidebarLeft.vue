<script setup lang="ts">
import { computed, ref } from 'vue';
import { RouterLink } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const session = useSessionStore();

// The official DB logo is a licensed asset — dropped in at
// public/brand/db-logo.svg on a build host (see the README there). Until it
// loads, the "DB" wordmark stands in. Never a reconstructed logo (issue #713).
// Runtime path (not a bundler import) so a missing file just 404s → fallback.
const dbLogoUrl = '/brand/db-logo.svg';
const logoOk = ref(true);

const links = computed(() => [
  { to: '/arbeitsplatz', key: 'nav.workplace' },
  { to: '/ereignisse', key: 'nav.events' },
  { to: '/archiv', key: 'nav.archive' },
  { to: '/wetterlage', key: 'nav.weather' },
  { to: '/monitore', key: 'nav.monitors' },
  { to: '/telefonbuch', key: 'nav.phonebook' },
  ...(session.can('workflows.manage_templates')
    ? [{ to: '/admin/workflows', key: 'nav.workflows' }]
    : []),
]);
</script>

<template>
  <nav
    class="sidebar"
    :aria-label="t('app.title')"
  >
    <div class="sidebar__brand">
      <img
        v-if="logoOk"
        class="sidebar__logo"
        :src="dbLogoUrl"
        alt="Deutsche Bahn"
        width="38"
        height="27"
        @error="logoOk = false"
      >
      <span
        v-else
        class="sidebar__db"
        aria-hidden="true"
      >DB</span>
      <span class="sidebar__title">{{ t('app.title') }}</span>
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
  gap: var(--bbz-space-md);
  padding: var(--bbz-space-md);
  height: 100%;
}
.sidebar__brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: var(--bbz-font-head);
  font-weight: var(--bbz-weight-bold);
  padding-bottom: var(--bbz-space-2xs);
  border-bottom: var(--bbz-border-width) solid var(--bbz-border);
}
.sidebar__db {
  background: var(--bbz-db-red);
  color: #fff;
  font-family: var(--bbz-font-head);
  font-weight: var(--bbz-weight-bold);
  padding: 0.15rem 0.4rem;
  border-radius: var(--bbz-radius-sm);
  font-size: var(--bbz-text-sm);
  letter-spacing: 0.03em;
}
.sidebar__logo {
  display: block;
  height: 1.7rem;
  width: auto;
}
.sidebar__title {
  font-size: var(--bbz-text-base);
}
.sidebar__nav {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.sidebar__nav a {
  display: block;
  padding: 0.5rem 0.65rem;
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
  border-left-color: var(--bbz-db-red);
  color: var(--bbz-text);
  font-weight: var(--bbz-weight-semibold);
}
.sidebar__nav a:focus-visible {
  outline: var(--bbz-focus-width) solid var(--bbz-focus-color);
  outline-offset: 2px;
}
.sidebar__foot {
  margin-top: auto;
  font-size: 0.8rem;
  color: var(--bbz-text-muted);
}
</style>
