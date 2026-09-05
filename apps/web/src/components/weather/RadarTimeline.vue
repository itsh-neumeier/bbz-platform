<script setup lang="ts">
/**
 * Niederschlagsradar-Zeitleiste (E18-09 / #391, MASTER_PROMPT §13.12).
 *
 * A frame series from `GET /weather/radar` (a DWD WMS GetMap URL per frame, the
 * browser fetches the image directly — no server proxy). The timeline is fully
 * keyboard-operable (AC "Radar-Zeitleiste ohne Maus bedienbar"): the scrubber is
 * a native `<input type="range">` (←/→ step, Home/End jump), and Play/Pause is a
 * native `<button>`. Autoplay motion is suppressed under `prefers-reduced-motion`
 * — the scrubber stays, only the moving animation goes (same rule as
 * PriorityPulse.vue).
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useReducedMotion } from '@/composables/useReducedMotion';
import type { RadarFrame } from '@/lib/weather';

const props = defineProps<{ frames: RadarFrame[] }>();
const { t, d } = useI18n();
const { reduced } = useReducedMotion();

const FRAME_MS = 800;

const idx = ref(0);
const playing = ref(false);
let timer: ReturnType<typeof setInterval> | undefined;

const count = computed(() => props.frames.length);
const current = computed<RadarFrame | null>(() => props.frames[idx.value] ?? null);
const frameTime = computed(() =>
  current.value ? d(new Date(current.value.frame_time), 'time') : '',
);

function stop(): void {
  playing.value = false;
  if (timer !== undefined) {
    clearInterval(timer);
    timer = undefined;
  }
}

function advance(): void {
  if (count.value === 0) return;
  idx.value = (idx.value + 1) % count.value;
}

function play(): void {
  if (count.value < 2 || reduced.value) return;
  playing.value = true;
  timer = setInterval(advance, FRAME_MS);
}

function toggle(): void {
  if (playing.value) stop();
  else play();
}

// keep the index valid as frames arrive / change; default to the newest frame
watch(
  () => props.frames,
  (next) => {
    stop();
    idx.value = Math.max(0, next.length - 1);
  },
  { immediate: true },
);

// a reduced-motion switch mid-playback stops the animation
watch(reduced, (r) => {
  if (r) stop();
});

onBeforeUnmount(stop);
</script>

<template>
  <div
    v-if="count"
    class="rt"
  >
    <img
      :src="current!.image_ref"
      :alt="t('weather.radarAlt')"
      class="rt__img"
    >

    <div class="rt__bar">
      <button
        v-if="!reduced && count > 1"
        type="button"
        class="rt__play"
        :aria-pressed="playing"
        @click="toggle"
      >
        {{ playing ? t('weather.radarPause') : t('weather.radarPlay') }}
      </button>

      <input
        id="wx-radar-scrub"
        v-model.number="idx"
        class="rt__scrub"
        type="range"
        min="0"
        :max="count - 1"
        :aria-label="t('weather.radarScrub')"
        :aria-valuetext="frameTime"
        @pointerdown="stop"
        @keydown="stop"
      >

      <span class="rt__meta">
        <time>{{ frameTime }}</time>
        <span class="rt__pos">{{ t('weather.radarFrame', { n: idx + 1, total: count }) }}</span>
      </span>
    </div>
  </div>

  <p
    v-else
    class="wx__empty"
  >
    {{ t('weather.noRadar') }}
  </p>
</template>

<style scoped>
.rt {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.rt__img {
  max-width: 100%;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-bg);
}
.rt__bar {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
}
.rt__play {
  padding: 0.25rem 0.7rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-bg);
  color: var(--bbz-text);
  cursor: pointer;
  font: inherit;
  font-size: 0.8rem;
}
.rt__scrub {
  flex: 1 1 8rem;
  min-width: 6rem;
}
.rt__meta {
  display: flex;
  flex-direction: column;
  font-size: 0.78rem;
  color: var(--bbz-text-muted);
  font-variant-numeric: tabular-nums;
}
.rt__pos {
  font-size: 0.72rem;
}
</style>
