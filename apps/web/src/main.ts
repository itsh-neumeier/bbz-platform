import { createApp } from 'vue';
import { createPinia } from 'pinia';
import PrimeVue from 'primevue/config';
import 'primeicons/primeicons.css';

import './theme/index.css';
import { DbPreset } from './theme/primevue-db-preset';
import App from './App.vue';
import { router } from './router';
import { i18n } from './i18n';

createApp(App)
  .use(createPinia())
  .use(router)
  .use(i18n)
  // PrimeVue stays registered (ADR-0013 / MASTER_PROMPT §6) with a DB-flavoured
  // preset (ADR-0029). `data-mode` on <html> drives the dark scheme; PrimeVue's
  // own `.p-dark` selector is disabled so the two never disagree.
  .use(PrimeVue, { theme: { preset: DbPreset, options: { darkModeSelector: false } }, ripple: false })
  .mount('#app');
