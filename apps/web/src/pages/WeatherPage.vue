<script setup lang="ts">
/**
 * Wetterlage (E18-09 / #391, MASTER_PROMPT §13.12). DWD warnings for
 * Mittelfranken, local observation tiles, the keyboard-operable radar timeline,
 * and "Wetterereignis erzeugen" from a warning via a confirmation dialog
 * (E18-08). Degrades cleanly when the DWD feed is `degraded`/`stale`/`down`: the
 * overall health badge says so, each panel flags its own data kind, and the
 * cached values stay visible. DWD attribution is shown as required by ADR-0026.
 */
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { ApiError } from '@/lib/apiClient';
import { useSessionStore } from '@/stores/session';
import {
  weatherApi,
  type CreateWeatherEventBody,
  type RadarFrame,
  type WeatherAlert,
  type WeatherHealth,
  type WeatherObservation,
} from '@/lib/weather';
import RadarTimeline from '@/components/weather/RadarTimeline.vue';
import WeatherEventDialog from '@/components/weather/WeatherEventDialog.vue';

const { t, d } = useI18n();
const router = useRouter();
const session = useSessionStore();

const canCreate = computed(() => session.can('weather.create_event'));

const health = ref<WeatherHealth | null>(null);
const attribution = ref('Deutscher Wetterdienst');
const alerts = ref<WeatherAlert[]>([]);
const observations = ref<WeatherObservation[]>([]);
const frames = ref<RadarFrame[]>([]);
const loadError = ref(false);

const dialogAlert = ref<WeatherAlert | null>(null);
const creating = ref(false);
const createError = ref<string | null>(null);

/** health status for one data kind ("warnings" | "observations" | "radar"). */
function kindState(kind: string): string | null {
  const k = health.value?.kinds.find((x) => x.data_kind === kind);
  return k && k.status !== 'ok' ? k.status : null;
}

/** "10.09. 14:00 – 10.09. 20:00" for a warning's validity window, if known. */
function validRange(a: WeatherAlert): string {
  if (!a.valid_from) return '';
  const from = d(new Date(a.valid_from), 'short');
  return a.valid_to ? `${from} – ${d(new Date(a.valid_to), 'short')}` : from;
}

async function load(): Promise<void> {
  try {
    const [a, o, r] = await Promise.all([
      weatherApi.alerts(),
      weatherApi.observations(),
      weatherApi.radar().catch(() => null),
    ]);
    health.value = a.health;
    attribution.value = a.attribution || attribution.value;
    alerts.value = a.alerts;
    observations.value = o.observations;
    frames.value = r?.frames ?? [];
  } catch {
    loadError.value = true;
  }
}

function openCreate(alert: WeatherAlert): void {
  createError.value = null;
  dialogAlert.value = alert;
}

async function confirmCreate(payload: {
  priority: CreateWeatherEventBody['priority'];
  assessment: string;
}): Promise<void> {
  if (!dialogAlert.value) return;
  creating.value = true;
  createError.value = null;
  try {
    const { event_id } = await weatherApi.createEvent(dialogAlert.value.id, {
      priority: payload.priority,
      assessment: payload.assessment || null,
    });
    dialogAlert.value = null;
    router.push('/ereignisse/' + event_id);
  } catch (e) {
    createError.value = e instanceof ApiError ? e.message : t('weather.createDialog.error');
  } finally {
    creating.value = false;
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
          <span
            v-if="kindState('warnings')"
            class="wx__stale"
          >{{ t('weather.stale.' + kindState('warnings')) }}</span>
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
            <strong>{{ a.headline || a.type }}</strong>
            <span class="wx__region">{{ a.region }}</span>
            <p
              v-if="validRange(a)"
              class="wx__valid"
            >
              {{ validRange(a) }}
            </p>
            <p v-if="a.description">
              {{ a.description }}
            </p>
            <button
              v-if="canCreate"
              type="button"
              class="wx__create"
              @click="openCreate(a)"
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
          <span
            v-if="kindState('observations')"
            class="wx__stale"
          >{{ t('weather.stale.' + kindState('observations')) }}</span>
        </h2>
        <ul
          v-if="observations.length"
          class="wx__tiles"
        >
          <li
            v-for="(o, i) in observations"
            :key="i"
            class="wx__tile"
          >
            <span class="wx__tile-place">{{ o.place }}</span>
            <span class="wx__tile-value">{{ o.value ?? '—' }} {{ o.unit }}</span>
            <span class="wx__tile-metric">{{ t('weather.metric.' + o.metric, o.metric) }}</span>
          </li>
        </ul>
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
          <span
            v-if="kindState('radar')"
            class="wx__stale"
          >{{ t('weather.stale.' + kindState('radar')) }}</span>
        </h2>
        <RadarTimeline :frames="frames" />
      </section>
    </div>

    <p class="wx__attr">
      {{ t('weather.attribution', { name: attribution }) }}
    </p>

    <WeatherEventDialog
      :open="dialogAlert !== null"
      :alert="dialogAlert"
      :busy="creating"
      :error="createError"
      @close="dialogAlert = null"
      @confirm="confirmCreate"
    />
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
.wx__stale {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 0.05rem 0.35rem;
  margin-left: 0.4rem;
  border-radius: var(--bbz-radius-sm);
  background: var(--bbz-prio-medium);
  color: var(--bbz-on-prio-medium);
  vertical-align: middle;
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
.wx__valid {
  color: var(--bbz-text-muted);
  font-size: 0.8rem;
}
.wx__create {
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
.wx__tiles {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(8rem, 1fr));
  gap: 0.5rem;
}
.wx__tile {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-surface);
}
.wx__tile-place {
  font-size: 0.72rem;
  color: var(--bbz-text-muted);
}
.wx__tile-value {
  font-size: 1.05rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.wx__tile-metric {
  font-size: 0.74rem;
  color: var(--bbz-text-muted);
}
.wx__empty {
  color: var(--bbz-text-muted);
  font-size: 0.85rem;
}
.wx__error {
  color: var(--bbz-danger-text);
}
.wx__attr {
  margin: 1.25rem 0 0;
  font-size: 0.74rem;
  color: var(--bbz-text-muted);
}
</style>
