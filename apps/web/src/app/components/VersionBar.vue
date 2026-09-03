<script setup lang="ts">
/**
 * The thin status footer under the content column (V10 mockup `.versionbar`).
 * Version / environment / serving node — from `/meta` (session store).
 */
import { useI18n } from 'vue-i18n';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const session = useSessionStore();
</script>

<template>
  <footer class="versionbar">
    <template v-if="session.meta">
      <span>{{ t('versionbar.version', { v: session.meta.version || '—' }) }}</span>
      <span aria-hidden="true">·</span>
      <span>{{ t('versionbar.env.' + session.meta.environment, session.meta.environment) }}</span>
      <span aria-hidden="true">·</span>
      <span>{{ t('versionbar.node', { node: session.meta.node_id }) }}</span>
    </template>
    <span v-else>{{ t('versionbar.offline') }}</span>
  </footer>
</template>

<style scoped>
.versionbar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  height: 100%;
  padding: 0 1rem;
  background: var(--bbz-surface);
  border-top: var(--bbz-border-width) solid var(--bbz-border);
  border-right: var(--bbz-border-width) solid var(--bbz-border);
  color: var(--bbz-text-muted);
  font-size: 0.72rem;
  letter-spacing: 0.01em;
  white-space: nowrap;
  overflow: hidden;
}
</style>
