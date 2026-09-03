<script setup lang="ts">
/**
 * Administration area shell (#721, part of #718). A left sub-navigation over a
 * `<RouterView>` for the sub-pages (Instanz · Benutzer · Verzeichnis ·
 * Integrationen · Handlungsanweisungen · Trigger-Regeln · Technische Endpunkte ·
 * System). Only the sections the user holds a `*.manage`-style permission for
 * are shown; the router guard (`meta.perm`) keeps the rest unreachable.
 */
import { computed } from 'vue';
import { RouterLink, RouterView } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { useSessionStore } from '@/stores/session';
import { ADMIN_SECTIONS } from '@/lib/admin';

const { t } = useI18n();
const session = useSessionStore();

const sections = computed(() => ADMIN_SECTIONS.filter((s) => session.can(s.perm)));
</script>

<template>
  <section class="admin">
    <div class="view-head">
      <div>
        <div class="section-kicker">
          {{ t('admin.kicker') }}
        </div>
        <h1>{{ t('admin.title') }}</h1>
        <p>{{ t('admin.subtitle') }}</p>
      </div>
    </div>

    <div class="admin__body">
      <nav
        class="admin__nav"
        :aria-label="t('admin.navLabel')"
      >
        <RouterLink
          v-for="s in sections"
          :key="s.name"
          :to="{ name: s.name }"
          class="admin__nav-item"
        >
          {{ t('admin.section.' + s.key) }}
        </RouterLink>
      </nav>

      <div class="admin__content">
        <RouterView />
      </div>
    </div>
  </section>
</template>

<style scoped>
.admin {
  display: grid;
  gap: 0.9rem;
  align-content: start;
}
.admin__body {
  display: grid;
  grid-template-columns: 15rem minmax(0, 1fr);
  gap: 1rem;
  align-items: start;
}
.admin__nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  position: sticky;
  top: 0;
}
.admin__nav-item {
  padding: 0.55rem 0.7rem;
  border-radius: var(--bbz-radius);
  border-left: 3px solid transparent;
  color: var(--bbz-text-muted);
  text-decoration: none;
  font-weight: var(--bbz-weight-medium);
  font-size: 0.9rem;
}
.admin__nav-item:hover {
  background: var(--bbz-surface-alt);
  color: var(--bbz-text);
}
.admin__nav-item.router-link-active {
  background: var(--bbz-surface);
  border-left-color: var(--bbz-info);
  color: var(--bbz-text);
  font-weight: var(--bbz-weight-semibold);
}
.admin__content {
  min-width: 0;
}
@media (max-width: 900px) {
  .admin__body {
    grid-template-columns: 1fr;
  }
  .admin__nav {
    position: static;
    flex-flow: row wrap;
  }
}
</style>
