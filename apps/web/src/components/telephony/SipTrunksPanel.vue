<script setup lang="ts">
/**
 * SIP trunks (ITSP) + public numbers (E13-09, ADR-0034). BBZ stores the trunk
 * to LEONET / Telekom / a generic provider and the public numbers on it, then
 * renders the Asterisk config a sync script pulls onto the PBX. The trunk auth
 * password is write-only — the API only reports whether one is stored.
 *
 * Gated on `integrations.configure` (the parent page already checks it).
 */
import { computed, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError } from '@/lib/apiClient';
import {
  adminApi,
  type SipNumber,
  type SipTrunk,
  type SipTrunkInput,
  type SipTrunkProbeResult,
  type SipTrunkProvider,
} from '@/lib/admin';
import { sipTrunkPreset } from '@/lib/sipTrunkPresets';

const props = withDefaults(defineProps<{ sipActive?: boolean }>(), { sipActive: false });

const { t } = useI18n();

const trunks = ref<SipTrunk[]>([]);
const numbers = ref<SipNumber[]>([]);
const error = ref('');
const busy = ref(false);
const saved = ref(false);
const probes = reactive<Record<string, SipTrunkProbeResult>>({});

const blankTrunk = (): SipTrunkInput => ({
  provider: 'generic',
  display_name: '',
  enabled: false,
  sip_server: '',
  sip_port: 5060,
  transport: 'udp',
  outbound_proxy: '',
  from_domain: '',
  registration: true,
  auth_username: '',
  auth_password: '',
  match_hosts: '',
  codecs: 'alaw,ulaw',
  dtmf_mode: 'rfc4733',
  caller_id_e164: '',
});

const form = reactive<SipTrunkInput & { trunk_id: string }>({ trunk_id: '', ...blankTrunk() });
const editing = ref(false);
const passwordConfigured = ref(false);

function resetForm(): void {
  Object.assign(form, { trunk_id: '', ...blankTrunk() });
  editing.value = false;
  passwordConfigured.value = false;
}

function editTrunk(tr: SipTrunk): void {
  // only the SipTrunkInput fields — NOT `auth_password_configured` (a read-only
  // flag) or a stray key, or the PUT body trips `extra="forbid"` -> 422.
  Object.assign(form, { trunk_id: tr.trunk_id, ...trunkToInput(tr), auth_password: '' });
  editing.value = true;
  passwordConfigured.value = tr.auth_password_configured;
  saved.value = false;
}

function applyPreset(): void {
  const preset = sipTrunkPreset(form.provider as SipTrunkProvider);
  if (preset) Object.assign(form, preset);
}

async function load(): Promise<void> {
  error.value = '';
  try {
    const res = await adminApi.sipTrunks();
    trunks.value = res.trunks;
    numbers.value = res.numbers;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.sipt.loadError');
  }
}

function formBody(): SipTrunkInput {
  // build the PUT body from exactly the known fields (the form is a reactive
  // object that may carry extra keys from a previous `Object.assign`)
  return {
    provider: form.provider,
    display_name: form.display_name,
    enabled: form.enabled,
    sip_server: form.sip_server,
    sip_port: form.sip_port,
    transport: form.transport,
    outbound_proxy: form.outbound_proxy,
    from_domain: form.from_domain,
    registration: form.registration,
    auth_username: form.auth_username,
    match_hosts: form.match_hosts,
    codecs: form.codecs,
    dtmf_mode: form.dtmf_mode,
    caller_id_e164: form.caller_id_e164,
    auth_password: form.auth_password || undefined,
  };
}

async function saveTrunk(): Promise<void> {
  busy.value = true;
  error.value = '';
  saved.value = false;
  try {
    await adminApi.putSipTrunk(form.trunk_id.trim(), formBody());
    saved.value = true;
    resetForm();
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.sipt.saveError');
  } finally {
    busy.value = false;
  }
}

async function toggleTrunk(tr: SipTrunk): Promise<void> {
  try {
    await adminApi.putSipTrunk(tr.trunk_id, {
      ...trunkToInput(tr),
      enabled: !tr.enabled,
      auth_password: undefined,
    });
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.sipt.saveError');
  }
}

async function removeTrunk(tr: SipTrunk): Promise<void> {
  if (!window.confirm(t('admin.sipt.confirmDelete', { id: tr.trunk_id }))) return;
  try {
    await adminApi.deleteSipTrunk(tr.trunk_id);
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.sipt.deleteError');
  }
}

const lastProbed = ref('');

