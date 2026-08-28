import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';

// Route-level code splitting; pages are placeholders in the foundation phase.
const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/arbeitsplatz' },
  {
    path: '/arbeitsplatz',
    name: 'workplace',
    component: () => import('@/pages/WorkplacePage.vue'),
  },
  {
    path: '/ereignisse',
    name: 'events',
    component: () => import('@/pages/PlaceholderPage.vue'),
    props: { titleKey: 'nav.events' },
  },
  {
    path: '/wetterlage',
    name: 'weather',
    component: () => import('@/pages/PlaceholderPage.vue'),
    props: { titleKey: 'nav.weather' },
  },
  {
    path: '/telefonbuch',
    name: 'phonebook',
    component: () => import('@/pages/PlaceholderPage.vue'),
    props: { titleKey: 'nav.phonebook' },
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
