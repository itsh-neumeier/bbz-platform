import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router';
import { ADMIN_SECTIONS } from '@/lib/admin';
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
        path: 'admin',
        component: () => import('@/pages/admin/AdminPage.vue'),
        children: [
          { path: '', name: 'admin', redirect: { name: 'admin-instance' } },
          {
            path: 'instanz',
            name: 'admin-instance',
            component: () => import('@/pages/admin/AdminInstancePage.vue'),
            meta: { perm: 'system.settings.manage' },
          },
          {
            path: 'benutzer',
            name: 'admin-users',
            component: () => import('@/pages/admin/AdminUsersPage.vue'),
            meta: { perm: 'users.manage' },
          },
          {
            path: 'benutzer/mfa',
            name: 'admin-users-mfa',
            component: () => import('@/pages/admin/AdminMfaPolicyPage.vue'),
            meta: { perm: 'permissions.manage' },
          },
          {
            path: 'verzeichnis',
            name: 'admin-directory',
            component: () => import('@/pages/admin/AdminPlaceholderPage.vue'),
            meta: { perm: 'system.settings.manage', adminIssue: 723 },
          },
          {
            path: 'integrationen',
            name: 'admin-integrations',
            component: () => import('@/pages/admin/AdminPlaceholderPage.vue'),
            meta: { perm: 'integrations.configure', adminIssue: 724 },
          },
          {
            // #725 renames this to `handlungsanweisungen` + redirects the old path
            path: 'workflows',
            name: 'workflow-admin',
            component: () => import('@/pages/WorkflowAdminPage.vue'),
            meta: { perm: 'workflows.manage_templates' },
          },
          {
            path: 'trigger-regeln',
            name: 'admin-triggers',
            component: () => import('@/pages/admin/AdminPlaceholderPage.vue'),
            meta: { perm: 'technical_endpoints.manage', adminIssue: 725 },
          },
          {
            path: 'technische-endpunkte',
            name: 'admin-endpoints',
            component: () => import('@/pages/admin/AdminPlaceholderPage.vue'),
            meta: { perm: 'technical_endpoints.manage', adminIssue: 725 },
          },
          {
            path: 'system',
            name: 'admin-system',
            component: () => import('@/pages/admin/AdminSystemPage.vue'),
            meta: { perm: 'system.cluster.view' },
          },
        ],
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

  // admin sub-pages are each gated on a `*.manage`-style permission (#721).
  // Server-side enforcement is authoritative; this keeps an unauthorized user
  // from landing on a page that would only 403 its data.
  const perm = to.meta.perm as string | undefined;
  if (perm && !session.can(perm)) {
    const fallback = ADMIN_SECTIONS.find((s) => session.can(s.perm));
    return fallback ? { name: fallback.name } : { name: 'workplace' };
  }
  return true;
});