async function testTrunk(tr: SipTrunk): Promise<void> {
  try {
    probes[tr.trunk_id] = await adminApi.testSipTrunk(tr.trunk_id);
    lastProbed.value = tr.trunk_id;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.sipt.testError');
  }
}

const PROBE_CLASS: Record<string, string> = {
  online: 'green',
  loaded: 'amber',
  not_loaded: 'red',
  unreachable: 'red',
};
const probeClass = (state: string): string => PROBE_CLASS[state] ?? 'gray';
const probeLabel = (state: string): string => t(`admin.sipt.probe.${state}`, state);

function trunkToInput(tr: SipTrunk): SipTrunkInput {
  return {
    provider: tr.provider,
    display_name: tr.display_name,
    enabled: tr.enabled,
    sip_server: tr.sip_server,
    sip_port: tr.sip_port,
    transport: tr.transport,
    outbound_proxy: tr.outbound_proxy,
    from_domain: tr.from_domain,
    registration: tr.registration,
    auth_username: tr.auth_username,
    match_hosts: tr.match_hosts,
    codecs: tr.codecs,
    dtmf_mode: tr.dtmf_mode,
    caller_id_e164: tr.caller_id_e164,
  };
}

// --- numbers -------------------------------------------------------------

const newNumber = reactive({ e164: '', trunk_id: '', bbz_line_id: '', label: '', enabled: true });
const numberError = ref('');

async function addNumber(): Promise<void> {
  numberError.value = '';
  if (!newNumber.e164.trim() || !newNumber.trunk_id) {
    numberError.value = t('admin.sipt.numberRequired');
    return;
  }
  try {
    await adminApi.putSipNumber(newNumber.e164.trim(), {
      trunk_id: newNumber.trunk_id,
      bbz_line_id: newNumber.bbz_line_id.trim(),
      label: newNumber.label.trim(),
      registration: false,
      auth_username: '',
      enabled: newNumber.enabled,
    });
    Object.assign(newNumber, { e164: '', bbz_line_id: '', label: '', enabled: true });
    await load();
  } catch (e) {
    numberError.value = e instanceof ApiError ? e.message : t('admin.sipt.numberSaveError');
  }
}

async function toggleNumber(n: SipNumber): Promise<void> {
  try {
    await adminApi.putSipNumber(n.e164, {
      trunk_id: n.trunk_id,
      bbz_line_id: n.bbz_line_id,
      label: n.label,
      registration: n.registration,
      auth_username: n.auth_username,
      enabled: !n.enabled,
    });
    await load();
  } catch (e) {
    numberError.value = e instanceof ApiError ? e.message : t('admin.sipt.numberSaveError');
  }
}

async function removeNumber(n: SipNumber): Promise<void> {
  try {
    await adminApi.deleteSipNumber(n.e164);
    await load();
  } catch (e) {
    numberError.value = e instanceof ApiError ? e.message : t('admin.sipt.numberDeleteError');
  }
}

// --- generated config ---------------------------------------------------

const configText = ref('');
const configPart = ref<'all' | 'pjsip' | 'extensions'>('all');
const configOpen = ref(false);
const copied = ref(false);

async function showConfig(): Promise<void> {
  error.value = '';
  try {
    configText.value = await adminApi.sipAsteriskConfig(configPart.value);
    configOpen.value = true;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.sipt.configError');
  }
}

async function copyConfig(): Promise<void> {
  try {
    await navigator.clipboard.writeText(configText.value);
    copied.value = true;
    window.setTimeout(() => (copied.value = false), 2000);
  } catch {
    /* clipboard blocked — the user can still select the text */
  }
}

const presetBannerProvider = computed(() => form.provider);

onMounted(load);
</script>

