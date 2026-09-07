<script setup lang="ts">
/**
 * SIP telephony gateway (E13-07, ADR-0033). Point BBZ at the site's Asterisk —
 * host, TLS, the ARI user + password, the Stasis app, and the SIP lines — with
 * a "test connection" probe. The ARI password is write-only: the API only ever
 * reports whether one is stored, never the value. A save takes effect without a
 * restart (the cached provider is evicted server-side).
 *
 * Gated on `integrations.configure`.
 */
import { computed, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError } from '@/lib/apiClient';
import { adminApi, type SipConfig, type SipLine, type SipProbeResult } from '@/lib/admin';

const { t } = useI18n();

const config = ref<SipConfig | null>(null);
const error = ref('');
const busy = ref(false);
const saved = ref(false);
const probe = ref<SipProbeResult | null>(null);
const probing = ref(false);

const form = reactive({
  host: '',
  port: 8088,
  tls: true,
  app_name: 'bbz-sip',
  dtmf_transport: 'rfc2833' as 'rfc2833' | 'sip_info',
  ari_username: '',
  ari_password: '',
  enabled: false,
});

const passwordConfigured = computed(() => config.value?.gateway.ari_password_configured ?? false);

function fill(c: SipConfig): void {
  config.value = c;
  form.host = c.gateway.host;
  form.port = c.gateway.port;
  form.tls = c.gateway.tls;
  form.app_name = c.gateway.app_name;
  form.dtmf_transport = c.gateway.dtmf_transport;
  form.ari_username = c.gateway.ari_username;
  form.ari_password = '';
  form.enabled = c.gateway.enabled;
}

async function load(): Promise<void> {
  error.value = '';
  try {
    fill(await adminApi.sipConfig());
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.sip.loadError');
  }
}

async function save(): Promise<void> {
  busy.value = true;
  error.value = '';
  saved.value = false;
  try {
    const body = { ...form, ari_password: form.ari_password || undefined };
    fill(await adminApi.putSipGateway(body));
    saved.value = true;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.sip.saveError');
  } finally {
    busy.value = false;
  }
}

async function testConnection(): Promise<void> {
  probing.value = true;
  probe.value = null;
  error.value = '';
  try {
    probe.value = await adminApi.testSipConnection();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.sip.testError');
  } finally {
    probing.value = false;
  }
}

// --- lines -----------------------------------------------------------------

const lines = computed<SipLine[]>(() => config.value?.lines ?? []);
const newLine = reactive({ bbz_line_id: '', asterisk_endpoint: '', label: '', enabled: true });
const lineError = ref('');

async function addLine(): Promise<void> {
  lineError.value = '';
  if (!newLine.bbz_line_id.trim()) {
    lineError.value = t('admin.sip.lineIdRequired');
    return;
  }
  try {
    await adminApi.putSipLine(newLine.bbz_line_id.trim(), {
      asterisk_endpoint: newLine.asterisk_endpoint.trim() || null,
      label: newLine.label.trim(),
      enabled: newLine.enabled,
    });
    newLine.bbz_line_id = '';
    newLine.asterisk_endpoint = '';
    newLine.label = '';
    newLine.enabled = true;
    await load();
  } catch (e) {
    lineError.value = e instanceof ApiError ? e.message : t('admin.sip.lineSaveError');
  }
}

async function toggleLine(line: SipLine): Promise<void> {
  try {
    await adminApi.putSipLine(line.bbz_line_id, {
      asterisk_endpoint: line.asterisk_endpoint,
      label: line.label,
      enabled: !line.enabled,
    });
    await load();
  } catch (e) {
    lineError.value = e instanceof ApiError ? e.message : t('admin.sip.lineSaveError');
  }
}

async function removeLine(line: SipLine): Promise<void> {
  try {
    await adminApi.deleteSipLine(line.bbz_line_id);
    await load();
  } catch (e) {
    lineError.value = e instanceof ApiError ? e.message : t('admin.sip.lineDeleteError');
  }
}

onMounted(load);
</script>

