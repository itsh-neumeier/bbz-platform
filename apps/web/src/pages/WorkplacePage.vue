<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const session = useSessionStore();
</script>

<template>
  <section>
    <h1>{{ t('nav.workplace') }}</h1>
    <p class="note">{{ t('foundation.notice') }}</p>

    <section aria-labelledby="event-store-heading" class="card">
      <h2 id="event-store-heading">{{ t('workplace.eventStore') }}</h2>
      <p class="note">
        {{ t('workplace.accept') }} · {{ t('workplace.acknowledge') }} ·
        {{ t('workplace.edit') }} · {{ t('workplace.archive') }}
      </p>
    </section>

    <section v-if="session.meta" class="card">
      <h2>meta</h2>
      <dl>
        <dt>node</dt>
        <dd>{{ session.meta.node_id }}</dd>
        <dt>known integrations</dt>
        <dd>{{ session.meta.known_integrations.join(', ') || '—' }}</dd>
      </dl>
    </section>
  </section>
</template>

<style scoped>
.card {
  background: var(--bbz-surface);
  border: 1px solid var(--bbz-border);
  border-radius: 6px;
  padding: 1rem;
  margin-top: 1rem;
}
.note {
  color: var(--bbz-text-muted);
}
dl {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.25rem 1rem;
}
dt {
  font-weight: 600;
}
</style>
