import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import { useSessionStore } from '@/stores/session';

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/features/auth/LoginView.vue'),
    meta: { public: true },
  },
  {
    path: '/',
    component: () => import('@/app/AppShell.vue'),
    children: [
      { path: '', redirect: '/arbeitsplatz' },
      {
        path: 'arbeitsplatz',
        name: 'workplace',
        component: () => import('@/pages/WorkplacePage.vue'),
      },
      {
        path: 'ereignisse',
        name: 'events',
        component: () => import('@/pages/EventsPage.vue'),
      },
      {
        path: 'ereignisse/:id',
        name: 'event-detail',
        component: () => import('@/pages/EventDetailPage.vue'),
      },
      // Archiv is folded into the Ereignisübersicht (§13.6) — keep the paths as
      // deep links: /archiv → the list filtered to archived, /archiv/:id → detail.
      { path: 'archiv', redirect: { name: 'events', query: { archiv: '1' } } },
      {
        path: 'archiv/:id',
        name: 'archive-detail',
        component: () => import('@/pages/EventDetailPage.vue'),
      },
      {
        path: 'wetterlage',
        name: 'weather',
        component: () => import('@/pages/WeatherPage.vue'),
      },
      {
        path: 'monitore',
        name: 'monitors',
        component: () => import('@/pages/MonitorPage.vue'),
      },
      {
        path: 'telefonbuch',
        name: 'phonebook',
        component: () => import('@/pages/PhonebookPage.vue'),
      },
      {
        path: 'admin/workflows',
        name: 'workflow-admin',
        component: () => import('@/pages/WorkflowAdminPage.vue'),
      },
    ],
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

let restored = false;

router.beforeEach(async (to) => {
  const session = useSessionStore();

  if (!restored) {
    restored = true;
    await session.restore();
  }

  if (to.meta.public) return true;

  if (!session.authenticated) {
    return {
      name: 'login',
      query: {
        redirect: to.fullPath,
        ...(session.expired ? { reason: 'expired' } : {}),
      },
    };
  }
  return true;
});
