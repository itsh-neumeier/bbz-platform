# @bbz/web

BBZ / 3-S-Zentrale web UI — Vue 3 + TypeScript + PrimeVue + Pinia + Vue Router +
vue-i18n.

**Foundation phase status:** app shell only (left sidebar / topbar / center
content / resizable right comms sidebar), design tokens, `prefers-reduced-motion`
contract, i18n wiring (DE), a keyboard-operable comms resize handle. No business
widgets — those arrive from Phase 3, using the existing functional mockup as the
binding UX/feature reference (no regression allowed).

## Commands

```bash
npm install
npm run dev         # http://localhost:5173, proxies /api,/health,/cluster -> :8000
npm run test        # vitest
npm run lint        # eslint incl. vuejs-accessibility (errors fail CI)
npm run typecheck   # vue-tsc
npm run e2e         # playwright smoke
```

> Node is **not** available in the current CI/dev container used to scaffold this
> repo, so the frontend test/lint steps are wired in `.github/workflows/ci.yml`
> but were not executed locally during the foundation commit. See the PR's
> "Known limitations".
