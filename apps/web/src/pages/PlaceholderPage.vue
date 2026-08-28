<script setup lang="ts">
import { useI18n } from 'vue-i18n';

const props = defineProps<{ titleKey: string }>();
const { t } = useI18n();
</script>

<template>
  <section>
    <h1>{{ t(props.titleKey) }}</h1>
    <p class="note">{{ t('foundation.notice') }}</p>
  </section>
</template>

<style scoped>
.note {
  color: var(--bbz-text-muted);
}
</style>
