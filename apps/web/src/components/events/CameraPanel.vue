<script setup lang="ts">
/**
 * Kamera-Panel im Ereignisdetail (E16-12 / #357, MASTER_PROMPT §31/§36).
 *
 * Shows the cameras the trigger engine associated with this event (from the
 * `CAMERA_OPENED` / `CAMERA_ACTION_FAILED` domain-event trail, ADR-0032) and
 * their live status. Camera opening is a decoupled side effect (ADR-0006): a
 * camera being unavailable is shown as text ("Video derzeit nicht verfügbar")
 * and never blocks working the event. The card is absent for events with no
 * associated cameras. Gated on `integrations.view`.
 */
import { onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useSessionStore } from '@/stores/session';
import { camerasApi, type EventCamera } from '@/lib/cameras';

const props = defineProps<{ eventId: string }>();
const { t } = useI18n();
const session = useSessionStore();

const loaded = ref(false);
const providerAvailable = ref(true);
const cameras = ref<EventCamera[]>([]);

async function load(): Promise<void> {
  if (!session.can('integrations.view')) return;
  loaded.value = false;
  try {
    const res = await camerasApi.forEvent(props.eventId);
    providerAvailable.value = res.provider_available;
    cameras.value = res.cameras;
  } catch {
    cameras.value = [];
  } finally {
    loaded.value = true;
  }
}

function statusKey(cam: EventCamera): 'online' | 'offline' | 'unknown' {
  if (cam.online === true) return 'online';
  if (cam.online === false) return 'offline';
  return 'unknown';
}

onMounted(load);
watch(() => props.eventId, load);
</script>

<template>
  <section
    v-if="loaded && session.can('integrations.view') && cameras.length"
    class="card campanel"
    aria-labelledby="epp-cams"
  >
    <div class="card-head">
      <div
        id="epp-cams"
        class="card-title"
      >
        {{ t('camera.title') }}
      </div>
    </div>
    <div class="card-body">
      <p
        v-if="!providerAvailable"
        role="status"
        class="campanel__down"
      >
        {{ t('camera.unavailable') }}
      </p>

      <ul class="campanel__list">
        <li
          v-for="cam in cameras"
          :key="cam.ref"
          class="campanel__item"
        >
          <span class="campanel__name">{{ cam.name }}</span>
          <span
            v-if="cam.site"
            class="campanel__site"
          >{{ cam.site }}</span>

          <span
            class="campanel__status"
            :class="'campanel__status--' + statusKey(cam)"
          >
            {{ t('camera.status.' + statusKey(cam)) }}
          </span>

          <span
            v-if="cam.last_action_state === 'failed'"
            class="campanel__failed"
          >
            {{ t('camera.openFailed') }}
          </span>
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.campanel__down {
  margin: 0 0 0.6rem;
  font-size: 0.85rem;
  color: var(--bbz-danger-text);
}
.campanel__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.campanel__item {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 0.4rem 0.55rem;
  font-size: 0.85rem;
}
.campanel__name {
  font-weight: 600;
}
.campanel__site {
  color: var(--bbz-text-muted);
  font-size: 0.78rem;
}
.campanel__status {
  font-size: 0.74rem;
  font-weight: 600;
  padding: 0.05rem 0.4rem;
  border-radius: var(--bbz-radius-sm);
  border: 1px solid var(--bbz-border);
}
.campanel__status--online {
  background: var(--bbz-success);
  color: var(--bbz-on-success);
  border-color: transparent;
}
.campanel__status--offline {
  background: var(--bbz-prio-high);
  color: var(--bbz-on-prio-high);
  border-color: transparent;
}
.campanel__status--unknown {
  color: var(--bbz-text-muted);
}
.campanel__failed {
  font-size: 0.74rem;
  color: var(--bbz-danger-text);
}
</style>
