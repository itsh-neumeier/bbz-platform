<script setup lang="ts">
/**
 * Layout: fixed left sidebar | center content | horizontally resizable right
 * comms sidebar, with a shared topbar (MASTER_PROMPT §13.1). The shell owns one
 * SSE connection that keeps the priority-alert banner + sync indicator live on
 * every page; the queue page opens its own for the row-level updates.
 */
import { onMounted, watch } from 'vue';
import SidebarLeft from './components/SidebarLeft.vue';
import TopBar from './components/TopBar.vue';
import CommsSidebar from './components/CommsSidebar.vue';
import PriorityAlertBanner from '@/components/events/PriorityAlertBanner.vue';
import SyncStatus from '@/components/events/SyncStatus.vue';
import { useEventStream } from '@/composables/useEventStream';
import { useEventsStore } from '@/stores/events';

const events = useEventsStore();
const { status: sync, lastSeq } = useEventStream((f) =>
  events.onStreamFrame(f.type, f.data.aggregate_id as string | undefined),
);
watch([sync, lastSeq], ([s, seq]) => events.setSync(s, seq), { immediate: true });

onMounted(() => events.loadAlert());
</script>

<template>
  <div class="shell">
    <SidebarLeft class="shell__sidebar" />
    <div class="shell__main">
      <TopBar>
        <template #alert>
          <PriorityAlertBanner />
        </template>
        <template #sync>
          <SyncStatus
            :state="sync"
            :seq="lastSeq"
          />
        </template>
      </TopBar>
      <div class="shell__body">
        <main class="shell__content">
          <RouterView />
        </main>
        <CommsSidebar class="shell__comms" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: var(--bbz-sidebar-width) 1fr;
  min-height: 100vh;
}
.shell__sidebar {
  background: var(--bbz-surface);
  border-right: 1px solid var(--bbz-border);
}
.shell__main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.shell__body {
  display: grid;
  grid-template-columns: 1fr var(--bbz-comms-width);
  flex: 1;
  min-height: 0;
}
.shell__content {
  padding: 1rem 1.25rem;
  overflow: auto;
}
.shell__comms {
  background: var(--bbz-surface);
  border-left: 1px solid var(--bbz-border);
  overflow: auto;
}
</style>
