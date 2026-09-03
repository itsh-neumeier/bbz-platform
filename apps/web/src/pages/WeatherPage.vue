<script setup lang="ts">
/**
 * Wetterlage (E18-09 / #391, MASTER_PROMPT §13). DWD warnings, local
 * observations, the radar timeline, and "Ereignis erzeugen" from a warning
 * (E18-08). Degrades cleanly when the DWD feed is `down`/`stale` (the health
 * badge says so and the panels show what is cached).
 */
import { onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { ApiError } from '@/lib/apiClient';
import {
  weatherApi,
  type RadarFrame,
  type WeatherAlert,
  type WeatherHealth,
  type WeatherObservation,
} from '@/lib/weather';

const { t, d } = useI18n();
const router = useRouter();

const health = ref<WeatherHealth | null>(null);
const alerts = ref<WeatherAlert[]>([]);
const observations = ref<WeatherObservation[]>([]);
const frames = ref<RadarFrame[]>([]);
const frameIdx = ref(0);
const loadError = ref(false);
const creating = ref<string | null>(null);

async function load(): Promise<void> {
  try {
    const [a, o, r] = await Promise.all([
      weatherApi.alerts(),
      weatherApi.observations(),
      weatherApi.radar().catch(() => null),
    ]);
    health.value = a.health;
    alerts.value = a.alerts;
    observations.value = o.observations;
    frames.value = r?.frames ?? [];
    frameIdx.value = Math.max(0, frames.value.length - 1);
  } catch {
    loadError.value = true;
  }
}

async function createEvent(alert: WeatherAlert): Promise<void> {
  creating.value = alert.id;
  try {
    const { id } = await weatherApi.createEvent(alert.id);
    router.push('/ereignisse/' + id);
  } catch (e) {
    loadError.value = e instanceof ApiError;
  } finally {
    creating.value = null;
  }
}

onMounted(load);
</script>

<template>
  <section class="wx">
    <header class="wx__head">
      <h1>{{ t('nav.weather') }}</h1>
      <span
        v-if="health"
        :class="['wx__health', 'wx__health--' + health.overall]"
      >
        {{ t('weather.health.' + health.overall) }}
      </span>
    </header>

    <p
      v-if="loadError"
      role="alert"
      class="wx__error"
    >
      {{ t('weather.loadError') }}
    </p>

    <div class="wx__grid">
      <section aria-labelledby="wx-alerts">
        <h2 id="wx-alerts">
          {{ t('weather.alerts') }}
        </h2>
        <ul
          v-if="alerts.length"
          class="wx__alerts"
        >
          <li
            v-for="a in alerts"
            :key="a.id"
            :class="'wx__alert wx__alert--l' + a.level"
          >
            <strong>{{ a.headline }}</strong>
            <span class="wx__region">{{ a.region }}</span>
            <p v-if="a.description">
              {{ a.description }}
            </p>
            <button
              type="button"
              :disabled="creating === a.id"
              @click="createEvent(a)"
            >
              {{ t('weather.createEvent') }}
            </button>
          </li>
        </ul>
        <p
          v-else
          class="wx__empty"
        >
          {{ t('weather.noAlerts') }}
        </p>
      </section>

      <section aria-labelledby="wx-obs">
        <h2 id="wx-obs">
          {{ t('weather.observations') }}
        </h2>
        <table
          v-if="observations.length"
          class="wx__obs"
        >
          <tbody>
            <tr
              v-for="(o, i) in observations"
              :key="i"
            >
              <td>{{ o.place }}</td>
              <td>{{ t('weather.metric.' + o.metric, o.metric) }}</td>
              <td>{{ o.value ?? '—' }} {{ o.unit }}</td>
            </tr>
          </tbody>
        </table>
        <p
          v-else
          class="wx__empty"
        >
          {{ t('weather.noObservations') }}
        </p>
      </section>

      <section aria-labelledby="wx-radar">
        <h2 id="wx-radar">
          {{ t('weather.radar') }}
        </h2>
        <template v-if="frames.length">
          <img
            :src="frames[frameIdx].image_ref"
            :alt="t('weather.radarAlt')"
            class="wx__radar-img"
          >
          <label for="wx-frame">
            {{ d(new Date(frames[frameIdx].frame_time), 'time') }}
          </label>
          <input
            id="wx-frame"
            v-model.number="frameIdx"
            type="range"
            min="0"
            :max="frames.length - 1"
          >
        </template>
        <p
          v-else
          class="wx__empty"
        >
          {{ t('weather.noRadar') }}
        </p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.wx__head {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}
.wx__head h1 {
  margin: 0 0 0.75rem;
  font-size: 1.25rem;
}
.wx__health {
  font-size: 0.78rem;
  padding: 0.1rem 0.45rem;
  border-radius: var(--bbz-radius-sm);
}
.wx__health--ok {
  background: var(--bbz-success);
  color: var(--bbz-on-success);
}
.wx__health--degraded,
.wx__health--stale {
  background: var(--bbz-prio-medium);
  color: var(--bbz-on-prio-medium);
}
.wx__health--down {
  background: var(--bbz-prio-high);
  color: var(--bbz-on-prio-high);
}
.wx__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: 1.5rem;
}
.wx__grid h2 {
  font-size: 0.95rem;
  margin: 0 0 0.5rem;
}
.wx__alerts {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.wx__alert {
  border-left: 4px solid var(--bbz-prio-low);
  padding-left: 0.6rem;
}
.wx__alert--l3,
.wx__alert--l4 {
  border-left-color: var(--bbz-prio-high);
}
.wx__alert--l2 {
  border-left-color: var(--bbz-prio-medium);
}
.wx__alert p {
  margin: 0.25rem 0;
  font-size: 0.85rem;
}
.wx__alert button {
  padding: 0.25rem 0.6rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-accent);
  color: #fff;
  cursor: pointer;
  font-size: 0.8rem;
}
.wx__region {
  color: var(--bbz-text-muted);
  font-size: 0.8rem;
  margin-left: 0.4rem;
}
.wx__obs {
  border-collapse: collapse;
  font-size: 0.85rem;
}
.wx__obs td {
  padding: 0.25rem 0.5rem;
  border-bottom: 1px solid var(--bbz-border);
}
.wx__radar-img {
  max-width: 100%;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
}
.wx__empty {
  color: var(--bbz-text-muted);
  font-size: 0.85rem;
}
.wx__error {
  color: var(--bbz-danger-text);
}
</style>
