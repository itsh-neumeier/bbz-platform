<script setup lang="ts">
/**
 * Per-role 2FA policy (#722, MASTER_PROMPT §12 / E21-05). A role with a policy
 * makes 2FA mandatory for anyone who holds it; `grace_period_days` gives a
 * newly-assigned user time to enrol. Backend: `/auth/mfa-policies`
 * (`permissions.manage`, step-up gated — the API may ask the operator to
 * re-verify their own second factor first).
 */
import { computed, onMounted, ref } from 'vue';
import { RouterLink } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { ApiError } from '@/lib/apiClient';
import { mfaPoliciesApi, rolesApi, type MfaPolicy, type Role } from '@/lib/users';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const session = useSessionStore();
const canManage = computed(() => session.can('permissions.manage'));

const roles = ref<Role[]>([]);
const policies = ref<Record<string, number>>({});
const error = ref('');
const busy = ref('');

const rows = computed(() =>
  roles.value.map((r) => ({
    ...r,
    required: r.key in policies.value,
    grace: policies.value[r.key] ?? 7,
  })),
);

async function load(): Promise<void> {
  error.value = '';
  try {
    const [r, p] = await Promise.all([rolesApi.list(), mfaPoliciesApi.list()]);
    roles.value = r;
    policies.value = Object.fromEntries(p.policies.map((x: MfaPolicy) => [x.role_key, x.grace_period_days]));
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.mfa.loadError');
  }
}

async function run(key: string, fn: () => Promise<unknown>): Promise<void> {
  busy.value = key;
  error.value = '';
  try {
    await fn();
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.mfa.saveError');
  } finally {
    busy.value = '';
  }
}

const toggle = (key: string, on: boolean) =>
  run(key, () => (on ? mfaPoliciesApi.set(key, policies.value[key] ?? 7) : mfaPoliciesApi.remove(key)));

const setGrace = (key: string, days: number) =>
  run(key, () => mfaPoliciesApi.set(key, Math.max(0, Math.min(365, Math.round(days)))));

onMounted(load);
</script>

<template>
  <div class="card">
    <div class="card-head">
      <div>
        <div class="card-title">
          {{ t('admin.mfa.title') }}
        </div>
        <div class="card-subtitle">
          {{ t('admin.mfa.subtitle') }}
        </div>
      </div>
      <RouterLink
        :to="{ name: 'admin-users' }"
        class="btn ghost sm"
      >
        {{ t('admin.mfa.back') }}
      </RouterLink>
    </div>
    <div class="card-body">
      <p
        v-if="error"
        role="alert"
        class="mfa__error"
      >
        {{ error }}
      </p>
      <table class="table">
        <thead>
          <tr>
            <th scope="col">
              {{ t('admin.mfa.colRole') }}
            </th>
            <th scope="col">
              {{ t('admin.mfa.colRequired') }}
            </th>
            <th scope="col">
              {{ t('admin.mfa.colGrace') }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="r in rows"
            :key="r.id"
          >
            <td>{{ r.name }}</td>
            <td>
              <input
                type="checkbox"
                :checked="r.required"
                :disabled="!canManage || busy === r.key"
                :aria-label="t('admin.mfa.requiredFor', { role: r.name })"
                @change="toggle(r.key, ($event.target as HTMLInputElement).checked)"
              >
            </td>
            <td>
              <input
                v-if="r.required"
                class="input mfa__grace"
                type="number"
                min="0"
                max="365"
                :value="r.grace"
                :disabled="!canManage || busy === r.key"
                :aria-label="t('admin.mfa.graceFor', { role: r.name })"
                @change="setGrace(r.key, Number(($event.target as HTMLInputElement).value))"
              >
              <span
                v-else
                class="muted"
              >—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.mfa__grace {
  width: 5rem;
}
.mfa__error {
  color: var(--bbz-danger-text);
}
</style>
