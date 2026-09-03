<script setup lang="ts">
/**
 * The operator shell (MASTER_PROMPT §13.1, V10 mockup `.app`): a three-column
 * grid — fixed left sidebar | content | horizontally resizable right column —
 * with a brand cell + shared topbar across the top and a version footer under
 * the content. The right column carries the comms sidebar (§13.8) over the
 * cross-workplace logbook (§13.1).
 *
 * The shell owns one SSE connection so the priority-alert banner + sync
 * indicator stay live on every page; pages open their own for row-level updates.
 */
import { onMounted, watch } from 'vue';
import LogoCell from './components/LogoCell.vue';
import SidebarLeft from './components/SidebarLeft.vue';
import TopBar from './components/TopBar.vue';
import VersionBar from './components/VersionBar.vue';
import CommsSidebar from './components/CommsSidebar.vue';
import GlobalLog from './components/GlobalLog.vue';
import PriorityAlertBanner from '@/components/events/PriorityAlertBanner.vue';
import SyncStatus from '@/components/events/SyncStatus.vue';
import { useEventStream } from '@/composables/useEventStream';
import { useEventsStore } from '@/stores/events';
import { useCallsStore } from '@/stores/calls';
import { useSessionStore } from '@/stores/session';

const events = useEventsStore();
const calls = useCallsStore();
const session = useSessionStore();
const { status: sync, lastSeq } = useEventStream((f) => {
  events.onStreamFrame(f.type, f.data.aggregate_id as string | undefined);
  calls.onStreamFrame(f.type);
});
watch([sync, lastSeq], ([s, seq]) => events.setSync(s, seq), { immediate: true });

// the shell keeps the priority alert live on every page (§13.7)
onMounted(() => void events.loadAlert());
</script>

<template>
  <div
    class="shell"
    :style="{ '--bbz-comms-width': session.commsWidth + 'px' }"
  >
    <LogoCell class="shell__logo" />
    <TopBar class="shell__topbar">
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

    <SidebarLeft class="shell__sidebar" />

    <main class="shell__content">
      <RouterView />
    </main>
    <VersionBar class="shell__footer" />

    <aside class="shell__right">
      <CommsSidebar class="shell__comms" />
      <GlobalLog class="shell__glog" />
    </aside>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: var(--bbz-sidebar-width) minmax(0, 1fr) var(--bbz-comms-width);
  grid-template-rows: var(--bbz-header-height) minmax(0, 1fr) var(--bbz-footer-height);
  height: 100vh;
  background: var(--bbz-bg);
  color: var(--bbz-text);
  /* the DB signature: a thin brand-red rule across the top of the application */
  border-top: 3px solid var(--bbz-db-red);
}
.shell__logo {
  grid-column: 1;
  grid-row: 1;
}
.shell__topbar {
  grid-column: 2 / 4;
  grid-row: 1;
  min-width: 0;
}
.shell__sidebar {
  grid-column: 1;
  grid-row: 2 / 4;
  min-height: 0;
}
.shell__content {
  grid-column: 2;
  grid-row: 2;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: var(--bbz-space-md) var(--bbz-space-lg);
  background: var(--bbz-bg);
}
.shell__footer {
  grid-column: 2;
  grid-row: 3;
}
.shell__right {
  grid-column: 3;
  grid-row: 2 / 4;
  min-height: 0;
  display: grid;
  grid-template-rows: 54fr 46fr;
  background: var(--bbz-bg);
  border-left: var(--bbz-border-width) solid var(--bbz-border);
}
.shell__comms,
.shell__glog {
  min-height: 0;
  overflow: hidden;
}
.shell__glog {
  border-top: var(--bbz-border-width) solid var(--bbz-border);
}
</style>
