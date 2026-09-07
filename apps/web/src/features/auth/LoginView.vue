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

// Licensed brand assets — runtime paths, `.gitignore`d, graceful fallback (the
// same mechanism as LogoCell / public/brand/README.md).
const logoUrl = '/brand/db-logo.svg';
const logoOk = ref(true);
const bgUrl = '/brand/login-bg.jpg';
const bgOk = ref(true);

const meta = computed(() => session.meta);

const username = ref('');
const password = ref('');
const totp = ref('');
const newPassword = ref('');
const confirmPassword = ref('');
const step = ref<'credentials' | 'totp'>('credentials');
const error = ref('');
const busy = ref(false);

const usernameEl = ref<HTMLInputElement | null>(null);
const totpEl = ref<HTMLInputElement | null>(null);
const newPasswordEl = ref<HTMLInputElement | null>(null);

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
watch(mustChange, async (on) => {
  if (on) {
    await nextTick();
    newPasswordEl.value?.focus();
  }
});

function goToDestination(): Promise<unknown> {
  const dest = typeof route.query.redirect === 'string' ? route.query.redirect : '/';
  return router.replace(dest);
}

async function submit(): Promise<void> {
  if (mustChange.value) {
    await changePassword();
    return;
  }
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
    await goToDestination();
  } catch (e) {
    error.value =
      e instanceof ApiError ? errorMessage(e.code, e.message) : t('login.networkError');
  } finally {
    busy.value = false;
  }
}

async function changePassword(): Promise<void> {
  error.value = '';
  if (newPassword.value !== confirmPassword.value) {
    error.value = t('login.pwMismatch');
    return;
  }
  busy.value = true;
  try {
    await session.changePassword(password.value, newPassword.value);
    await goToDestination();
  } catch (e) {
    if (e instanceof ApiError) {
      error.value =
        e.code === 'unauthorized'
          ? t('login.currentPasswordWrong')
          : e.code === 'validation_error'
            ? t('login.newPasswordRejected')
            : errorMessage(e.code, e.message);
    } else {
      error.value = t('login.networkError');
    }
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
    <img
      v-if="bgOk"
      class="login__bg"
      :src="bgUrl"
      alt=""
      aria-hidden="true"
      @error="bgOk = false"
    >
    <div class="login__scrim" />

    <form
      class="login__card"
      aria-labelledby="login-title"
      @submit.prevent="submit"
    >
      <header class="login__brand">
        <img
          v-if="logoOk"
          class="login__logo"
          :src="logoUrl"
          alt="Deutsche Bahn"
          width="52"
          height="37"
          @error="logoOk = false"
        >
        <span
          v-else
          class="login__logo-fallback"
          aria-hidden="true"
        >DB</span>
        <span class="login__brand-copy">
          <strong>DB InfraGO AG</strong>
          <small>Personenbahnhöfe</small>
        </span>
      </header>

      <h1
        id="login-title"
        class="login__title"
      >
        {{ session.instanceName }}
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
        <div class="login__field">
          <label for="login-new-password">{{ t('login.newPassword') }}</label>
          <input
            id="login-new-password"
            ref="newPasswordEl"
            v-model="newPassword"
            name="new-password"
            type="password"
            autocomplete="new-password"
            required
          >
        </div>
        <div class="login__field">
          <label for="login-confirm-password">{{ t('login.confirmPassword') }}</label>
          <input
            id="login-confirm-password"
            v-model="confirmPassword"
            name="confirm-password"
            type="password"
            autocomplete="new-password"
            required
          >
        </div>
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
        type="submit"
        class="login__submit"
        :disabled="busy"
      >
        {{
          busy
            ? t('login.working')
            : mustChange
              ? t('login.changePasswordSubmit')
              : t('login.submit')
        }}
      </button>

      <footer class="login__foot">
        <template v-if="meta">
          <span>BBZ-OS · {{ t('versionbar.version', { v: meta.version || '—' }) }}</span>
          <span aria-hidden="true">·</span>
          <span>{{ t('versionbar.env.' + meta.environment, meta.environment) }}</span>
          <span aria-hidden="true">·</span>
          <span>{{ t('versionbar.node', { node: meta.node_id }) }}</span>
        </template>
        <span v-else>{{ t('versionbar.offline') }}</span>
      </footer>
    </form>
  </main>
</template>


<style scoped>
.login {
  position: relative;
  display: grid;
  place-items: center;
  min-height: 100vh;
  padding: 1.5rem;
  overflow: hidden;
  /* brand fallback when /brand/login-bg.jpg is absent: rails receding into
     DB-red distance — quiet, never a blank screen */
  background:
    radial-gradient(
      120% 80% at 50% 0%,
      color-mix(in srgb, var(--bbz-db-red, #ec0016) 22%, var(--bbz-bg)) 0%,
      var(--bbz-bg) 60%
    ),
    var(--bbz-bg);
}
.login__bg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  z-index: 0;
}
.login__scrim {
  position: absolute;
  inset: 0;
  z-index: 1;
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--bbz-bg) 55%, transparent) 0%,
    color-mix(in srgb, var(--bbz-bg) 78%, transparent) 100%
  );
  backdrop-filter: blur(1.5px);
}
.login__card {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  width: min(22rem, 92vw);
  padding: 1.75rem;
  background: var(--bbz-surface);
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  box-shadow: 0 12px 32px -12px rgb(0 0 0 / 35%);
}
.login__brand {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  padding-bottom: 0.9rem;
  border-bottom: 1px solid var(--bbz-border);
}
.login__logo {
  display: block;
  height: 2.3rem;
  width: auto;
  flex: none;
}
.login__logo-fallback {
  flex: none;
  display: grid;
  place-items: center;
  width: 2.6rem;
  height: 1.8rem;
  background: var(--bbz-db-red, #ec0016);
  color: #fff;
  font-family: var(--bbz-font-head);
  font-weight: var(--bbz-weight-bold);
  font-size: 1.1rem;
  letter-spacing: 0.03em;
  border-radius: var(--bbz-radius-sm);
}
.login__brand-copy {
  min-width: 0;
  line-height: 1.2;
}
.login__brand-copy strong {
  display: block;
  font-family: var(--bbz-font-head);
  font-size: 0.95rem;
}
.login__brand-copy small {
  display: block;
  color: var(--bbz-text-muted);
  font-size: 0.72rem;
  margin-top: 1px;
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
.login__foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.4rem 0.6rem;
  margin-top: 0.3rem;
  padding-top: 0.9rem;
  border-top: 1px solid var(--bbz-border);
  color: var(--bbz-text-muted);
  font-size: 0.72rem;
  letter-spacing: 0.01em;
  text-align: center;
}
</style>
