<script setup lang="ts">
/**
 * A stub for an Administration section whose UI ships in a follow-up issue
 * (#722 users · #723 directory · #724 integrations · #725 trigger-rules /
 * technical endpoints). The section already appears in the sub-nav and is
 * permission-gated (#721) so the structure is testable now.
 */
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';

const { t } = useI18n();
const route = useRoute();
const issue = computed(() => Number(route.meta.adminIssue) || null);
</script>

<template>
  <div class="card">
    <div class="card-body admin-stub">
      <p class="admin-stub__lead">
        {{ t('admin.placeholder.lead') }}
      </p>
      <p
        v-if="issue"
        class="muted"
      >
        {{ t('admin.placeholder.issue', { n: issue }) }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.admin-stub {
  display: grid;
  gap: 0.4rem;
}
.admin-stub__lead {
  font-weight: var(--bbz-weight-semibold);
}
</style>
