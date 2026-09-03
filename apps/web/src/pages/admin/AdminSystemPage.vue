<script setup lang="ts">
/**
 * System information (#721) — a read-only view of `/api/v1/meta`: build,
 * environment, node identity and the integrations the server discovered.
 * Deeper diagnostics (`/health/details`, cluster status) are a follow-up.
 */
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const session = useSessionStore();

const rows = computed(() => {
  const m = session.meta;
  if (!m) return [];
  return [
    { k: t('admin.system.instance'), v: session.instanceName },
    { k: t('admin.system.service'), v: m.service },
    { k: t('admin.system.version'), v: m.version || '—' },
    { k: t('admin.system.environment'), v: m.environment },
    { k: t('admin.system.node'), v: m.node_id },
    { k: t('admin.system.apiVersion'), v: m.api_version },
  ];
});
</script>

<template>
  <div class="card">
    <div class="card-head">
      <div>
        <div class="card-title">
          {{ t('admin.system.title') }}
        </div>
        <div class="card-subtitle">
          {{ t('admin.system.subtitle') }}
        </div>
      </div>
    </div>
    <div class="card-body">
      <p
        v-if="!session.meta"
        class="muted"
      >
        {{ t('admin.loading') }}
      </p>
      <template v-else>
        <dl class="sys-grid">
          <template
            v-for="r in rows"
            :key="r.k"
          >
            <dt>{{ r.k }}</dt>
            <dd>{{ r.v }}</dd>
          </template>
        </dl>

        <h3 class="sys-h">
          {{ t('admin.system.integrations') }}
        </h3>
        <ul class="sys-tags">
          <li
            v-for="id in session.meta.known_integrations"
            :key="id"
          >
            <span class="tag gray">{{ id }}</span>
          </li>
          <li
            v-if="session.meta.known_integrations.length === 0"
            class="muted"
          >
            {{ t('admin.system.noIntegrations') }}
          </li>
        </ul>
      </template>
    </div>
  </div>
</template>

<style scoped>
.sys-grid {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.4rem 1.2rem;
  margin: 0;
}
.sys-grid dt {
  color: var(--bbz-text-muted);
  font-size: 0.85rem;
}
.sys-grid dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}
.sys-h {
  margin: 1.2rem 0 0.5rem;
  font-size: 0.95rem;
}
.sys-tags {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}
</style>