<template>
  <section class="sip">
    <p
      v-if="error"
      role="alert"
      class="sip__error"
    >
      {{ error }}
    </p>

    <p
      v-if="config && !config.active"
      class="sip__note muted"
    >
      {{ t('admin.sip.notActive') }}
    </p>

    <form
      class="card"
      @submit.prevent="save"
    >
      <div class="card-head">
        <div class="card-title">
          {{ t('admin.sip.gatewayTitle') }}
        </div>
      </div>
      <div class="card-body sip__form">
        <label for="sip-host">{{ t('admin.sip.host') }}</label>
        <input
          id="sip-host"
          v-model="form.host"
          class="input"
          autocomplete="off"
          :placeholder="t('admin.sip.hostPlaceholder')"
        >

        <label for="sip-port">{{ t('admin.sip.port') }}</label>
        <input
          id="sip-port"
          v-model.number="form.port"
          type="number"
          min="1"
          max="65535"
          class="input"
        >

        <label for="sip-app">{{ t('admin.sip.appName') }}</label>
        <input
          id="sip-app"
          v-model="form.app_name"
          class="input"
          autocomplete="off"
        >

        <label for="sip-dtmf">{{ t('admin.sip.dtmfTransport') }}</label>
        <select
          id="sip-dtmf"
          v-model="form.dtmf_transport"
          class="input"
        >
          <option value="rfc2833">
            RFC 2833
          </option>
          <option value="sip_info">
            SIP INFO
          </option>
        </select>

        <label for="sip-user">{{ t('admin.sip.ariUser') }}</label>
        <input
          id="sip-user"
          v-model="form.ari_username"
          class="input"
          autocomplete="off"
        >

        <label for="sip-pass">{{ t('admin.sip.ariPassword') }}</label>
        <input
          id="sip-pass"
          v-model="form.ari_password"
          type="password"
          class="input"
          autocomplete="new-password"
          :placeholder="
            passwordConfigured ? t('admin.sip.passwordKeep') : t('admin.sip.passwordUnset')
          "
        >

        <div class="sip__checks">
          <label class="sip__check">
            <input
              v-model="form.tls"
              type="checkbox"
            >
            {{ t('admin.sip.tls') }}
          </label>
          <label class="sip__check">
            <input
              v-model="form.enabled"
              type="checkbox"
            >
            {{ t('admin.sip.enabled') }}
          </label>
        </div>
      </div>

      <div class="card-foot sip__actions">
        <button
          type="submit"
          class="btn btn--primary"
          :disabled="busy"
        >
          {{ busy ? t('admin.saving') : t('admin.save') }}
        </button>
        <button
          type="button"
          class="btn"
          :disabled="probing || !form.host"
          @click="testConnection"
        >
          {{ probing ? t('admin.sip.testing') : t('admin.sip.test') }}
        </button>
        <span
          v-if="saved"
          class="sip__ok"
        >{{ t('admin.sip.saved') }}</span>
        <span
          v-if="probe"
          class="tag"
          :class="probe.reachable ? 'green' : 'red'"
        >
          {{ probe.reachable ? t('admin.sip.reachable') : t('admin.sip.unreachable') }}
          <template v-if="probe.asterisk_version"> · {{ probe.asterisk_version }}</template>
        </span>
      </div>
      <p
        v-if="probe && !probe.reachable"
        class="sip__probe-detail muted"
      >
        {{ probe.detail }}
      </p>
    </form>

    <div class="card">
      <div class="card-head">
        <div class="card-title">
          {{ t('admin.sip.linesTitle') }}
        </div>
      </div>
      <div class="card-body sip__lines">
        <p
          v-if="lineError"
          role="alert"
          class="sip__error"
        >
          {{ lineError }}
        </p>
        <table
          v-if="lines.length"
          class="sip__table"
        >
          <thead>
            <tr>
              <th>{{ t('admin.sip.lineId') }}</th>
              <th>{{ t('admin.sip.endpoint') }}</th>
              <th>{{ t('admin.sip.label') }}</th>
              <th>{{ t('admin.sip.enabled') }}</th>
              <th><span class="visually-hidden">{{ t('admin.sip.actions') }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="line in lines"
              :key="line.bbz_line_id"
            >
              <td>{{ line.bbz_line_id }}</td>
              <td><code>{{ line.asterisk_endpoint }}</code></td>
              <td>{{ line.label || '—' }}</td>
              <td>
                <button
                  type="button"
                  class="tag"
                  :class="line.enabled ? 'green' : 'gray'"
                  @click="toggleLine(line)"
                >
                  {{ line.enabled ? t('admin.sip.on') : t('admin.sip.off') }}
                </button>
              </td>
              <td>
                <button
                  type="button"
                  class="btn btn--sm"
                  @click="removeLine(line)"
                >
                  {{ t('admin.sip.remove') }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <p
          v-else
          class="muted"
        >
          {{ t('admin.sip.noLines') }}
        </p>

        <form
          class="sip__add"
          @submit.prevent="addLine"
        >
          <input
            v-model="newLine.bbz_line_id"
            class="input"
            :aria-label="t('admin.sip.lineId')"
            :placeholder="t('admin.sip.lineId')"
          >
          <input
            v-model="newLine.asterisk_endpoint"
            class="input"
            :aria-label="t('admin.sip.endpoint')"
            :placeholder="t('admin.sip.endpointPlaceholder')"
          >
          <input
            v-model="newLine.label"
            class="input"
            :aria-label="t('admin.sip.label')"
            :placeholder="t('admin.sip.label')"
          >
          <button
            type="submit"
            class="btn"
          >
            {{ t('admin.sip.addLine') }}
          </button>
        </form>
      </div>
    </div>
  </section>
</template>

<style scoped>
.sip {
  display: grid;
  gap: 0.9rem;
  align-content: start;
}
.sip__error {
  color: var(--bbz-danger-text);
}
.sip__form {
  display: grid;
  grid-template-columns: 10rem minmax(0, 22rem);
  gap: 0.55rem 0.9rem;
  align-items: center;
}
.sip__form label {
  font-weight: var(--bbz-weight-semibold);
  font-size: 0.85rem;
}
.sip__checks {
  grid-column: 1 / -1;
  display: flex;
  gap: 1.2rem;
  margin-top: 0.3rem;
}
.sip__check {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.9rem;
}
.sip__actions {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  flex-wrap: wrap;
}
.sip__ok {
  color: var(--bbz-success-text);
  font-size: 0.82rem;
}
.sip__probe-detail {
  padding: 0 1rem 0.8rem;
  font-size: 0.82rem;
}
.sip__lines {
  display: grid;
  gap: 0.7rem;
}
.sip__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
.sip__table th,
.sip__table td {
  text-align: left;
  padding: 0.4rem 0.5rem;
  border-bottom: 1px solid var(--bbz-border);
}
.sip__add {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.sip__add .input {
  flex: 1 1 8rem;
}
@media (max-width: 640px) {
  .sip__form {
    grid-template-columns: 1fr;
    align-items: start;
  }
}
</style>
