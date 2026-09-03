<script setup lang="ts">
/**
 * Login (E07-02 / #97). Local provider only — OIDC redirect is Epic 21, shown
 * disabled. Handles the TOTP second-factor step and the
 * `must_change_password` state. On a *session-expiry* re-login the form is
 * preserved so the operator does not lose an in-progress username.
 */
import { computed, nextTick, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import { ApiError } from '@/lib/apiClient';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const router = useRouter();
const route = useRoute();
const session = useSessionStore();

const username = ref('');
const password = ref('');
const totp = ref('');
const step = ref<'credentials' | 'totp'>('credentials');
const error = ref('');
const busy = ref(false);

const usernameEl = ref<HTMLInputElement | null>(null);
const totpEl = ref<HTMLInputElement | null>(null);

const expired = computed(() => session.expired || route.query.reason === 'expired');
const mustChange = computed(() => session.mustChangePassword);

watch(
  step,
  async (s) => {
    await nextTick();
    (s === 'totp' ? totpEl.value : usernameEl.value)?.focus();
  },
  { immediate: true },
);

async function submit(): Promise<void> {
  error.value = '';
  busy.value = true;
  try {
    const factor = await session.login({
      username: username.value.trim(),
      password: password.value,
      totp: step.value === 'totp' ? totp.value.trim() : undefined,
    });
    if (factor.kind === 'totp') {
      step.value = 'totp';
      return;
    }
    if (factor.kind === 'webauthn') {
      error.value = t('login.webauthnUnsupported');
      return;
    }
    if (session.mustChangePassword) return;
    const dest = typeof route.query.redirect === 'string' ? route.query.redirect : '/';
    await router.replace(dest);
  } catch (e) {
    error.value =
      e instanceof ApiError ? errorMessage(e.code, e.message) : t('login.networkError');
  } finally {
    busy.value = false;
  }
}

function errorMessage(code: string, fallback: string): string {
  const key = `login.err.${code}`;
  const msg = t(key);
  return msg === key ? fallback : msg;
}

function restart(): void {
  step.value = 'credentials';
  totp.value = '';
  password.value = '';
  error.value = '';
}
</script>

<template>
  <main class="login">
    <form
      class="login__card"
      aria-labelledby="login-title"
      @submit.prevent="submit"
    >
      <h1
        id="login-title"
        class="login__title"
      >
        {{ t('app.title') }}
      </h1>

      <p
        v-if="expired"
        class="login__notice"
        role="status"
      >
        {{ t('login.expiredNotice') }}
      </p>

      <template v-if="mustChange">
        <p
          class="login__notice login__notice--warn"
          role="alert"
        >
          {{ t('login.mustChange') }}
        </p>
        <button
          type="button"
          class="login__link"
          @click="session.reset()"
        >
          {{ t('login.back') }}
        </button>
      </template>

      <template v-else-if="step === 'credentials'">
        <div class="login__field">
          <label for="login-provider">{{ t('login.provider') }}</label>
          <select
            id="login-provider"
            disabled
          >
            <option>{{ t('login.providerLocal') }}</option>
          </select>
        </div>
        <div class="login__field">
          <label for="login-username">{{ t('login.username') }}</label>
          <input
            id="login-username"
            ref="usernameEl"
            v-model="username"
            name="username"
            autocomplete="username"
            required
          >
        </div>
        <div class="login__field">
          <label for="login-password">{{ t('login.password') }}</label>
          <input
            id="login-password"
            v-model="password"
            name="password"
            type="password"
            autocomplete="current-password"
            required
          >
        </div>
      </template>

      <template v-else>
        <p
          class="login__notice"
          role="status"
        >
          {{ t('login.totpPrompt') }}
        </p>
        <div class="login__field">
          <label for="login-totp">{{ t('login.totpCode') }}</label>
          <input
            id="login-totp"
            ref="totpEl"
            v-model="totp"
            name="totp"
            inputmode="numeric"
            autocomplete="one-time-code"
            pattern="[0-9]*"
            required
          >
        </div>
        <button
          type="button"
          class="login__link"
          @click="restart"
        >
          {{ t('login.back') }}
        </button>
      </template>

      <p
        v-if="error"
        class="login__error"
        role="alert"
      >
        {{ error }}
      </p>

      <button
        v-if="!mustChange"
        type="submit"
        class="login__submit"
        :disabled="busy"
      >
        {{ busy ? t('login.working') : t('login.submit') }}
      </button>
    </form>
  </main>
</template>

<style scoped>
.login {
  display: grid;
  place-items: center;
  min-height: 100vh;
  background: var(--bbz-bg);
}
.login__card {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  width: min(22rem, 92vw);
  padding: 1.75rem;
  background: var(--bbz-surface);
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
}
.login__title {
  margin: 0 0 0.25rem;
  font-size: 1.15rem;
}
.login__field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  font-size: 0.85rem;
}
.login__field input,
.login__field select {
  padding: 0.5rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-bg);
  color: var(--bbz-text);
  font-size: 1rem;
}
.login__field input:focus-visible,
.login__submit:focus-visible,
.login__link:focus-visible {
  outline: var(--bbz-focus-width) solid var(--bbz-focus-color);
  outline-offset: 2px;
}
.login__submit {
  padding: 0.6rem;
  border: 0;
  border-radius: var(--bbz-radius);
  background: var(--bbz-accent);
  color: #fff;
  font-size: 1rem;
  cursor: pointer;
}
.login__submit:disabled {
  opacity: 0.6;
  cursor: progress;
}
.login__link {
  align-self: flex-start;
  padding: 0;
  border: 0;
  background: none;
  color: var(--bbz-accent);
  text-decoration: underline;
  cursor: pointer;
  font-size: 0.85rem;
}
.login__notice {
  margin: 0;
  font-size: 0.85rem;
  color: var(--bbz-text-muted);
}
.login__notice--warn {
  color: var(--bbz-warn-text);
}
.login__error {
  margin: 0;
  font-size: 0.85rem;
  color: var(--bbz-danger-text);
}
</style>
