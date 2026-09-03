<script setup lang="ts">
/**
 * User administration (#722, part of #718). Backend: Epic 02 (`/users`,
 * `/roles`, `/users/{id}/roles`). List + create a local account + edit name +
 * assign/revoke roles + activate/deactivate (revokes sessions, audited
 * `USER_DEACTIVATED`) + admin password reset (shows the one-time password).
 * The per-role 2FA policy lives on `/admin/benutzer/mfa`.
 */
import { computed, onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { ApiError } from '@/lib/apiClient';
import { usersApi, rolesApi, type AdminUser, type Role } from '@/lib/users';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const session = useSessionStore();
const canManage = computed(() => session.can('users.manage'));
const canRoles = computed(() => session.can('roles.manage'));

const users = ref<AdminUser[]>([]);
const roles = ref<Role[]>([]);
const selectedId = ref<string | null>(null);
const error = ref('');
const loading = ref(true);
const busy = ref(false);
const oneTimePw = ref('');

const showCreate = ref(false);
const draft = ref({ display_name: '', local_username: '', initial_password: '' });

const selected = computed(() => users.value.find((u) => u.id === selectedId.value) ?? null);
const roleName = (key: string) => roles.value.find((r) => r.key === key)?.name ?? key;

async function load(): Promise<void> {
  loading.value = true;
  error.value = '';
  try {
    const [u, r] = await Promise.all([usersApi.list(), rolesApi.list()]);
    users.value = u;
    roles.value = r;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.users.loadError');
  } finally {
    loading.value = false;
  }
}

function select(id: string): void {
  selectedId.value = id;
  oneTimePw.value = '';
  error.value = '';
}

async function refreshOne(id: string): Promise<void> {
  const fresh = await usersApi.get(id);
  const i = users.value.findIndex((u) => u.id === id);
  if (i >= 0) users.value[i] = fresh;
}

async function act(fn: () => Promise<unknown>): Promise<void> {
  busy.value = true;
  error.value = '';
  try {
    await fn();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.users.actionError');
  } finally {
    busy.value = false;
  }
}

async function create(): Promise<void> {
  await act(async () => {
    const body = {
      display_name: draft.value.display_name.trim(),
      local_username: draft.value.local_username.trim() || null,
      initial_password: draft.value.initial_password || null,
    };
    const u = await usersApi.create(body);
    users.value = [...users.value, u].sort((a, b) => a.display_name.localeCompare(b.display_name));
    showCreate.value = false;
    draft.value = { display_name: '', local_username: '', initial_password: '' };
    select(u.id);
  });
}

async function toggleActive(u: AdminUser): Promise<void> {
  const activating = u.status !== 'active';
  if (!activating && !confirm(t('admin.users.confirmDeactivate', { name: u.display_name }))) return;
  await act(async () => {
    if (activating) await usersApi.activate(u.id);
    else await usersApi.deactivate(u.id);
    await refreshOne(u.id);
  });
}

async function resetPw(u: AdminUser): Promise<void> {
  const pw = prompt(t('admin.users.newPasswordPrompt'));
  if (!pw) return;
  await act(async () => {
    await usersApi.resetPassword(u.id, pw);
    oneTimePw.value = pw;
  });
}

async function toggleRole(u: AdminUser, role: Role): Promise<void> {
  const has = u.roles.includes(role.key);
  await act(async () => {
    if (has) await rolesApi.revoke(u.id, role.id);
    else await rolesApi.assign(u.id, role.id);
    await refreshOne(u.id);
  });
}

onMounted(load);
</script>

<template>
  <section class="au">
    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">
            {{ t('admin.users.title') }}
          </div>
          <div class="card-subtitle">
            {{ t('admin.users.subtitle') }}
          </div>
        </div>
        <div class="au__head-actions">
          <RouterLink
            :to="{ name: 'admin-users-mfa' }"
            class="btn ghost sm"
          >
            {{ t('admin.users.mfaLink') }}
          </RouterLink>
          <button
            v-if="canManage"
            type="button"
            class="btn primary sm"
            @click="showCreate = !showCreate"
          >
            {{ t('admin.users.new') }}
          </button>
        </div>
      </div>

      <div class="card-body">
        <p
          v-if="error"
          role="alert"
          class="au__error"
        >
          {{ error }}
        </p>

        <form
          v-if="showCreate && canManage"
          class="au__create"
          @submit.prevent="create"
        >
          <label>{{ t('admin.users.fDisplayName') }}
            <input
              v-model="draft.display_name"
              class="input"
              required
            >
          </label>
          <label>{{ t('admin.users.fUsername') }}
            <input
              v-model="draft.local_username"
              class="input"
              autocomplete="off"
            >
          </label>
          <label>{{ t('admin.users.fInitialPassword') }}
            <input
              v-model="draft.initial_password"
              class="input"
              type="text"
              autocomplete="off"
            >
          </label>
          <button
            type="submit"
            class="btn primary sm"
            :disabled="busy || !draft.display_name.trim()"
          >
            {{ t('admin.users.createBtn') }}
          </button>
          <small class="muted">{{ t('admin.users.createHint') }}</small>
        </form>

        <div class="detail-grid">
          <div class="au__table-wrap">
            <table class="table">
              <thead>
                <tr>
                  <th scope="col">
                    {{ t('admin.users.colName') }}
                  </th>
                  <th scope="col">
                    {{ t('admin.users.colProviders') }}
                  </th>
                  <th scope="col">
                    {{ t('admin.users.colRoles') }}
                  </th>
                  <th scope="col">
                    {{ t('admin.users.colStatus') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="u in users"
                  :key="u.id"
                  class="au__row"
                  :class="{ 'au__row--sel': u.id === selectedId, 'au__row--off': u.status !== 'active' }"
                  tabindex="0"
                  @click="select(u.id)"
                  @keydown.enter="select(u.id)"
                >
                  <td>{{ u.display_name }}</td>
                  <td>
                    <span
                      v-for="p in u.providers"
                      :key="p"
                      class="tag gray"
                    >{{ p }}</span>
                    <span
                      v-if="u.providers.length === 0"
                      class="muted"
                    >—</span>
                  </td>
                  <td>
                    <span
                      v-for="rk in u.roles"
                      :key="rk"
                      class="tag blue"
                    >{{ roleName(rk) }}</span>
                    <span
                      v-if="u.roles.length === 0"
                      class="muted"
                    >—</span>
                  </td>
                  <td>
                    <span
                      class="tag"
                      :class="u.status === 'active' ? 'green' : 'gray'"
                    >{{ t('admin.users.status.' + u.status, u.status) }}</span>
                  </td>
                </tr>
                <tr v-if="!loading && users.length === 0">
                  <td
                    colspan="4"
                    class="muted"
                  >
                    {{ t('admin.users.empty') }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div
            v-if="selected"
            class="card au__detail"
          >
            <div class="card-head">
              <div class="card-title">
                {{ selected.display_name }}
              </div>
            </div>
            <div class="card-body au__detail-body">
              <p
                v-if="oneTimePw"
                class="au__otp"
                role="status"
              >
                {{ t('admin.users.otp', { pw: oneTimePw }) }}
              </p>

              <fieldset
                class="au__roles"
                :disabled="!canRoles || busy"
              >
                <legend>{{ t('admin.users.rolesLegend') }}</legend>
                <label
                  v-for="r in roles"
                  :key="r.id"
                  class="au__role"
                >
                  <input
                    type="checkbox"
                    :checked="selected.roles.includes(r.key)"
                    @change="toggleRole(selected, r)"
                  >
                  {{ r.name }}
                </label>
              </fieldset>

              <div
                v-if="canManage"
                class="au__detail-actions"
              >
                <button
                  type="button"
                  class="btn sm"
                  :class="selected.status === 'active' ? 'danger' : 'success'"
                  :disabled="busy"
                  @click="toggleActive(selected)"
                >
                  {{ selected.status === 'active' ? t('admin.users.deactivate') : t('admin.users.activate') }}
                </button>
                <button
                  type="button"
                  class="btn ghost sm"
                  :disabled="busy || !selected.providers.includes('local')"
                  @click="resetPw(selected)"
                >
                  {{ t('admin.users.resetPassword') }}
                </button>
              </div>
            </div>
          </div>
          <p
            v-else
            class="muted au__prompt"
          >
            {{ t('admin.users.selectPrompt') }}
          </p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.au__head-actions {
  display: flex;
  gap: 0.4rem;
  align-items: center;
}
.au__create {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  align-items: end;
  padding: 0.8rem;
  margin-bottom: 0.8rem;
  border: var(--bbz-border-width) solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-surface-alt);
}
.au__create label {
  display: grid;
  gap: 0.2rem;
  font-size: 0.8rem;
}
.au__create .input {
  min-width: 12rem;
}
.au__table-wrap {
  overflow: auto;
  max-height: 60vh;
}
.au__row {
  cursor: pointer;
}
.au__row:hover {
  background: var(--bbz-surface-alt);
}
.au__row:focus-visible {
  outline: var(--bbz-focus-width) solid var(--bbz-focus-color);
  outline-offset: -2px;
}
.au__row--sel {
  background: var(--bbz-info-bg);
  box-shadow: inset 3px 0 0 var(--bbz-info);
}
.au__row--off {
  opacity: 0.6;
}
.au__row td .tag {
  margin: 1px 2px 1px 0;
}
.au__detail-body {
  display: grid;
  gap: 1rem;
}
.au__roles {
  display: grid;
  gap: 0.3rem;
  border: var(--bbz-border-width) solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  padding: 0.6rem 0.8rem;
}
.au__role {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.9rem;
}
.au__detail-actions {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.au__otp {
  padding: 0.5rem 0.7rem;
  border-radius: var(--bbz-radius);
  background: var(--bbz-warn-bg);
  color: var(--bbz-warn-text);
  font-variant-numeric: tabular-nums;
}
.au__error {
  color: var(--bbz-danger-text);
}
.au__prompt,
.au__detail {
  align-self: start;
}
</style>