<template>
  <div class="sipt">
    <p
      v-if="error"
      role="alert"
      class="sipt__error"
    >
      {{ error }}
    </p>

    <p
      v-if="!props.sipActive"
      class="sipt__banner sipt__banner--info"
    >
      {{ t('admin.sipt.notActive') }}
    </p>

    <!-- trunks -->
    <div class="card">
      <div class="card-head">
        <div class="card-title">
          {{ t('admin.sipt.trunksTitle') }}
        </div>
      </div>
      <div class="card-body sipt__body">
        <table
          v-if="trunks.length"
          class="sipt__table"
        >
          <thead>
            <tr>
              <th>{{ t('admin.sipt.trunkId') }}</th>
              <th>{{ t('admin.sipt.provider') }}</th>
              <th>{{ t('admin.sipt.server') }}</th>
              <th>{{ t('admin.sipt.registration') }}</th>
              <th>{{ t('admin.sip.enabled') }}</th>
              <th><span class="visually-hidden">{{ t('admin.sip.actions') }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="tr in trunks"
              :key="tr.trunk_id"
            >
              <td>
                <code>{{ tr.trunk_id }}</code>
                <span
                  v-if="tr.display_name"
                  class="muted"
                > · {{ tr.display_name }}</span>
              </td>
              <td>{{ tr.provider }}</td>
              <td><code>{{ tr.sip_server || '—' }}:{{ tr.sip_port }}</code> / {{ tr.transport }}</td>
              <td>
                {{ tr.registration ? t('admin.sipt.registers') : t('admin.sipt.ipOnly') }}
                <span
                  v-if="tr.auth_password_configured"
                  class="muted"
                > · {{ t('admin.sipt.pwSet') }}</span>
              </td>
              <td>
                <button
                  type="button"
                  class="tag"
                  :class="tr.enabled ? 'green' : 'gray'"
                  @click="toggleTrunk(tr)"
                >
                  {{ tr.enabled ? t('admin.sip.on') : t('admin.sip.off') }}
                </button>
              </td>
              <td class="sipt__row-actions">
                <button
                  type="button"
                  class="btn btn--sm"
                  @click="testTrunk(tr)"
                >
                  {{ t('admin.sipt.test') }}
                </button>
                <button
                  type="button"
                  class="btn btn--sm"
                  @click="editTrunk(tr)"
                >
                  {{ t('admin.sipt.edit') }}
                </button>
                <button
                  type="button"
                  class="btn btn--sm"
                  @click="removeTrunk(tr)"
                >
                  {{ t('admin.sip.remove') }}
                </button>
                <span
                  v-if="probes[tr.trunk_id]"
                  class="tag sipt__probe"
                  :class="probeClass(probes[tr.trunk_id].state)"
                  :title="probes[tr.trunk_id].detail"
                >
                  {{ probeLabel(probes[tr.trunk_id].state) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <p
          v-if="lastProbed && probes[lastProbed]"
          class="sipt__probe-detail muted"
        >
          <strong>{{ lastProbed }}</strong> — {{ probes[lastProbed].detail }}
        </p>
        <p
          v-else
          class="muted"
        >
          {{ t('admin.sipt.noTrunks') }}
        </p>
      </div>
    </div>

    <!-- add / edit trunk -->
    <form
      class="card"
      @submit.prevent="saveTrunk"
    >
      <div class="card-head">
        <div class="card-title">
          {{ editing ? t('admin.sipt.editTrunk', { id: form.trunk_id }) : t('admin.sipt.newTrunk') }}
        </div>
      </div>
      <div class="card-body sipt__form">
        <label for="sipt-id">{{ t('admin.sipt.trunkId') }}</label>
        <input
          id="sipt-id"
          v-model="form.trunk_id"
          class="input"
          :disabled="editing"
          autocomplete="off"
          placeholder="leonet"
        >

        <label for="sipt-provider">{{ t('admin.sipt.provider') }}</label>
        <select
          id="sipt-provider"
          v-model="form.provider"
          class="input"
          @change="applyPreset"
        >
          <option value="generic">
            {{ t('admin.sipt.providerGeneric') }}
          </option>
          <option value="leonet">
            LEONET
          </option>
          <option value="telekom">
            Telekom
          </option>
        </select>

        <label for="sipt-name">{{ t('admin.sipt.displayName') }}</label>
        <input
          id="sipt-name"
          v-model="form.display_name"
          class="input"
          autocomplete="off"
        >

        <label for="sipt-server">{{ t('admin.sipt.server') }}</label>
        <input
          id="sipt-server"
          v-model="form.sip_server"
          class="input"
          autocomplete="off"
          placeholder="sip.provider.example"
        >

        <label for="sipt-port">{{ t('admin.sip.port') }}</label>
        <input
          id="sipt-port"
          v-model.number="form.sip_port"
          type="number"
          min="1"
          max="65535"
          class="input"
        >

        <label for="sipt-transport">{{ t('admin.sipt.transport') }}</label>
        <select
          id="sipt-transport"
          v-model="form.transport"
          class="input"
        >
          <option value="udp">
            UDP
          </option>
          <option value="tcp">
            TCP
          </option>
          <option value="tls">
            TLS
          </option>
        </select>

        <label for="sipt-from">{{ t('admin.sipt.fromDomain') }}</label>
        <input
          id="sipt-from"
          v-model="form.from_domain"
          class="input"
          autocomplete="off"
        >

        <label for="sipt-proxy">{{ t('admin.sipt.outboundProxy') }}</label>
        <input
          id="sipt-proxy"
          v-model="form.outbound_proxy"
          class="input"
          autocomplete="off"
        >

        <label for="sipt-user">{{ t('admin.sipt.authUser') }}</label>
        <input
          id="sipt-user"
          v-model="form.auth_username"
          class="input"
          autocomplete="off"
        >

        <label for="sipt-pass">{{ t('admin.sipt.authPassword') }}</label>
        <input
          id="sipt-pass"
          v-model="form.auth_password"
          type="password"
          class="input"
          autocomplete="new-password"
          :placeholder="
            passwordConfigured ? t('admin.sip.passwordKeep') : t('admin.sip.passwordUnset')
          "
        >

        <label for="sipt-match">{{ t('admin.sipt.matchHosts') }}</label>
        <input
          id="sipt-match"
          v-model="form.match_hosts"
          class="input"
          autocomplete="off"
          placeholder="91.106.121.3/32, sbc.provider.example"
        >

        <label for="sipt-codecs">{{ t('admin.sipt.codecs') }}</label>
        <input
          id="sipt-codecs"
          v-model="form.codecs"
          class="input"
          autocomplete="off"
        >

        <label for="sipt-dtmf">{{ t('admin.sip.dtmfTransport') }}</label>
        <select
          id="sipt-dtmf"
          v-model="form.dtmf_mode"
          class="input"
        >
          <option value="rfc4733">
            RFC 4733
          </option>
          <option value="inband">
            Inband
          </option>
          <option value="info">
            SIP INFO
          </option>
          <option value="auto">
            auto
          </option>
        </select>

        <label for="sipt-cli">{{ t('admin.sipt.callerId') }}</label>
        <input
          id="sipt-cli"
          v-model="form.caller_id_e164"
          class="input"
          autocomplete="off"
          placeholder="+49891234567"
        >

        <div class="sipt__checks">
          <label class="sipt__check">
            <input
              v-model="form.registration"
              type="checkbox"
            >
            {{ t('admin.sipt.doRegister') }}
          </label>
          <label class="sipt__check">
            <input
              v-model="form.enabled"
              type="checkbox"
            >
            {{ t('admin.sip.enabled') }}
          </label>
        </div>

        <p
          v-if="presetBannerProvider !== 'generic'"
          class="sipt__banner sipt__banner--preset"
        >
          {{ t('admin.sipt.presetBanner') }}
        </p>
      </div>
      <div class="card-foot sipt__actions">
        <button
          type="submit"
          class="btn btn--primary"
          :disabled="busy"
        >
          {{ busy ? t('admin.saving') : t('admin.save') }}
        </button>
        <button
          v-if="editing"
          type="button"
          class="btn"
          @click="resetForm"
        >
          {{ t('admin.sipt.cancel') }}
        </button>
        <span
          v-if="saved"
          class="sipt__ok"
        >{{ t('admin.sip.saved') }}</span>
      </div>
    </form>

    <!-- numbers -->
    <div class="card">
      <div class="card-head">
        <div class="card-title">
          {{ t('admin.sipt.numbersTitle') }}
        </div>
      </div>
      <div class="card-body sipt__body">
        <p
          v-if="numberError"
          role="alert"
          class="sipt__error"
        >
          {{ numberError }}
        </p>
        <table
          v-if="numbers.length"
          class="sipt__table"
        >
          <thead>
            <tr>
              <th>{{ t('admin.sipt.number') }}</th>
              <th>{{ t('admin.sipt.trunkId') }}</th>
              <th>{{ t('admin.sipt.bbzLine') }}</th>
              <th>{{ t('admin.sip.label') }}</th>
              <th>{{ t('admin.sip.enabled') }}</th>
              <th><span class="visually-hidden">{{ t('admin.sip.actions') }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="n in numbers"
              :key="n.e164"
            >
              <td><code>{{ n.e164 }}</code></td>
              <td>{{ n.trunk_id }}</td>
              <td>{{ n.bbz_line_id || n.e164 }}</td>
              <td>{{ n.label || '—' }}</td>
              <td>
                <button
                  type="button"
                  class="tag"
                  :class="n.enabled ? 'green' : 'gray'"
                  @click="toggleNumber(n)"
                >
                  {{ n.enabled ? t('admin.sip.on') : t('admin.sip.off') }}
                </button>
              </td>
              <td>
                <button
                  type="button"
                  class="btn btn--sm"
                  @click="removeNumber(n)"
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
          {{ t('admin.sipt.noNumbers') }}
        </p>

        <form
          class="sipt__add"
          @submit.prevent="addNumber"
        >
          <input
            v-model="newNumber.e164"
            class="input"
            :aria-label="t('admin.sipt.number')"
            placeholder="+49891234567"
          >
          <select
            v-model="newNumber.trunk_id"
            class="input"
            :aria-label="t('admin.sipt.trunkId')"
          >
            <option
              value=""
              disabled
            >
              {{ t('admin.sipt.pickTrunk') }}
            </option>
            <option
              v-for="tr in trunks"
              :key="tr.trunk_id"
              :value="tr.trunk_id"
            >
              {{ tr.trunk_id }}
            </option>
          </select>
          <input
            v-model="newNumber.bbz_line_id"
            class="input"
            :aria-label="t('admin.sipt.bbzLine')"
            :placeholder="t('admin.sipt.bbzLinePlaceholder')"
          >
          <input
            v-model="newNumber.label"
            class="input"
            :aria-label="t('admin.sip.label')"
            :placeholder="t('admin.sip.label')"
          >
          <button
            type="submit"
            class="btn"
          >
            {{ t('admin.sipt.addNumber') }}
          </button>
        </form>
      </div>
    </div>

    <!-- generated Asterisk config -->
    <div class="card">
      <div class="card-head">
        <div class="card-title">
          {{ t('admin.sipt.configTitle') }}
        </div>
      </div>
      <div class="card-body sipt__body">
        <p class="muted">
          {{ t('admin.sipt.configHint') }}
        </p>
        <div class="sipt__config-actions">
          <select
            v-model="configPart"
            class="input"
            :aria-label="t('admin.sipt.configPart')"
          >
            <option value="all">
              pjsip + extensions
            </option>
            <option value="pjsip">
              pjsip.conf
            </option>
            <option value="extensions">
              extensions.conf
            </option>
          </select>
          <button
            type="button"
            class="btn"
            @click="showConfig"
          >
            {{ t('admin.sipt.showConfig') }}
          </button>
          <button
            v-if="configOpen"
            type="button"
            class="btn btn--sm"
            @click="copyConfig"
          >
            {{ copied ? t('admin.sipt.copied') : t('admin.sipt.copy') }}
          </button>
        </div>
        <pre
          v-if="configOpen"
          class="sipt__config"
        >{{ configText }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sipt {
  display: grid;
  gap: 0.9rem;
}
.sipt__error {
  color: var(--bbz-danger-text);
}
.sipt__body {
  display: grid;
  gap: 0.7rem;
}
.sipt__form {
  display: grid;
  grid-template-columns: 11rem minmax(0, 24rem);
  gap: 0.55rem 0.9rem;
  align-items: center;
}
.sipt__form label {
  font-weight: var(--bbz-weight-semibold);
  font-size: 0.85rem;
}
.sipt__checks {
  grid-column: 1 / -1;
  display: flex;
  gap: 1.2rem;
  margin-top: 0.3rem;
}
.sipt__check {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.9rem;
}
.sipt__banner {
  grid-column: 1 / -1;
  margin: 0.4rem 0 0;
  padding: 0.5rem 0.7rem;
  border-left: 3px solid var(--bbz-warning-border, var(--bbz-border-strong));
  background: var(--bbz-warning-surface, var(--bbz-surface-alt));
  font-size: 0.82rem;
}
.sipt__banner--info {
  margin: 0;
  border-left-color: var(--bbz-accent);
  color: var(--bbz-text-muted);
}
.sipt__actions {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  flex-wrap: wrap;
}
.sipt__ok {
  color: var(--bbz-success-text);
  font-size: 0.82rem;
}
.sipt__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
}
.sipt__table th,
.sipt__table td {
  text-align: left;
  padding: 0.4rem 0.5rem;
  border-bottom: 1px solid var(--bbz-border);
  vertical-align: top;
}
.sipt__row-actions {
  display: flex;
  gap: 0.3rem;
  flex-wrap: wrap;
  align-items: center;
}
.sipt__probe {
  font-size: 0.72rem;
}
.sipt__probe-detail {
  margin: 0.1rem 0 0;
  font-size: 0.8rem;
}
.sipt__add {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.sipt__add .input {
  flex: 1 1 9rem;
}
.sipt__config-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  align-items: center;
}
.sipt__config {
  max-height: 24rem;
  overflow: auto;
  padding: 0.7rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius-sm, 4px);
  background: var(--bbz-surface-alt);
  font-size: 0.78rem;
  white-space: pre;
}
@media (max-width: 640px) {
  .sipt__form {
    grid-template-columns: 1fr;
    align-items: start;
  }
}
</style>
