<script setup lang="ts">
/**
 * The top-left brand cell (MASTER_PROMPT §13.2, V10 mockup `.logo-cell`).
 * The DB logo is a licensed asset dropped in at `public/brand/db-logo.svg` on a
 * build host (see the README there); until it loads the "DB" wordmark stands in.
 * Runtime path, not a bundler import — a missing file just 404s → fallback.
 */
import { ref } from 'vue';

const logoUrl = '/brand/db-logo.svg';
const logoOk = ref(true);
</script>

<template>
  <header class="logocell">
    <img
      v-if="logoOk"
      class="logocell__img"
      :src="logoUrl"
      alt="Deutsche Bahn"
      width="52"
      height="37"
      @error="logoOk = false"
    >
    <span
      v-else
      class="logocell__db"
      aria-hidden="true"
    >DB</span>
    <span class="logocell__copy">
      <strong>DB InfraGO AG</strong>
      <small>Personenbahnhöfe</small>
    </span>
  </header>
</template>

<style scoped>
.logocell {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  padding: 0 1rem;
  min-width: 0;
  background: var(--bbz-surface);
  border-right: var(--bbz-border-width) solid var(--bbz-border);
  border-bottom: var(--bbz-border-width) solid var(--bbz-border);
}
.logocell__img {
  display: block;
  height: 2.3rem;
  width: auto;
  flex: none;
}
.logocell__db {
  flex: none;
  display: grid;
  place-items: center;
  width: 2.6rem;
  height: 1.8rem;
  background: var(--bbz-db-red);
  color: #fff;
  font-family: var(--bbz-font-head);
  font-weight: var(--bbz-weight-bold);
  font-size: 1.1rem;
  letter-spacing: 0.03em;
  border-radius: var(--bbz-radius-sm);
}
.logocell__copy {
  min-width: 0;
}
.logocell__copy strong {
  display: block;
  font-family: var(--bbz-font-head);
  font-size: 0.95rem;
  white-space: nowrap;
}
.logocell__copy small {
  display: block;
  color: var(--bbz-text-muted);
  font-size: 0.72rem;
  white-space: nowrap;
  margin-top: 1px;
}
@media (max-width: 980px) {
  .logocell__copy {
    display: none;
  }
}
</style>
