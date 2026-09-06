<script setup lang="ts">
/**
 * `/monitore` — the monitor-layout dialog as a routed view so the sidebar nav
 * and the topbar monitor-layout button (both push here) and deep links keep
 * working. The routing UI itself is `MonitorRoutingDialog.vue` (E19-08 / #408);
 * closing it navigates back to the previous view (Arbeitsplatz by default).
 */
import { useRouter } from 'vue-router';
import MonitorRoutingDialog from '@/components/monitor/MonitorRoutingDialog.vue';

const router = useRouter();

function close(): void {
  if (window.history.length > 1) router.back();
  else void router.push('/arbeitsplatz');
}
</script>

<template>
  <MonitorRoutingDialog
    open
    @close="close"
  />
</template>
