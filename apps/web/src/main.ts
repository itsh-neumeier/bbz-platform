import { createApp } from 'vue';
import { createPinia } from 'pinia';
import PrimeVue from 'primevue/config';
import Aura from '@primevue/themes/aura';
import 'primeicons/primeicons.css';

import './theme/tokens.css';
import App from './App.vue';
import { router } from './router';
import { i18n } from './i18n';

createApp(App)
  .use(createPinia())
  .use(router)
  .use(i18n)
  .use(PrimeVue, { theme: { preset: Aura }, ripple: false })
  .mount('#app');
