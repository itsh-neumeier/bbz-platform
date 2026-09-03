<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const session = useSessionStore();

// Horizontally resizable comms sidebar with a persisted width and a
// keyboard-operable handle — operation must not rely on drag alone (RULES.md).
const dragging = ref(false);
const STEP = 16;

function onPointerDown(e: PointerEvent) {
  dragging.value = true;
  (e.target as HTMLElement).setPointerCapture(e.pointerId);
}
function onPointerMove(e: PointerEvent) {
  if (!dragging.value) return;
  const next = window.innerWidth - e.clientX;
  session.setCommsWidth(Math.min(640, Math.max(280, next)));
}
function onPointerUp() {
  dragging.value = false;
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'ArrowLeft') session.setCommsWidth(Math.min(640, session.commsWidth + STEP));
  else if (e.key === 'ArrowRight') session.setCommsWidth(Math.max(280, session.commsWidth - STEP));
}

onBeforeUnmount(onPointerUp);
</script>

<template>
  <aside
    class="comms"
    :style="{ width: session.commsWidth + 'px' }"
    :aria-label="t('comms.phone')"
  >
    <button
      class="comms__handle"
      type="button"
      :aria-label="t('comms.phone') + ' – Breite anpassen'"
      aria-valuemin="280"
      aria-valuemax="640"
      :aria-valuenow="session.commsWidth"
      role="separator"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @keydown="onKey"
    />
    <div class="comms__body">
      <h2>{{ t('comms.phone') }}</h2>
      <p class="comms__note">
        {{ t('foundation.notice') }}
      </p>
    </div>
  </aside>
</template>

<style scoped>
.comms {
  position: relative;
  padding: 0.75rem 1rem 0.75rem 1.25rem;
}
.comms__handle {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 10px;
  padding: 0;
  border: 0;
  cursor: col-resize;
  background: transparent;
}
.comms__handle:focus-visible {
  outline: 2px solid var(--bbz-accent);
}
.comms__note {
  color: var(--bbz-text-muted);
  font-size: 0.85rem;
}
</style>
