<script setup lang="ts">
/**
 * Layout skeleton from the mockup (MASTER_PROMPT §13.1):
 * fixed left sidebar | center content | horizontally resizable right comms sidebar,
 * with a shared topbar spanning content + comms.
 *
 * Foundation phase: structure, tokens, keyboard-resizable comms sidebar and the
 * reduced-motion contract. No business widgets yet.
 */
import SidebarLeft from './components/SidebarLeft.vue';
import TopBar from './components/TopBar.vue';
import CommsSidebar from './components/CommsSidebar.vue';
</script>

<template>
  <div class="shell">
    <SidebarLeft class="shell__sidebar" />
    <div class="shell__main">
      <TopBar />
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
