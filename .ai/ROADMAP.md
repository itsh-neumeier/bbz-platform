# .ai/ROADMAP.md — BBZ Platform Delivery Roadmap

> **Status: ENTWURF ZUR FREIGABE.** Dieses Dokument ist die herstellerneutrale
> Umsetzungs-Roadmap. Nach Freigabe werden daraus GitHub-Milestones (ein
> Milestone pro Epic), Labels und Issues erzeugt. Es wird **kein Feature-Code**
> durch dieses Dokument erzeugt.

Quellen: `MASTER_PROMPT_CLAUDE_CODE.md`, `AGENTS.md`, `.ai/*`, alle ADRs
(`.ai/DECISIONS/ADR-0001…0018`). Bei Widerspruch gewinnt die dokumentierte
Architekturentscheidung; Änderungen nur per neuer/aktualisierter ADR.

> **Umsetzungsstand:** `docs/roadmap-status.md` führt jeden noch nicht
> gemergten Punkt mit Status, Blocker und — wo vorhanden — der jetzt noch
> machbaren Teilaufgabe. `.ai/CURRENT_STATE.md` ist das laufende Detailprotokoll.

---

## 1. Wie diese Roadmap zu lesen ist

- **Epic** = fachlich zusammenhängender Lieferblock, entspricht einem GitHub-Milestone.
- **Issue** = kleinste einzeln bearbeitbare Einheit. Genau ein Feature-Branch,
  ein PR, ein Review. Branch-Namen nach MASTER_PROMPT §18:
  `feature/<gh-issue-nr>-<kurzname>` (bzw. `fix/` `refactor/` `docs/`).
- **Issue-ID** (`E03-06`) ist nur die Roadmap-Referenz. Die echte GitHub-Nummer
  wird bei der Erzeugung eingesetzt; Abhängigkeiten werden dann auf die echten
  Nummern umgeschrieben.
- Jedes Issue folgt dem Pflicht-Template aus Abschnitt 3.
- **Definition of Done** (`.ai/DEFINITION_OF_DONE.md`) und **Task-Protokoll**
  (`.ai/TASK_PROTOCOL.md`) gelten zusätzlich für jedes Issue und werden in den
  Einzel-Issues nicht wiederholt.

### Querschnittsregeln (gelten implizit für JEDES Issue)

Diese müssen nicht je Issue neu genannt werden, sind aber immer einzuhalten
(`.ai/RULES.md`, MASTER_PROMPT §26):

1. Kein Direkt-Commit auf `main`; Issue → Branch → PR → Review → Merge.
2. Keine Integrationslogik im Core (`bbz_core.domain` importiert nichts nach außen).
3. Keine Business-Rule ausschließlich im Frontend; RBAC serverseitig.
4. Jede schreibende Operation ist idempotent (Command-Envelope, ADR-0012).
5. Jede kritische Aktion erzeugt einen unveränderlichen Audit-Eintrag (ADR-0011).
6. Keine erfundenen externen API-Verträge (CUCM, Coda, Weytec, Siedle, DWD).
7. Zeit ist UTC im Transport, `event_seq` ist der einzige Ordnungs-/Catch-up-Cursor (ADR-0017).
8. `prefers-reduced-motion` und tastaturbedienbare Nicht-Drag-Pfade sind Pflicht.
9. Secrets nie im Repo; sensible Werte referenziert per ID, nie im Klartext-Audit (ADR-0015).

---

## 2. Milestones, Phasen und Abhängigkeits-Graph

| # | Epic (Milestone) | MASTER_PROMPT-Phase | Haupt-ADRs | Kern-Abhängigkeit |
|---|---|---|---|---|
| 01 | Repository Foundation | Phase 0 (Abschluss/Härtung) | 0007–0018 | — |
| 02 | Identity / RBAC | Phase 1 | 0008 | 01 |
| 03 | Event Core | Phase 1 | 0011, 0012 | 02 |
| 04 | Audit / Domain Events | Phase 1 | 0011 | 03 |
| 05 | EPK Workflow Engine | Phase 1 | 0005, 0010 | 03, 04 |
| 06 | HA Cluster | Phase 2 | 0001, 0018 | 03, 04 |
| 07 | Web UI / PrimeVue | Phase 3 | 0013 | 02, 03, 05 |
| 08 | BBZ Desktop Client | Phase 4 | 0013 | 07, 09 |
| 09 | BBZ Client Agent | Phase 4 | 0009 | 03, 06 |
| 10 | BKU Agent | Phase 4 | 0003, 0009 | 02, 04, 09 |
| 11 | Telephony Core | Phase 5 | 0002, 0012 | 03, 04 |
| 12 | Cisco CUCM | Phase 5 | 0002, 0018 | 11, 06 |
| 13 | SIP Provider | Phase 5 | 0002 | 11 |
| 14 | Contacts / Call Priorities | Phase 6 | — | 03, 11 |
| 15 | Technical Trigger Engine | Phase 5–6 | 0004, 0010 | 04, 05, 11 |
| 16 | Coda Video / HxGN dC3 Video | Phase 5+ | 0006, 0016 | 15 |
| 17 | Siedle | Phase 5+ | 0004 | 11, 15, 16 |
| 18 | DWD Weather | Phase 7 | — | 03, 07 |
| 19 | Weytec Monitor Routing | Phase 8 | — | 02, 07 |
| 20 | Archive / Postprocessing | Phase 1+ | 0011 | 03, 04 |
| 21 | Enterprise Authentication | Phase 9 | — | 02 |
| 22 | Monitoring / Observability | fortlaufend | 0008 | 03, 06 |
| 23 | Security Hardening | fortlaufend | 0014, 0015 | 02, 06 |
| 24 | Production Deployment | fortlaufend/Abschluss | 0014 | 06, 22, 23 |

**Kritischer Pfad:** 01 → 02 → 03 → 04 → 05 → 07, parallel 06; danach 11 → 12/13
→ 15 → 16 → 17. 08/09/10 nach 06+07. 21/22/23/24 begleitend, 24 zuletzt.

### GitHub-Setup, das bei Freigabe erzeugt wird

- **Milestones:** `01 Repository Foundation` … `24 Production Deployment`.
- **Labels:** `epic:01-foundation` … `epic:24-prod-deployment`;
  `phase:0`…`phase:9`; `area:backend` `area:frontend` `area:agent`
  `area:integration` `area:infra` `area:db` `area:security` `area:a11y`;
  Bestand (`foundation`, `documentation`, …) bleibt.
- **Issue-Referenzen:** Abhängigkeiten als `Depends on #<nr>` im Body + GitHub-
  „tracked by"/Task-Listen im jeweiligen Epic-Tracking-Issue.

---

## 3. Pflicht-Template pro Issue

```
### <ID> · <Titel>
**Epic:** <nn Name> · **Phase:** <n> · **Area:** <label(s)> · **Branch:** feature/<nr>-<kurzname>

- **Ziel:** Was am Ende funktioniert (1 Satz, prüfbar).
- **Fachlicher Hintergrund:** Warum, mit Bezug auf MASTER_PROMPT/ADR/.ai.
- **Scope:** Was in diesem Branch entsteht.
- **Nicht im Scope:** Was ausdrücklich NICHT hier passiert (Abgrenzung zu Folge-Issues).
- **Abhängigkeiten:** Roadmap-IDs / Epics / externe Voraussetzungen.
- **Acceptance Criteria:** Punktweise, testbar.
- **Tests:** Konkrete Testarten/-fälle (unit/integration/API/e2e/HA/migration).
- **Security-Auswirkung:** Auth, Angriffsfläche, Secrets, Validierung.
- **HA-Auswirkung:** Active/Active, Idempotenz, Failover, Replay.
- **Permissions:** Betroffene Permission-Keys (`.ai` Permission-Katalog).
- **Audit Events:** Erzeugte Audit-/Domain-Events.
```

---

# EPIC 01 · Repository Foundation

**Milestone:** `01 Repository Foundation` · **Phase:** 0 · **Ziel des Epics:**
Foundation abschließen und härten, sodass Phase 1 auf einer freigegebenen
Architektur (ADRs Accepted), reproduzierbaren Builds und einer signierten
Release-Pipeline aufsetzen kann. Kein Domänencode.

**Stand:** Grundgerüst gemäß `.ai/CURRENT_STATE.md` liegt vor (FastAPI-Skeleton,
SDK-Pakete, Rule-DSL-Parser, Mock-Integrationen, Vue-Shell, CI/Security grün,
Python 3.13). Es fehlen die unten genannten Punkte.

### E01-01 · ADRs 0007–0018 von „Proposed" auf „Accepted" überführen
**Epic:** 01 Repository Foundation · **Phase:** 0 · **Area:** documentation · **Branch:** docs/<nr>-adr-acceptance

- **Ziel:** Alle Architektur-ADRs, die Phase 1 blockieren, sind reviewt und auf `Accepted` (oder mit begründeter offener Frage markiert).
- **Fachlicher Hintergrund:** `.ai/CURRENT_STATE.md` „Next target" nennt die ADR-Akzeptanz als Phase-1-Voraussetzung; MASTER_PROMPT §1 verbietet stille Architekturänderungen.
- **Scope:** Review-Durchgang je ADR 0007–0018; Status-Feld aktualisieren; offene Punkte je ADR explizit als „Open question" im ADR notieren; `.ai/CURRENT_STATE.md` „New ADRs"-Abschnitt nachziehen.
- **Nicht im Scope:** Inhaltliche Neukonzeption einer ADR; ADR-0009 (eigene Entscheidung in E09-01); neue ADRs.
- **Abhängigkeiten:** —
- **Acceptance Criteria:**
  - ADR 0007, 0008, 0010, 0011, 0012, 0013, 0014, 0015, 0017, 0018 tragen `Status: Accepted`.
  - Jede verbleibende Unklarheit steht als benannter Open-Point im jeweiligen ADR und in `CURRENT_STATE.md`.
  - Keine Code-Änderung im PR.
- **Tests:** Doc-only; CI `docs` + commitlint müssen grün sein.
- **Security-Auswirkung:** Keine.
- **HA-Auswirkung:** Keine.
- **Permissions:** —
- **Audit Events:** —

### E01-02 · Funktionales HTML-Mockup ins Repo übernehmen
**Epic:** 01 Repository Foundation · **Phase:** 0 · **Area:** documentation, frontend · **Branch:** docs/<nr>-commit-mockup

- **Ziel:** Das verbindliche funktionale Mockup liegt unter `docs/mockup/` und ist als Feature-/Test-Baseline referenzierbar.
- **Fachlicher Hintergrund:** MASTER_PROMPT §6/§13/§27 und `.ai/FEATURES.md` erklären das Mockup zur verbindlichen UX-Referenz; `.ai/CURRENT_STATE.md` führt „commit the functional HTML mockup" als offenen Punkt.
- **Scope:** Mockup-Dateien unverändert nach `docs/mockup/` legen; `docs/mockup/README.md` mit Herkunft/Stand; Verweis aus `.ai/FEATURES.md` und `docs/` Parity-Checkliste (Gerüst) anlegen.
- **Nicht im Scope:** Umbau des Mockups in Vue (Epic 07); inhaltliche Änderungen am Mockup.
- **Abhängigkeiten:** Mockup-Quelldateien müssen vom Auftraggeber bereitgestellt werden (externe Voraussetzung).
- **Acceptance Criteria:**
  - `docs/mockup/` enthält das lauffähige Mockup (statisch im Browser öffenbar).
  - `docs/mockup-parity-checklist.md` listet alle Feature-Punkte aus `.ai/FEATURES.md` als offene Checkboxen.
  - gitleaks/Trivy grün (keine Secrets im Mockup).
- **Tests:** Doc-only; Link-Check; Security-Scan grün.
- **Security-Auswirkung:** Mockup auf eingebettete Tokens/URLs prüfen.
- **HA-Auswirkung:** Keine.
- **Permissions:** —
- **Audit Events:** —

### E01-03 · ADR + Entscheidung: Runtime-Secret-Store
**Epic:** 01 Repository Foundation · **Phase:** 0 · **Area:** security, infra · **Branch:** docs/<nr>-adr-secret-store

- **Ziel:** Verbindliche Entscheidung für den produktiven Secret-Store (z. B. HashiCorp Vault vs. SOPS-age) als neue ADR-0019.
- **Fachlicher Hintergrund:** ADR-0015 lässt die konkrete Wahl offen („decided before staging"); `.ai/CURRENT_STATE.md` führt sie als offene Entscheidung.
- **Scope:** ADR-0019 mit Kontext, Entscheidung, Konsequenzen, Alternativen; Auswirkung auf Compose/Deploy skizzieren; `.ai/SECURITY.md`/`.ai/CURRENT_STATE.md` referenzieren.
- **Nicht im Scope:** Implementierung der Secret-Store-Anbindung (Epic 23).
- **Abhängigkeiten:** —
- **Acceptance Criteria:**
  - `.ai/DECISIONS/ADR-0019-SECRET-STORE.md` mit `Status: Accepted`.
  - Migrationspfad von „Docker-Compose-Secrets jetzt" zu Zielzustand beschrieben.
- **Tests:** Doc-only.
- **Security-Auswirkung:** Legt Grundlage für Secret-Handling fest.
- **HA-Auswirkung:** Store muss selbst HA-fähig/erreichbar auf beiden Knoten sein — in ADR adressieren.
- **Permissions:** —
- **Audit Events:** —

### E01-04 · release.yml: Image-Build, SBOM, Signatur, GHCR
**Epic:** 01 Repository Foundation · **Phase:** 0 · **Area:** infra, security · **Branch:** feature/<nr>-release-pipeline

- **Ziel:** Getaggte Releases bauen signierte, SBOM-versehene Container-Images und pushen sie nach GHCR.
- **Fachlicher Hintergrund:** MASTER_PROMPT §19 und ADR-0014 fordern SBOM, cosign-Signatur (keyless OIDC), versionierte Images, kein ungeprüftes `latest`.
- **Scope:** `.github/workflows/release.yml` (Trigger: Tag `v*`); Build `bbz-api` + `bbz-web`; Tags = git-SHA **und** SemVer; SBOM via Syft; Signatur via cosign keyless; Push GHCR; Job-Summary mit Digests.
- **Nicht im Scope:** Deployment-Automatik (Epic 24); Signatur-Verifikation beim Deploy (E24-01/E23-12); Gateway-Image (Epic 12).
- **Abhängigkeiten:** E01-01 (ADR-0014 Accepted).
- **Acceptance Criteria:**
  - Tag-Push erzeugt Images `ghcr.io/<org>/bbz-api:<semver>` + `:<sha>` (analog web).
  - Für jedes Image liegt eine SBOM als Release-Artefakt vor.
  - `cosign verify` gegen die OIDC-Identität ist im Job dokumentiert und erfolgreich.
  - Kein `latest`-Tag wird gepusht.
- **Tests:** Dry-Run auf einem Pre-Release-Tag; `cosign verify` im Workflow; Trivy-Scan des gebauten Images.
- **Security-Auswirkung:** Supply-Chain-Provenienz; OIDC-Berechtigungen minimal (`packages: write`, `id-token: write`).
- **HA-Auswirkung:** Keine (Build-Zeit).
- **Permissions:** —
- **Audit Events:** —

### E01-05 · Branch-Protection & Repo-Settings final
**Epic:** 01 Repository Foundation · **Phase:** 0 · **Area:** infra · **Branch:** docs/<nr>-branch-protection

- **Ziel:** `main` ist durch Branch-Protection abgesichert und der Sollzustand ist dokumentiert.
- **Fachlicher Hintergrund:** ADR-0014 verlangt „Branch protection on `main`: PR required, CI required, no force-push, linear history, CODEOWNERS review"; `docs/repo-settings.md` existiert als Platzhalter.
- **Scope:** `docs/repo-settings.md` vervollständigen (erforderliche Checks: `backend`, `frontend`, `conventional commits`, `docker compose config`, `gitleaks`, `pip-audit`, `trivy fs`); Anleitung + `gh api`-Snippet zum Setzen; CODEOWNERS-Review-Pflicht; Hinweis, dass Einstellung manuell/administrativ erfolgt.
- **Nicht im Scope:** Tatsächliches Setzen der Settings (Admin-Aktion des Repo-Owners) — nur dokumentieren und, falls Rechte vorhanden, per PR-Kommentar anfordern.
- **Abhängigkeiten:** E01-01.
- **Acceptance Criteria:**
  - `docs/repo-settings.md` beschreibt jeden erforderlichen Status-Check namentlich.
  - Reproduzierbarer `gh api`-Befehl für die Protection-Regel ist enthalten.
- **Tests:** Doc-only.
- **Security-Auswirkung:** Verhindert ungeprüfte/erzwungene Änderungen an `main`.
- **HA-Auswirkung:** Keine.
- **Permissions:** —
- **Audit Events:** —
- **Status (2026-09-02):** done — `docs/repo-settings.md` rewritten: the 12
  check-runs by exact name (kept in sync with the workflow `name:` values), a
  `gh api -X PUT …/branches/main/protection` snippet + a read-back one-liner,
  tag protection for `v*` (E01-04), squash-only / conversation-resolution /
  linear-history. `frontend` + `npm audit` are documented as *not yet required*
  (E01-06 / #14). Applying it is the maintainer's one-time action.

### E01-06 · Frontend-CI härten (Lockfile, `npm ci`, kein continue-on-error)
**Epic:** 01 Repository Foundation · **Phase:** 0 · **Area:** frontend, infra · **Branch:** feature/<nr>-frontend-ci-hardening

- **Ziel:** Der Frontend-CI-Job ist blockierend und reproduzierbar.
- **Fachlicher Hintergrund:** `.ai/CURRENT_STATE.md` führt den Job als `continue-on-error` bis zur ersten `apps/web`-Härtung; ADR-0014 verlangt reproduzierbare Builds.
- **Scope:** `apps/web/package-lock.json` committen; CI auf `npm ci`; `continue-on-error` entfernen; Node-Version im Workflow pinnen; Doku in `docs/DEV_SETUP.md`.
- **Nicht im Scope:** Major-Dependency-Upgrades (separates Tracking-Issue #14); neue UI-Features.
- **Abhängigkeiten:** —
- **Acceptance Criteria:**
  - `npm ci` in CI ohne Peer-Konflikte; `lint` + `typecheck` + `unit` grün und **blockierend**.
  - Lockfile im Repo; `.gitignore` lässt es zu.
  - `docs/DEV_SETUP.md` nennt die exakte Node-Version.
- **Tests:** CI-Lauf; lokal `npm ci && npm run lint && npm run typecheck && npm test`.
- **Security-Auswirkung:** Deterministische Dependency-Auflösung; kleinere Supply-Chain-Fläche.
- **HA-Auswirkung:** Keine.
- **Permissions:** —
- **Audit Events:** —

### E01-07 · Coverage-Gates & Import-Boundary-Contracts für Phase 1 vorbereiten
**Epic:** 01 Repository Foundation · **Phase:** 0 · **Area:** backend, infra · **Branch:** feature/<nr>-coverage-boundary-gates

- **Ziel:** Die in ADR-0008 zugesagten Qualitäts-Gates sind konfiguriert und greifen, sobald Phase-1-Pakete existieren.
- **Fachlicher Hintergrund:** ADR-0008: „coverage gate rises to ≥ 90% on `domain`, `authorization`, rule DSL, workflow engine when Phase 1 starts; foundation floor 70%". `import-linter` erzwingt Schichtgrenzen.
- **Scope:** `pytest`-Coverage-Konfiguration mit per-Pfad-Schwellen (Fail-under 70 global, Platzhalter-Contracts für `bbz_core.domain`, `authorization`, `bbz_rule_dsl`, `workflow_engine` mit 90); zusätzliche `import-linter`-Contracts für die künftigen Schichten (`domain ↛ infra/api/integrations_host`); dokumentiert in `docs/CONVENTIONS.md`.
- **Nicht im Scope:** Die 90%-Schwelle scharf schalten (passiert im jeweiligen Phase-1-Issue, wenn das Paket real ist).
- **Abhängigkeiten:** E01-01 (ADR-0008 Accepted).
- **Acceptance Criteria:**
  - CI schlägt fehl bei Gesamt-Coverage < 70%.
  - `import-linter` enthält benannte Contracts für alle in ADR-0008 genannten Schichten (ggf. `ignore_imports` mit TODO-Verweis, bis Paket existiert).
  - `docs/CONVENTIONS.md` beschreibt die Gate-Politik.
- **Tests:** CI; bewusst eingebauter Verstoß muss den Build brechen (im PR gezeigt, dann zurückgenommen).
- **Security-Auswirkung:** Keine direkt; erzwingt langfristig Domänen-Isolation.
- **HA-Auswirkung:** Keine.
- **Permissions:** —
- **Audit Events:** —
- **Status (2026-09-02):** done. Global 70 % floor was already enforced. Added
  two named `import-linter` contracts (rule-DSL standalone leaf; workflow engine
  domain-only) → **7 contracts, one per ADR-0008 layer**. New
  `tools/coverage_gates.py` reads `coverage.json` after pytest and checks the
  four layers (domain / authorization / rule DSL / workflow engine) against a
  90 % floor, **report-only** — the owning Phase-1 issue flips its gate to
  enforced (ratchet). Wired into the `backend` job. `docs/CONVENTIONS.md` gains
  a "Quality gates" section. The deliberate-violation demo is in the PR.

---

# EPIC 02 · Identity / RBAC

**Milestone:** `02 Identity / RBAC` · **Phase:** 1 · **Ziel des Epics:**
Serverseitige Identität, dynamische Rollen/Permissions/Scopes und ein
erzwingbarer Autorisierungs-Layer. Basis für jedes weitere schreibende Feature.
Quellen: MASTER_PROMPT §11/§12/§14, `docs/domain/permission-catalog.md`,
`.ai/SECURITY.md`, ADR-0008.

### E02-01 · DB-Schema: users, auth_identities, user_presence
**Epic:** 02 Identity / RBAC · **Phase:** 1 · **Area:** db, backend · **Branch:** feature/<nr>-schema-users

- **Ziel:** Alembic-Migration legt die Kern-Identitätstabellen reversibel an.
- **Fachlicher Hintergrund:** MASTER_PROMPT §14 Kernobjekte; §11 fordert providerbasierte Auth mit weiter möglichen lokalen Accounts; Präsenz (verfügbar/Pause/offline) ist Mockup-Feature (§13.4).
- **Scope:** Tabellen `users` (id, external_ref?, display_name, status, created/updated), `auth_identities` (user_id, provider `local|entra_oidc|ldap_ad`, subject, credentials-Ref, unique(provider,subject)), `user_presence` (user_id, state, changed_at, changed_by); SQLAlchemy-Modelle in `bbz_core.infra`; Migration up/down.
- **Nicht im Scope:** Passwort-Hashing-Logik (E02-03); Rollen/Permissions (E02-02); API (E02-09/10).
- **Abhängigkeiten:** Epic 01 (Alembic-Baseline vorhanden).
- **Acceptance Criteria:**
  - `alembic upgrade head` + `downgrade base` + `upgrade head` grün gegen echtes PostgreSQL.
  - `mypy --strict` + `ruff` clean; Modelle liegen ausschließlich in `infra`.
  - Unique-Constraint auf `(provider, subject)` vorhanden.
- **Tests:** Migration up/down/up (CI); Modell-Roundtrip-Test (insert/select) gegen Test-DB.
- **Security-Auswirkung:** Credential-Material wird referenziert, nicht inline gespeichert; keine Klartext-Spalten für Geheimnisse.
- **HA-Auswirkung:** Reine Schemaänderung; expand-only (ADR-0011 Migrationsstrategie).
- **Permissions:** —
- **Audit Events:** —

### E02-02 · DB-Schema: roles, permissions, groups, Zuordnungstabellen
**Epic:** 02 Identity / RBAC · **Phase:** 1 · **Area:** db, backend · **Branch:** feature/<nr>-schema-rbac

- **Ziel:** Migration legt das vollständig dynamische RBAC-Schema an.
- **Fachlicher Hintergrund:** MASTER_PROMPT §12: kein fest verdrahtetes Rollenmodell; Benutzer/Gruppen/Rollen/Permissions/Scopes/optionale Bedingungen.
- **Scope:** `permissions` (key, area, description), `roles` (key, name, builtin flag), `role_permissions` (role_id, permission_id, scope, condition_json?), `groups`, `group_roles`, `user_roles`, `user_groups`. Scope als Enum `global|region|bbz|workplace|own_events|assigned_events`.
- **Nicht im Scope:** Seed-Daten (E02-14); Permission-Check-Logik (E02-06); Scope-Auflösung (E02-07).
- **Abhängigkeiten:** E02-01.
- **Acceptance Criteria:**
  - Migration up/down/up grün.
  - Alle Katalog-Permissions aus `docs/domain/permission-catalog.md` sind als `permissions`-Keys darstellbar (kein Freitext-Zwang).
  - `role_permissions` kann pro Zeile einen Scope + optionale strukturierte Bedingung (Rule-DSL-JSON, ADR-0010) tragen.
- **Tests:** Migration up/down/up; Constraint-Tests (FK, unique(role,permission,scope)).
- **Security-Auswirkung:** Modelliert die gesamte Autorisierungsbasis; Bedingungen sind strukturierte Daten, kein Code.
- **HA-Auswirkung:** expand-only Schema.
- **Permissions:** —
- **Audit Events:** —

### E02-03 · Lokaler Auth-Provider: Argon2id, Login, Policy, Lockout
**Epic:** 02 Identity / RBAC · **Phase:** 1 · **Area:** backend, security · **Branch:** feature/<nr>-auth-local

- **Ziel:** Lokale Benutzer können sich mit Passwort anmelden; Fehlversuche werden begrenzt.
- **Fachlicher Hintergrund:** MASTER_PROMPT §11: lokale Accounts mit Argon2id, Sperr-/Passwortpolicy, Login-Audit; `.ai/SECURITY.md`.
- **Scope:** `bbz_core.auth.local` mit Argon2id-Hashing (parametrisiert), Passwort-Policy (Länge/Klassen/Blocklist), Lockout nach n Fehlversuchen mit Zeitfenster, Passwort-setzen/-ändern; Provider hinter `AuthProvider`-Protocol (siehe E02-04).
- **Nicht im Scope:** Session-/Token-Ausgabe (E02-05); TOTP (E02-13); Entra/LDAP (Epic 21).
- **Abhängigkeiten:** E02-01.
- **Acceptance Criteria:**
  - Falsches Passwort → generische Fehlermeldung, kein User-Enumeration-Leak.
  - Nach n Fehlversuchen ist der Account für konfiguriertes Fenster gesperrt.
  - Argon2id-Parameter aus Settings (`BBZ_`-Präfix), nicht hartkodiert.
  - Policy-Verstoß beim Setzen → strukturierter Validierungsfehler.
- **Tests:** Unit: Hash/Verify, Policy-Grenzfälle, Lockout-Zähler/Reset; Timing-neutrale Fehlerantwort.
- **Security-Auswirkung:** Kern der lokalen Authentifizierung; kein Klartext-Passwort in Logs/Audit; Lockout gegen Brute-Force.
- **HA-Auswirkung:** Lockout-Zustand in DB (beide Knoten sehen denselben Zähler).
- **Permissions:** —
- **Audit Events:** `LOGIN_SUCCEEDED`, `LOGIN_FAILED`, `ACCOUNT_LOCKED` (Audit, siehe E02-12).

### E02-04 · Auth-Provider-Abstraktion (local | entra_oidc | ldap_ad)
**Epic:** 02 Identity / RBAC · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-auth-provider-protocol

- **Ziel:** Ein `AuthProvider`-Protocol, gegen das der Rest des Systems arbeitet; nur `local` implementiert.
- **Fachlicher Hintergrund:** MASTER_PROMPT §11: „Auth muss providerbasiert sein"; lokale Accounts bleiben immer möglich.
- **Scope:** `AuthProvider`-Protocol (`authenticate`, `get_identity`, `capabilities`), Provider-Registry + Konfiguration welcher Provider aktiv ist, `identity → user`-Mapping/Provisionierungs-Hook (Stub für externe).
- **Nicht im Scope:** OIDC/LDAP-Implementierung (Epic 21); MFA-Policy (Epic 21).
- **Abhängigkeiten:** E02-01, E02-03.
- **Acceptance Criteria:**
  - `local` erfüllt das Protocol vollständig.
  - Externe Provider sind als `NotImplementedError`-Stubs mit Capability-Flags registriert (ehrlich gelabelt).
  - Aktive Provider-Liste kommt aus Settings.
- **Tests:** Unit: Registry-Auswahl, Fallback auf `local`, Protocol-Konformität von `local`.
- **Security-Auswirkung:** Zentraler Auth-Eintrittspunkt; verhindert Provider-spezifische Sonderpfade im Core.
- **HA-Auswirkung:** Zustandslos.
- **Permissions:** —
- **Audit Events:** —

### E02-05 · Session/Token-Ausgabe: sichere Cookies, Refresh, Logout, CSRF
**Epic:** 02 Identity / RBAC · **Phase:** 1 · **Area:** backend, security · **Branch:** feature/<nr>-auth-session

- **Ziel:** Nach erfolgreicher Authentifizierung erhält der Client eine sichere Session; Logout und Refresh funktionieren.
- **Fachlicher Hintergrund:** MASTER_PROMPT §22 (secure cookies/tokens, CSRF), `.ai/SECURITY.md` (secure cookies/tokens, PKCE später).
- **Scope:** Kurzlebiges Access-Token + Refresh (HttpOnly/Secure/SameSite-Cookie oder Bearer für Agents), Server-Session-Registry für Revocation, `/api/v1/auth/login|logout|refresh|me`, CSRF-Schutz für Cookie-Flows (Double-Submit oder SameSite=strict + Header-Check).
- **Nicht im Scope:** OIDC-PKCE-Flow (Epic 21); Agent-mTLS (Epic 09).
- **Abhängigkeiten:** E02-03, E02-04.
- **Acceptance Criteria:**
  - Logout invalidiert Refresh serverseitig (Revocation greift auf beiden Knoten).
  - Abgelaufenes Access-Token → 401 mit Fehler-Envelope; Refresh erneuert.
  - Schreibende Cookie-Requests ohne gültiges CSRF-Token → 403.
  - `GET /api/v1/auth/me` liefert User + effektive Permissions/Scopes.
- **Tests:** API-Tests: Login→me→refresh→logout→me(401); CSRF-Negativfall; parallele Sessions.
- **Security-Auswirkung:** Session-Fixierung/Revocation, CSRF, Cookie-Flags; Token-Signaturschlüssel als Secret.
- **HA-Auswirkung:** Session-/Revocation-Zustand in DB oder etcd, damit Failover eine gültige Session nicht verliert.
- **Permissions:** —
- **Audit Events:** `SESSION_STARTED`, `SESSION_ENDED` (Audit).

### E02-06 · Permission-Registry & Permission-Check-Service
**Epic:** 02 Identity / RBAC · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-permission-service

- **Ziel:** Ein zentraler Service beantwortet „darf User X Permission P im Scope S?".
- **Fachlicher Hintergrund:** MASTER_PROMPT §12; `.ai/RULES.md`: „Permissions are enforced server-side."
- **Scope:** Permission-Key-Registry (statische Liste, gegen `permissions`-Tabelle validiert), `authorize(user, permission, scope_ctx) -> Decision`, effektive Permissions eines Users (über Rollen+Gruppen) mit Caching pro Request; Konfliktregel dokumentiert (deny gewinnt nicht — additive Grants, kein negatives Recht in v1).
- **Nicht im Scope:** Scope-/Bedingungsauswertung im Detail (E02-07); FastAPI-Dependency (E02-08); UI.
- **Abhängigkeiten:** E02-02.
- **Acceptance Criteria:**
  - Unbekannter Permission-Key → Programmierfehler (Startup-Check), nie „silently allow".
  - Effektive Permissions aggregieren korrekt über mehrere Rollen und Gruppen.
  - Ergebnis ist deterministisch und pro Request gecacht.
- **Tests:** Unit: additive Aggregation, unbekannter Key, leere Rollen; Property-Test: Grant-Reihenfolge irrelevant.
- **Security-Auswirkung:** Alleinige Wahrheit für „erlaubt/verboten"; Fehler hier = Rechteausweitung.
- **HA-Auswirkung:** Reine Leseauswertung; Cache nur request-lokal.
- **Permissions:** alle (Infrastruktur).
- **Audit Events:** —

### E02-07 · Scope-Auflösung (global/region/bbz/workplace/own/assigned)
**Epic:** 02 Identity / RBAC · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-scope-resolver

- **Ziel:** Der Permission-Check berücksichtigt den Objekt-Scope korrekt.
- **Fachlicher Hintergrund:** MASTER_PROMPT §12 „Scopes"; Beispiel: `events.takeover` nur innerhalb eigener BBZ.
- **Scope:** `ScopeContext` (region_id, bbz_id, workplace_id, event_owner_id, event_assignee_id), Auflösungslogik je Scope-Typ, Kombination mit E02-06; Rule-DSL-Bedingung (ADR-0010) auf `role_permissions.condition_json` auswerten.
- **Nicht im Scope:** Multi-Tenancy-Ausbau (`region`/`bbz` als echte Mandanten) — nur Datenfelder + Auswertung, kein Tenant-Provisioning.
- **Abhängigkeiten:** E02-06, E05-01 (Rule-DSL `evaluate()` — falls noch nicht fertig: Bedingungsauswertung hinter Feature-Flag, hart „deny" bis DSL da).
- **Acceptance Criteria:**
  - `own_events`/`assigned_events` prüfen gegen Owner/Assignee des konkreten Objekts.
  - `bbz`-Scope verweigert objektübergreifende Aktionen über BBZ-Grenzen.
  - Ungültiger/fehlender Scope-Kontext → deny, nie allow.
- **Tests:** Unit-Matrix: jeder Scope-Typ × (erlaubt/verweigert); Bedingungs-DSL-Fälle.
- **Security-Auswirkung:** Verhindert horizontale Rechteausweitung zwischen BBZ/Arbeitsplätzen/Ereignissen.
- **HA-Auswirkung:** Zustandslos.
- **Permissions:** alle scoped Permissions.
- **Audit Events:** —

### E02-08 · Autorisierungs-Enforcement als FastAPI-Dependency
**Epic:** 02 Identity / RBAC · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-authz-dependency

- **Ziel:** Endpoints deklarieren ihre Rechteanforderung deklarativ; ohne Recht → 403 mit einheitlichem Envelope.
- **Fachlicher Hintergrund:** MASTER_PROMPT §15; ADR-0012 Fehler-Envelope; `.ai/RULES.md` serverseitig.
- **Scope:** `require(permission, scope_extractor)`-Dependency, die Auth-Kontext (E02-05) + Permission-Service (E02-06/07) verbindet; 401 vs 403 sauber getrennt; Fehlerbody `{"error": {code, message, correlation_id}}`.
- **Nicht im Scope:** Konkrete Endpoint-Verdrahtung (in den Feature-Epics); Rate-Limiting (Epic 23).
- **Abhängigkeiten:** E02-05, E02-06, E02-07.
- **Acceptance Criteria:**
  - Ein Beispiel-Endpoint mit `require("system.audit.view", global)` liefert 403 für unberechtigte, 200 für berechtigte User.
  - Unauthentifiziert → 401; authentifiziert-aber-verboten → 403; beide mit `correlation_id`.
  - Kein Endpoint kann „vergessen" zu prüfen ohne dass ein Lint/Test es meldet (Konvention + Test-Helfer).
- **Tests:** API-Tests 401/403/200; Contract-Test, dass alle `/api/v1`-Write-Routes eine `require(...)`-Dependency haben.
- **Security-Auswirkung:** Zentrale Durchsetzung; einheitliche Fehlersemantik ohne Info-Leak.
- **HA-Auswirkung:** Zustandslos.
- **Permissions:** alle.
- **Audit Events:** optional `AUTHZ_DENIED` (Audit, konfigurierbar) für sicherheitsrelevante Endpoints.

### E02-09 · RBAC-Admin-API: Rollen/Permissions/Zuordnungen
**Epic:** 02 Identity / RBAC · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-rbac-admin-api

- **Ziel:** Administratoren können Rollen anlegen, Permissions zuweisen und Rollen an User/Gruppen binden — per API.
- **Fachlicher Hintergrund:** MASTER_PROMPT §12: „Rollen können jederzeit neu erstellt werden."
- **Scope:** CRUD `/api/v1/roles`, `/api/v1/roles/{id}/permissions` (mit Scope/Bedingung), `/api/v1/users/{id}/roles`, `/api/v1/groups` + `/groups/{id}/roles`; alles mit Command-Envelope + `roles.manage`/`permissions.manage`.
- **Nicht im Scope:** Admin-UI (eigene UI-Issues in Epic 07); Directory-Sync (Epic 21).
- **Abhängigkeiten:** E02-02, E02-08, E03-03 (Command-/Idempotenz-Infrastruktur) oder E02-05 minimal.
- **Acceptance Criteria:**
  - Neue Rolle sofort in `authorize()` wirksam (kein Neustart).
  - Builtin-Rollen (E02-14) sind nicht löschbar, aber in Permissions editierbar (dokumentierte Policy).
  - Doppelter Command → identische Antwort, keine Doppelanlage.
- **Tests:** API-CRUD; Idempotenz; „neue Rolle wirkt sofort"-Integrationstest.
- **Security-Auswirkung:** Rechteverwaltung ist selbst hochprivilegiert; jede Änderung auditiert; Schutz vor Selbst-Entrechtung des letzten Admins.
- **HA-Auswirkung:** Schreibpfad idempotent; Wirkung sofort auf beiden Knoten (DB-basiert).
- **Permissions:** `roles.view` `roles.manage` `permissions.manage` `users.view`
- **Audit Events:** `ROLE_CREATED` `ROLE_UPDATED` `ROLE_DELETED` `ROLE_PERMISSION_CHANGED` `USER_ROLE_ASSIGNED` `USER_ROLE_REVOKED` (alle Audit).

### E02-10 · Users-Admin-API: CRUD, aktivieren/deaktivieren, Passwort-Reset
**Epic:** 02 Identity / RBAC · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-users-admin-api

- **Ziel:** Benutzerverwaltung für lokale Accounts über API.
- **Fachlicher Hintergrund:** MASTER_PROMPT §11/§12; Betrieb braucht Onboarding/Offboarding.
- **Scope:** CRUD `/api/v1/users`, Aktiv/Inaktiv-Toggle, administrativer Passwort-Reset (Einmal-Setzen/Force-Change), Verknüpfung `auth_identities`; `users.manage`.
- **Nicht im Scope:** Self-Service-Passwortänderung (E02-03-nahe, eigener kleiner Endpoint möglich, hier nicht); externe Identitäten (Epic 21).
- **Abhängigkeiten:** E02-01, E02-03, E02-08.
- **Acceptance Criteria:**
  - Deaktivierter User kann sich nicht mehr anmelden und verliert aktive Sessions.
  - Admin-Reset erzwingt Passwortwechsel beim nächsten Login.
  - Löschung ist „soft" (Status), harte Löschung nur mit dokumentierter Sonderregel (Audit-Integrität).
- **Tests:** API-CRUD; „deaktiviert → Login 401 + Session weg"; Force-Change-Flow.
- **Security-Auswirkung:** Account-Lebenszyklus; kein Klartext-Passwort in Response/Audit; Offboarding trennt sofort.
- **HA-Auswirkung:** Session-Invalidierung wirkt knotenübergreifend (E02-05).
- **Permissions:** `users.view` `users.manage`
- **Audit Events:** `USER_CREATED` `USER_UPDATED` `USER_DEACTIVATED` `USER_REACTIVATED` `USER_PASSWORD_RESET` (Audit).

### E02-11 · Benutzerpräsenz: verfügbar / Pause / offline
**Epic:** 02 Identity / RBAC · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-user-presence

- **Ziel:** Ein User kann seinen Präsenzstatus setzen; andere sehen ihn; er ist die Grundlage für „Ereignis übernehmen".
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.4: Nutzerstatus verfügbar/Pause/offline; Übernahme nur wenn Verantwortlicher Pause/offline.
- **Scope:** `PUT /api/v1/presence` (self), `GET /api/v1/presence` (Liste, `users.view`), Auto-offline bei Session-Ende/Timeout, Präsenz im Event-Stream publizieren.
- **Nicht im Scope:** Takeover-Logik selbst (E03-10); UI (Epic 07).
- **Abhängigkeiten:** E02-05, E03-04 (Event-Stream) — falls Stream noch nicht da: Präsenz zunächst nur per Query.
- **Acceptance Criteria:**
  - Statuswechsel ist sofort per `GET /presence` sichtbar und (falls vorhanden) im Stream.
  - Session-Ende/Heartbeat-Timeout → automatisch `offline`.
  - Nur der User selbst (oder `users.manage`) kann fremde Präsenz nicht setzen — außer explizit erlaubt.
- **Tests:** API-Tests; Timeout→offline; Stream-Publikation.
- **Security-Auswirkung:** Gering; Präsenz ist keine sensible Rechteinformation, aber Basis für Takeover-Autorisierung.
- **HA-Auswirkung:** Präsenz in DB; Heartbeat-Timeout muss auch nach Failover greifen (Server-Zeit maßgeblich).
- **Permissions:** `users.view`
- **Audit Events:** `USER_PRESENCE_CHANGED` (Domain-Event; Audit nur bei administrativ erzwungenem Wechsel).

### E02-12 · Login-Audit & Fehlversuchs-Tracking
**Epic:** 02 Identity / RBAC · **Phase:** 1 · **Area:** backend, security · **Branch:** feature/<nr>-login-audit

- **Ziel:** Alle Anmeldevorgänge (Erfolg/Fehler/Lockout) sind unveränderlich auditiert und abfragbar.
- **Fachlicher Hintergrund:** MASTER_PROMPT §11 „Login Audit"; §17 Audit-Prinzipien; `.ai/SECURITY.md`.
- **Scope:** Audit-Schreibpfad für `LOGIN_SUCCEEDED|LOGIN_FAILED|ACCOUNT_LOCKED|SESSION_STARTED|SESSION_ENDED` mit wer/wann/wo/Client/IP/Grund; Query bereits über E04-04, hier nur die Erzeugung + minimaler Filter.
- **Nicht im Scope:** Generisches Audit-Query-API (E04-04); Alerting (Epic 22).
- **Abhängigkeiten:** E02-03, E02-05, E04-02 (Audit-Write-Service) — falls E04 noch nicht: temporäre Audit-Tabelle mit Migrationshinweis.
- **Acceptance Criteria:**
  - Jeder Login-Versuch erzeugt genau einen unveränderlichen Audit-Eintrag.
  - `LOGIN_FAILED` enthält keinen Hinweis, ob der Username existierte (kein Enumeration-Leak im Audit-`message`, nur im internen Feld).
  - Einträge sind nicht per API/ORM löschbar.
- **Tests:** Unit/Integration: je Pfad ein Audit-Row; Unveränderlichkeit (Update/Delete schlägt fehl).
- **Security-Auswirkung:** Forensik-Grundlage; Brute-Force-Erkennung; keine sensiblen Daten im Klartext.
- **HA-Auswirkung:** Audit-Write in derselben TX wie Auth-Statusänderung.
- **Permissions:** `system.audit.view` (zum Lesen)
- **Audit Events:** siehe Scope.

### E02-13 · TOTP (optionale 2FA) für lokale Accounts
**Epic:** 02 Identity / RBAC · **Phase:** 1 · **Area:** backend, security · **Branch:** feature/<nr>-totp

- **Ziel:** Lokale User können TOTP aktivieren; bei aktiviertem TOTP ist es beim Login zweiter Faktor.
- **Fachlicher Hintergrund:** MASTER_PROMPT §11: „optional TOTP", „WebAuthn vorbereiten"; MFA insgesamt in Epic 21.
- **Scope:** TOTP-Secret-Erzeugung (RFC 6238), QR/otpauth-URI, Enrolment mit Verifikation, Recovery-Codes (Hash gespeichert), Login-Schritt „TOTP erforderlich"; Secret verschlüsselt at rest.
- **Nicht im Scope:** Policy „welche Rolle MUSS MFA" (Epic 21); WebAuthn (Epic 21); TOTP für externe Provider.
- **Abhängigkeiten:** E02-03, E02-05.
- **Acceptance Criteria:**
  - Enrolment erst abgeschlossen nach einem gültigen Verifikationscode.
  - Login ohne/mit falschem TOTP bei aktiviertem Faktor → 401.
  - Recovery-Code ist genau einmal verwendbar.
  - TOTP-Secret nie im Klartext in Logs/Audit/Response.
- **Tests:** Unit: Code-Fenster/Drift, Recovery-Einmaligkeit; API: Enrol→Login-Challenge→Erfolg.
- **Security-Auswirkung:** Zweiter Faktor; Secret-Verschlüsselung; Rate-Limit auf TOTP-Verifikation (Epic 23-Hook).
- **HA-Auswirkung:** Secret/Recovery-Status in DB; auf beiden Knoten identisch.
- **Permissions:** — (self-service); `users.manage` zum Zurücksetzen fremder TOTP.
- **Audit Events:** `MFA_ENROLLED` `MFA_DISABLED` `MFA_CHALLENGE_FAILED` `MFA_RECOVERY_USED` (Audit).

### E02-14 · Seed: Standardrollen & Permission-Katalog
**Epic:** 02 Identity / RBAC · **Phase:** 1 · **Area:** db, backend · **Branch:** feature/<nr>-seed-roles

- **Ziel:** Ein frisches System hat den vollständigen Permission-Katalog und die Beispielrollen als Startdaten.
- **Fachlicher Hintergrund:** MASTER_PROMPT §12 Beispielrollen (Sichtleiter, Disponent, Administrator, Nachbearbeitung, Nur Lesen); `docs/domain/permission-catalog.md`.
- **Scope:** Daten-Migration, die alle Permission-Keys anlegt und die 5 Builtin-Rollen mit sinnvollem Default-Mapping befüllt; „Administrator" erhält alle `*.manage`-Rechte; idempotent (re-runnable).
- **Nicht im Scope:** Kundenindividuelle Rollen; Scope-Feinschliff pro Kunde.
- **Abhängigkeiten:** E02-02.
- **Acceptance Criteria:**
  - Nach `alembic upgrade head` existieren alle Katalog-Permissions und 5 Builtin-Rollen.
  - Down-Migration entfernt nur die Seed-Daten, keine vom Nutzer angelegten.
  - „Nur Lesen" hat ausschließlich `*.view`-Rechte.
- **Tests:** Migration up/down; Assertion über Permission-Anzahl & Rollen-Mapping.
- **Security-Auswirkung:** Least-Privilege-Defaults; kein Default-Passwort/Default-Admin-Account hier (der wird über E02-10/Bootstrap-Doku angelegt).
- **HA-Auswirkung:** Reine Daten; expand-only.
- **Permissions:** — (definiert sie)
- **Audit Events:** —

---

# EPIC 03 · Event Core

**Milestone:** `03 Event Core` · **Phase:** 1 · **Ziel des Epics:** Das
eventorientierte Herz der Plattform: Ereignis-Aggregat mit Lebenszyklus,
Ereignisverantwortung fürs GESAMTE Ereignis, globaler `event_seq`,
Idempotenz-/Command-Infrastruktur und der Live-Event-Stream. Quellen:
MASTER_PROMPT §3/§13.3–13.7/§14/§15/§16, `docs/domain/event-catalog.md`,
ADR-0011, ADR-0012.

### E03-01 · DB-Schema: events, event_status_history, event_assignments, event_notes
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** db, backend · **Branch:** feature/<nr>-schema-events

- **Ziel:** Eine Migration legt die Ereignis-Kerntabellen reversibel an.
- **Fachlicher Hintergrund:** MASTER_PROMPT §14 Kernobjekte; Verantwortung gilt fürs ganze Ereignis (§13.4).
- **Scope:** `events` (id, uuid, title, priority `critical|high|medium|low`, status, bbz_id, workplace_id, source, version, created/updated), `event_status_history` (event_id, from, to, at, by, correlation_id), `event_assignments` (event_id, user_id, assigned_at, assigned_by, active), `event_notes` (event_id, kind `work|postprocess`, body, by, at). Optimistic-Concurrency-Spalte `version`.
- **Nicht im Scope:** Archiv-Detailmodell (Epic 20); Workflow-Verknüpfung (Epic 05).
- **Abhängigkeiten:** E02-01 (User-FKs).
- **Acceptance Criteria:** Migration up/down/up grün; `version` startet bei 1; FK-Constraints gesetzt; Modelle nur in `infra`.
- **Tests:** Migration up/down/up (CI, echtes PostgreSQL); Modell-Roundtrip.
- **Security-Auswirkung:** Keine (Schema); scope-relevante Spalten (`bbz_id`, `workplace_id`) für E02-07.
- **HA-Auswirkung:** expand-only Migration (ADR-0011).
- **Permissions:** —
- **Audit Events:** —

### E03-02 · `event_seq` + append-only `domain_events`-Log
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** db, backend · **Branch:** feature/<nr>-domain-event-log

- **Ziel:** Jede fachliche Zustandsänderung schreibt in derselben Transaktion einen `domain_events`-Eintrag mit global monoton steigender `event_seq`.
- **Fachlicher Hintergrund:** MASTER_PROMPT §3/§16; ADR-0011: `event_seq` als `BIGINT`-Identity nur auf dem PostgreSQL-Primary, Lücken toleriert, Ordnung garantiert.
- **Scope:** Tabelle `domain_events` (seq BIGINT identity, uuid, aggregate_type, aggregate_id, event_type, occurred_at_utc, node_id, user_id, client_id, command_id, correlation_id, payload jsonb, schema_version); `append_event(...)`-Helfer, der NUR innerhalb einer laufenden DB-TX aufrufbar ist; Envelope-Validierung gegen `packages/event-schemas`.
- **Nicht im Scope:** Stream-Endpoint (E03-04/05); Outbox (Epic 04).
- **Abhängigkeiten:** E03-01, Epic 01 (event-schemas-Paket).
- **Acceptance Criteria:** `event_seq` strikt monoton pro Primary; `append_event` außerhalb einer TX → Fehler; Payload gegen Envelope-Schema validiert; `schema_version` Pflicht.
- **Tests:** Integration: nebenläufige Inserts → keine Duplikate/Umkehrungen; Envelope-Schemaverstoß → Reject; „append ohne TX" → Fehler.
- **Security-Auswirkung:** Kein Löschen/Ändern (nur Insert); Grants entsprechend (Hook zu E04-10).
- **HA-Auswirkung:** Single-Writer-Primary garantiert Monotonie; nach Failover setzt die Sequence auf dem neuen Primary fort (Lücke toleriert).
- **Permissions:** —
- **Audit Events:** infrastruktur (schreibt alle Domain-Events).

### E03-03 · `commands`-Tabelle + Idempotenz-Service
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-command-idempotency

- **Ziel:** Ein doppelt gesendeter Command (gleiche `X-Command-Id`) liefert das Originalergebnis zurück, ohne die Aktion erneut auszuführen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §15; ADR-0012: Duplicate `command_id` → Originalantwort; ADR-0011: `commands` speichert Idempotency-Key + Result-Hash.
- **Scope:** `commands` (command_id PK, user_id, endpoint, request_hash, result_json, result_status, created_at); Dekorator/Contextmanager `idempotent(command_id)`; Integration in den Write-Pfad; Behandlung „gleicher Key, anderer Body" → 409/Fehler.
- **Nicht im Scope:** Offline-Outbox des Clients (Epic 09); Envelope-Header-Parsing (bereits als `CommandEnvelope` im Skeleton, hier anbinden).
- **Abhängigkeiten:** E03-01.
- **Acceptance Criteria:** Zweiter identischer Command → gleiche Response, keine zweite Wirkung; gleicher Key + abweichender Body → definierter Fehler; abgelaufene/aufgeräumte Keys dokumentiert.
- **Tests:** API: doppelter POST → identische Antwort, ein Domain-Event; Race (parallele identische Commands) → genau eine Ausführung.
- **Security-Auswirkung:** Verhindert Replay-basierte Doppelwirkung; Key an User gebunden.
- **HA-Auswirkung:** Kern der Active/Active-Sicherheit; `commands`-Tabelle auf dem Primary, beide App-Knoten prüfen dagegen.
- **Permissions:** —
- **Audit Events:** —

### E03-04 · Ereignis-Aggregat & Zustandsautomat
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-event-aggregate

- **Ziel:** Ein reines Domänen-Aggregat kapselt die erlaubten Ereignis-Übergänge und erzeugt die passenden Domain-Events.
- **Fachlicher Hintergrund:** MASTER_PROMPT §3 Event-Liste; §13 Ereignislebenszyklus; ADR-0008 `domain/` ist pure.
- **Scope:** Zustände `new → accepted → acknowledged → opened → (archived) → (reactivated→opened)`; Übergangsfunktionen mit Vorbedingungen; erzeugte Events `EVENT_CREATED/ACCEPTED/ACKNOWLEDGED/OPENED/ASSIGNED/TAKEN_OVER/ARCHIVED/REACTIVATED`; keine I/O im Aggregat.
- **Nicht im Scope:** Persistenz/Repository (E03-05); API (E03-06 ff.); Workflow-Start (Epic 05).
- **Abhängigkeiten:** E03-01 (Statusbegriffe), `domain`-Schicht aus Epic 01.
- **Acceptance Criteria:** Ungültiger Übergang → Domänen-Fehler, kein Event; jeder gültige Übergang liefert deterministisch die korrekte Event-Liste; 100 % Branch-Coverage (ADR-0008-Gate).
- **Tests:** Unit: vollständige Übergangsmatrix (gültig/ungültig); Property-Test: nie Event ohne Zustandsänderung.
- **Security-Auswirkung:** Keine (pure); Regeln hier statt im Frontend (`.ai/RULES.md`).
- **HA-Auswirkung:** Zustandslos/deterministisch → auf beiden Knoten identisch.
- **Permissions:** — (Rechteprüfung im API-Layer).
- **Audit Events:** definiert die Domain-Events; Audit in E04.

### E03-05 · Event-Repository & Unit-of-Work (State + Event in einer TX)
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** backend, db · **Branch:** feature/<nr>-event-repository

- **Ziel:** Ein Repository persistiert Aggregat-Zustand und schreibt die Domain-Events atomar in derselben Transaktion.
- **Fachlicher Hintergrund:** ADR-0011: „every state mutation must also append its event in-tx"; kein Event-Sourcing, sondern State + Log.
- **Scope:** `EventRepository` (load/save), Unit-of-Work, der `append_event` (E03-02) + `event_status_history` + `version`-Increment atomar macht; Optimistic-Concurrency-Check gegen `X-Expected-Version`.
- **Nicht im Scope:** Query-Modelle (E03-11); Outbox-Dispatch (Epic 04).
- **Abhängigkeiten:** E03-02, E03-04.
- **Acceptance Criteria:** State-Änderung ohne zugehörigen Event-Insert ist nicht möglich (Test erzwingt es); Version-Konflikt → definierter Fehler (→ 409 im API); Rollback lässt weder State noch Event zurück.
- **Tests:** Integration: erzwungener Fehler nach State-Write → nichts persistiert; Concurrency: zwei Saves mit gleicher erwarteter Version → einer 409.
- **Security-Auswirkung:** Keine direkt.
- **HA-Auswirkung:** Atomarität State+Event ist Voraussetzung für konsistenten Catch-up.
- **Permissions:** —
- **Audit Events:** —

### E03-06 · Command: Ereignis erstellen
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-event-create

- **Ziel:** `POST /api/v1/events` legt ein Ereignis mit Priorität an und erzeugt `EVENT_CREATED`.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.3 Prioritäten kritisch/hoch/mittel/niedrig; §15 Command-Envelope.
- **Scope:** Endpoint mit `require("events.create", scope)`, Command-Envelope, Validierung (Titel, Priorität, bbz/workplace), Aggregat-Aufruf, Persistenz, Response mit `version` + Location.
- **Nicht im Scope:** Trigger-basierte Erstellung (Epic 15/16); Workflow-Anhang (Epic 05).
- **Abhängigkeiten:** E02-08, E03-03, E03-05.
- **Acceptance Criteria:** Berechtigter User erzeugt Ereignis (201 + `EVENT_CREATED`); unberechtigt → 403; doppelter Command → identische Antwort, ein Event; ungültige Priorität → 422.
- **Tests:** API: 201/403/422/Idempotenz; Domain-Event geschrieben.
- **Security-Auswirkung:** Rechte-/Scope-Prüfung; Eingabevalidierung.
- **HA-Auswirkung:** Idempotent über `command_id`.
- **Permissions:** `events.create`
- **Audit Events:** `EVENT_CREATED` (Domain + Audit).

### E03-07 · Commands: annehmen / quittieren / öffnen
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-event-accept-ack-open

- **Ziel:** Die drei Kern-Übergänge sind je ein Endpoint mit korrekter Rechte- und Zustandsprüfung.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.3/§13.5: Maßnahmen erst nach Annahme+Quittierung bearbeitbar.
- **Scope:** `POST /events/{id}/accept|acknowledge|open`, jeweils `X-Expected-Version`, Aggregat-Übergang, Events `EVENT_ACCEPTED/ACKNOWLEDGED/OPENED`.
- **Nicht im Scope:** Maßnahmen-Bearbeitung (Epic 05); UI (Epic 07).
- **Abhängigkeiten:** E03-06.
- **Acceptance Criteria:** Reihenfolge erzwungen (open vor accept → 409/Domänenfehler); Version-Konflikt → 409 mit aktuellem Stand in `details`; je Übergang genau ein Domain-Event.
- **Tests:** API: Happy Path + falsche Reihenfolge + Version-Konflikt + Idempotenz.
- **Security-Auswirkung:** Scope `assigned_events`/`bbz` je nach Konfiguration.
- **HA-Auswirkung:** Idempotent; Optimistic Concurrency.
- **Permissions:** `events.accept` `events.acknowledge` `events.open`
- **Audit Events:** `EVENT_ACCEPTED` `EVENT_ACKNOWLEDGED` `EVENT_OPENED`.

### E03-08 · Command: Ereignis bearbeiten (Felder, Optimistic Concurrency)
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-event-edit

- **Ziel:** `PATCH /events/{id}` ändert erlaubte Felder mit Optimistic Concurrency.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.5/§15; Konflikt → HTTP 409 mit neuem Serverstand.
- **Scope:** Editierbare Felder (Titel, Beschreibung, Priorität soweit erlaubt), `require("events.edit")`, `X-Expected-Version` Pflicht, `EVENT_UPDATED` Domain-Event mit Vorher/Nachher.
- **Nicht im Scope:** Prioritätsänderung mit Sondereskalation; Statusübergänge (E03-07/11).
- **Abhängigkeiten:** E03-06.
- **Acceptance Criteria:** Konflikt → 409 + aktuelle Repräsentation; nur Whitelist-Felder; Vorher/Nachher im Event-Payload.
- **Tests:** API: Erfolg, 409, Whitelist-Verstoß (422), Idempotenz.
- **Security-Auswirkung:** Feld-Whitelist verhindert unbeabsichtigte Änderungen; Audit mit Diff.
- **HA-Auswirkung:** Optimistic Concurrency + Idempotenz.
- **Permissions:** `events.edit`
- **Audit Events:** `EVENT_UPDATED` (Domain + Audit mit Diff).

### E03-09 · Ereignisverantwortung: an Nutzer übertragen
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-event-assign

- **Ziel:** Ein berechtigter Nutzer überträgt die Verantwortung für das gesamte Ereignis an einen Nutzer.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.4: Verantwortung fürs GESAMTE Ereignis, nicht pro Schritt.
- **Scope:** `POST /events/{id}/assign` (target_user_id), setzt `event_assignments` aktiv, deaktiviert vorherige, `EVENT_ASSIGNED`; Regeln: Ziel muss existierend/aktiv sein.
- **Nicht im Scope:** Übernahme durch Dritte (E03-10); Schrittzuweisung (existiert nicht).
- **Abhängigkeiten:** E03-06, E02-11 (Präsenz für spätere Regel).
- **Acceptance Criteria:** Genau ein aktiver Assignee pro Ereignis; Wechsel erzeugt genau ein `EVENT_ASSIGNED`; Selbstzuweisung erlaubt bei `events.assign`.
- **Tests:** API: Zuweisung/Neuzuweisung, ungültiges Ziel, Idempotenz; Invariante „ein aktiver Assignee".
- **Security-Auswirkung:** `events.assign`, Scope `bbz`.
- **HA-Auswirkung:** Idempotent; Assignee-Wechsel ist ein einzelner atomarer Übergang.
- **Permissions:** `events.assign`
- **Audit Events:** `EVENT_ASSIGNED` (Domain + Audit).

### E03-10 · Ereignisverantwortung: übernehmen (nur bei Pause/offline)
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-event-takeover

- **Ziel:** Ist der Verantwortliche in Pause/offline, kann ein berechtigter Nutzer das Ereignis übernehmen — auditiert.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.4: „Wenn Verantwortlicher Pause/offline: berechtigte Nutzer können Ereignis übernehmen. Übernahmen müssen auditiert werden."
- **Scope:** `POST /events/{id}/takeover`; Vorbedingung: aktueller Assignee-Präsenz ∈ {Pause, offline}; setzt neuen aktiven Assignee; `EVENT_TAKEN_OVER`; Pflicht-Audit mit Grund optional.
- **Nicht im Scope:** Erzwungene Übernahme trotz „verfügbar" (bewusst nicht erlaubt).
- **Abhängigkeiten:** E03-09, E02-11, E02-07 (Scope).
- **Acceptance Criteria:** Übernahme bei „verfügbar" → 409/verboten; bei Pause/offline → Erfolg + `EVENT_TAKEN_OVER` + Audit; Scope `bbz` erzwungen.
- **Tests:** API: alle Präsenzzustände × berechtigt/unberechtigt; Audit-Eintrag vorhanden; Idempotenz.
- **Security-Auswirkung:** Kritische Aktion — immer Audit; Scope verhindert BBZ-übergreifende Übernahme.
- **HA-Auswirkung:** Idempotent; Präsenz-Check gegen serverseitigen Stand (nicht Client).
- **Permissions:** `events.takeover` (Scope `bbz`)
- **Audit Events:** `EVENT_TAKEN_OVER` (Domain + **Pflicht-Audit** mit vorher/nachher Assignee).

### E03-11 · Commands: archivieren & reaktivieren (mit Bestätigung)
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-event-archive-reactivate

- **Ziel:** Ereignisse können archiviert und — nur mit expliziter Bestätigung — reaktiviert werden.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.6/§26: „Keine Reaktivierung ohne explizite Bestätigung"; archivierte Ereignisse nie hart löschen.
- **Scope:** `POST /events/{id}/archive` → `EVENT_ARCHIVED`, verlässt Arbeitswarteschlange; `POST /events/{id}/reactivate` erfordert `confirm=true` + Grund → `EVENT_REACTIVATED`, zurück in die Warteschlange.
- **Nicht im Scope:** Archiv-Detailansicht/Notizen (Epic 20); UI-Popup (Epic 07).
- **Abhängigkeiten:** E03-07.
- **Acceptance Criteria:** Reaktivierung ohne `confirm` → 422/abgelehnt; archiviertes Ereignis erscheint nicht in der Work-Queue-Query; beide Übergänge auditiert; kein Hard-Delete-Pfad existiert.
- **Tests:** API: Archiv → Queue-Query leer; Reaktivierung ohne/mit confirm; Idempotenz; „kein DELETE-Endpoint" Contract-Test.
- **Security-Auswirkung:** `events.archive`/`events.reactivate`; Pflicht-Audit; Schutz vor unbeabsichtigter Reaktivierung.
- **HA-Auswirkung:** Idempotent.
- **Permissions:** `events.archive` `events.reactivate`
- **Audit Events:** `EVENT_ARCHIVED` `EVENT_REACTIVATED` (Domain + **Pflicht-Audit**).

### E03-12 · Queries: Arbeitswarteschlange, Ereignisliste, Ereignisdetail
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-event-queries

- **Ziel:** Read-Endpoints für die drei zentralen Ansichten des Mockups.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.3 (gemeinsame Arbeitswarteschlange), §13.6 (Ereignisse-Ansicht chronologisch inkl. Archiv).
- **Scope:** `GET /events?queue=active` (nicht archiviert, Prioritätssortierung), `GET /events` (chronologisch, inkl. archiviert, Filter/Pagination), `GET /events/{id}` (Detail inkl. Statushistorie, Assignee, Notizen).
- **Nicht im Scope:** Stream (E03-13/14); Export (E03-16).
- **Abhängigkeiten:** E03-01, E02-08.
- **Acceptance Criteria:** `queue=active` enthält keine archivierten; Sortierung kritisch→niedrig, dann Alter; `events.view` + Scope-Filter angewendet (User sieht nur erlaubte BBZ/Scopes); stabile Pagination per `event_seq`/id.
- **Tests:** API: Queue-Abgrenzung, Sortierung, Scope-Filter, Pagination-Stabilität.
- **Security-Auswirkung:** Scope-gefilterte Sicht; kein Datenleck über BBZ-Grenzen.
- **HA-Auswirkung:** Reine Reads; von Standby-Lesereplika bedienbar (später).
- **Permissions:** `events.view`
- **Audit Events:** —

### E03-13 · Event-Stream: SSE mit `after_seq`-Catch-up
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-event-stream-sse

- **Ziel:** `GET /api/v1/events/stream?after_seq=N` liefert verpasste Events ab `N` und dann live.
- **Fachlicher Hintergrund:** MASTER_PROMPT §16: Catch-up ab letztem bestätigten `event_seq`, danach Live; ADR-0011.
- **Scope:** SSE-Endpoint, Catch-up-Query aus `domain_events` ab `after_seq`, danach Live-Fan-out (In-Process-Pub/Sub + DB-Poll/LISTEN als Fallback), Heartbeat, Scope-Filterung pro Verbindung.
- **Nicht im Scope:** WebSocket-Variante (E03-14); Client-Offline-Outbox (Epic 09).
- **Abhängigkeiten:** E03-02, E02-05.
- **Acceptance Criteria:** Nach Reconnect mit `after_seq` gehen keine Events verloren und keine doppelt (bei-once-Semantik ≥); Backpressure/Heartbeat vorhanden; nur scope-erlaubte Events werden ausgeliefert.
- **Tests:** Integration: Events während „offline" erzeugt → beim Reconnect nachgeliefert; Ordnung = `event_seq`; Scope-Filter.
- **Security-Auswirkung:** Authn/Authz pro Stream; keine Cross-Scope-Leaks.
- **HA-Auswirkung:** Client hält Verbindung zu einem Knoten; nach Serverwechsel Catch-up per `after_seq` gegen den anderen Knoten (identischer `domain_events`-Log).
- **Permissions:** `events.view`
- **Audit Events:** —

### E03-14 · Event-Stream: WebSocket-Variante
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-event-stream-ws

- **Ziel:** `/ws/events?after_seq=N` bietet dieselbe Semantik wie SSE für bidirektionale Clients.
- **Fachlicher Hintergrund:** MASTER_PROMPT §16 nennt WebSocket **oder** SSE; Kiosk/Agent profitieren von WS.
- **Scope:** WS-Endpoint, gemeinsame Catch-up-/Fan-out-Logik mit E03-13 (geteilter Service), Ping/Pong, saubere Close-Codes, ACK-Cursor-Nachricht vom Client.
- **Nicht im Scope:** Command-Versand über WS (bleibt REST, ADR-0012).
- **Abhängigkeiten:** E03-13.
- **Acceptance Criteria:** Funktionsgleich zu SSE bzgl. Catch-up/Ordnung/Scope; Client-ACK aktualisiert den serverseitigen „last delivered"-Hinweis (nur Optimierung, nicht Wahrheit).
- **Tests:** Integration: Reconnect-Catch-up; parallele SSE- und WS-Clients erhalten dieselbe Sequenz.
- **Security-Auswirkung:** Wie E03-13; Origin-Check.
- **HA-Auswirkung:** Wie E03-13.
- **Permissions:** `events.view`
- **Audit Events:** —

### E03-15 · Query: globale Prioritätswarnung (unangenommene high/critical)
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-priority-warning-query

- **Ziel:** Ein Endpoint liefert, ob mindestens ein hohes/kritisches Ereignis noch NICHT angenommen wurde (für die Topbar-Warnung).
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.7: auf allen Seiten außer Arbeitsplatz auffällige Warnung; Klick öffnet das Ereignis.
- **Scope:** `GET /events/priority-alert` → `{active: bool, events: [{id, priority, title}]}`; scope-gefiltert; auch als Stream-Signal (Domain-Event `PRIORITY_ALERT_CHANGED` optional).
- **Nicht im Scope:** UI-Darstellung (Epic 07).
- **Abhängigkeiten:** E03-12.
- **Acceptance Criteria:** Reagiert korrekt auf Statuswechsel (accept setzt `active` ggf. zurück); nur scope-sichtbare Ereignisse zählen.
- **Tests:** API: create high → active true; accept → active false; Scope-Isolation.
- **Security-Auswirkung:** Scope-Filter.
- **HA-Auswirkung:** Reine Query.
- **Permissions:** `events.view`
- **Audit Events:** —

### E03-16 · Ereignis-Notizen & Export
**Epic:** 03 Event Core · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-event-notes-export

- **Ziel:** Notizen an Ereignisse hängen und ein Ereignis (inkl. Historie) exportieren.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.6 Nachbearbeitungsnotizen; §12 `events.export`.
- **Scope:** `POST /events/{id}/notes` (kind `work`), `GET /events/{id}/export` (JSON-Bundle: Ereignis + Statushistorie + Notizen + zugehörige Domain-Events); Postprocess-Notizen kommen in Epic 20.
- **Nicht im Scope:** PDF-Rendering (Epic 20); Bulk-Export.
- **Abhängigkeiten:** E03-01, E03-12.
- **Acceptance Criteria:** Notiz erzeugt `EVENT_NOTE_ADDED`; Export enthält vollständige Historie und ist deterministisch geordnet (`event_seq`); `events.export` erforderlich.
- **Tests:** API: Notiz-CRUD-Teil, Export-Vollständigkeit/Ordnung, Rechteprüfung.
- **Security-Auswirkung:** Export kann sensible Daten enthalten → `events.export` + Scope; Audit des Exports.
- **HA-Auswirkung:** Reads + ein idempotenter Write (Notiz).
- **Permissions:** `events.postprocess` (Notiz) `events.export`
- **Audit Events:** `EVENT_NOTE_ADDED` (Domain); `EVENT_EXPORTED` (Audit).

---

# EPIC 04 · Audit / Domain Events

**Milestone:** `04 Audit / Domain Events` · **Phase:** 1 · **Ziel des Epics:**
Unveränderliches Audit, das in derselben Transaktion wie die Zustandsänderung
entsteht, plus die transaktionale Outbox/Inbox-Infrastruktur für exactly-once
Active/Active. Quellen: MASTER_PROMPT §3/§17, ADR-0011, `.ai/SECURITY.md`.

### E04-01 · DB-Schema: audit_events (append-only, vorher/nachher)
**Epic:** 04 · **Phase:** 1 · **Area:** db, backend · **Branch:** feature/<nr>-schema-audit

- **Ziel:** Migration legt die unveränderliche Audit-Tabelle an.
- **Fachlicher Hintergrund:** MASTER_PROMPT §17: wer/wann/wo/Arbeitsplatz/Client/Aktion/vorher/nachher/Grund/correlation_id.
- **Scope:** `audit_events` (id, occurred_at_utc, actor_user_id, actor_client_id, workplace_id, node_id, action, target_type, target_id, before jsonb, after jsonb, reason, correlation_id, event_seq_ref). Kein `updated_at`/kein Delete-Pfad.
- **Nicht im Scope:** Write-Service (E04-02); Integritätsmechanismus (E04-10); Query (E04-04).
- **Abhängigkeiten:** E02-01, E03-01.
- **Acceptance Criteria:** Migration up/down/up grün; nur INSERT im ORM-Mapping erlaubt; alle §17-Felder vorhanden.
- **Tests:** Migration up/down/up; Modell verweigert UPDATE/DELETE.
- **Security-Auswirkung:** Grundlage der Nachvollziehbarkeit; keine Geheimnis-Spalten.
- **HA-Auswirkung:** expand-only.
- **Permissions:** — · **Audit Events:** —

### E04-02 · Audit-Write-Service (in-TX mit Zustandsänderung)
**Epic:** 04 · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-audit-write-service

- **Ziel:** `write_audit(...)` schreibt garantiert in derselben TX wie die auslösende Änderung.
- **Fachlicher Hintergrund:** MASTER_PROMPT §17/§26.12: „Jede kritische Aktion muss Audit erzeugen."
- **Scope:** Service + Unit-of-Work-Integration; standardisierte `action`-Keys; Diff-Helfer (before/after); Pflicht-Reason für definierte Aktionen.
- **Nicht im Scope:** Konkrete Verdrahtung je Feature (E04-03 + Feature-Epics).
- **Abhängigkeiten:** E04-01, E03-05.
- **Acceptance Criteria:** Audit ohne begleitende TX → Fehler; Rollback der Fach-TX rollt Audit mit zurück; Reason-Pflicht erzwungen für markierte Aktionen.
- **Tests:** Integration: Fehler nach State-Write → kein Audit-Row; Reason fehlt bei Pflicht-Aktion → Fehler.
- **Security-Auswirkung:** Verhindert „Aktion ohne Spur".
- **HA-Auswirkung:** Atomarität State+Audit.
- **Permissions:** — · **Audit Events:** infrastruktur.

### E04-03 · Kritische Aktionen verdrahten (Übernahme/Übergabe/Archiv/Reaktivierung)
**Epic:** 04 · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-audit-critical-actions

- **Ziel:** Die in §17 genannten kritischen Aktionen erzeugen nachweislich Audit.
- **Fachlicher Hintergrund:** MASTER_PROMPT §17-Liste: Übernahme, Übergabe, Archivierung, Reaktivierung, Rollenänderungen, Integrationsänderungen, Monitorrouting, Anrufdokumentation.
- **Scope:** Audit-Aufrufe in E03-09/10/11 und E02-09/10 verankern; Contract-Test „jede kritische Aktion → Audit".
- **Nicht im Scope:** Telefonie/Monitor/Integrationen (deren eigene Epics rufen `write_audit` selbst — hier nur der Contract-Test, der es erzwingt).
- **Abhängigkeiten:** E04-02, E03-09/10/11.
- **Acceptance Criteria:** Für jede kritische Aktion existiert ein Test, der genau einen Audit-Eintrag mit before/after prüft; fehlender Audit-Call bricht CI.
- **Tests:** Integration je Aktion; Registry-basierter „critical action → audit"-Contract-Test.
- **Security-Auswirkung:** Lückenlosigkeit.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** alle kritischen.

### E04-04 · Audit-Query-API
**Epic:** 04 · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-audit-query-api

- **Ziel:** `GET /api/v1/audit` mit Filtern und Pagination für Berechtigte.
- **Fachlicher Hintergrund:** MASTER_PROMPT §12 `system.audit.view`.
- **Scope:** Filter (actor, target_type/id, action, Zeitraum, correlation_id), stabile Pagination, Scope-Filter; nur lesend.
- **Nicht im Scope:** Export (E20-06); UI (Epic 07).
- **Abhängigkeiten:** E04-01, E02-08.
- **Acceptance Criteria:** `system.audit.view` Pflicht; Ergebnisse scope-gefiltert; keine Schreiboperation erreichbar; deterministische Ordnung.
- **Tests:** API: Filterkombinationen, Rechteprüfung, Scope-Isolation, Pagination-Stabilität.
- **Security-Auswirkung:** Sichtbarkeit sensibler Vorgänge streng an Permission gebunden.
- **HA-Auswirkung:** Read-only.
- **Permissions:** `system.audit.view` · **Audit Events:** optional `AUDIT_QUERIED`.

### E04-05 · Domain-Event-Envelope & schema_version-Policy finalisieren
**Epic:** 04 · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-event-envelope-finalize

- **Ziel:** Der Envelope aus `packages/event-schemas` ist final und jede `event_type`-Payload hat ein versioniertes Schema.
- **Fachlicher Hintergrund:** ADR-0011: „Phase 1 finalizes payloads and `schema_version` policy"; `docs/domain/event-catalog.md`.
- **Scope:** Envelope-Felder gegen MASTER_PROMPT §3 abgleichen; JSON-Schemas je `event_type` (mind. die Event-/Call-/Contact-/Monitor-/Weather-Typen); Loader + Validierung im `append_event`-Pfad; Versionierungsregel (additive minor, breaking → neue major + Migrationsnotiz).
- **Nicht im Scope:** Telefonie-Normalisierung im Detail (Epic 11).
- **Abhängigkeiten:** E03-02, Epic 01 (Paket).
- **Acceptance Criteria:** Jeder in Phase 1 erzeugte Domain-Event validiert gegen sein Schema; unbekannter `event_type` oder fehlende `schema_version` → Reject; Policy in `docs/domain/event-catalog.md` dokumentiert.
- **Tests:** Schema-Validierungstests je Typ; Negativfälle.
- **Security-Auswirkung:** Keine sensiblen Rohdaten im Payload (Policy).
- **HA-Auswirkung:** Stabiler Vertrag für Catch-up/Replay.
- **Permissions:** — · **Audit Events:** —

### E04-06 · Transaktionale Outbox + Dispatcher-Worker
**Epic:** 04 · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-outbox

- **Ziel:** Externe Seiteneffekte werden in-TX als Outbox-Zeilen geschrieben und von einem Worker idempotent zugestellt.
- **Fachlicher Hintergrund:** ADR-0011: „Transactional outbox … idempotent on `provider_event_id + rule_version + action_index`"; MASTER_PROMPT §29 Active/Active.
- **Scope:** `external_action_outbox` (id, dedupe_key unique, action_type, payload, status, attempts, next_attempt_at, result); Worker mit Backoff/Retry; Handler-Registry (zunächst nur `notify`/`noop`).
- **Nicht im Scope:** Konkrete Handler für Telefonie/Kamera/Tür (Epics 11/16/17); Singleton-Wahl (E04-08).
- **Abhängigkeiten:** E03-05.
- **Acceptance Criteria:** Doppelte Outbox-Zeile mit gleichem `dedupe_key` unmöglich (unique); Worker liefert genau einmal erfolgreich zu; fehlgeschlagene Zustellung wird mit Backoff wiederholt und nach Limit als `failed` sichtbar.
- **Tests:** Integration: dedupe_key-Konflikt; Retry/Backoff; „genau einmal" trotz Worker-Neustart.
- **Security-Auswirkung:** Verhindert Doppelaktionen (Tür, Alarm).
- **HA-Auswirkung:** Kernbaustein exactly-once; Worker als Singleton (E04-08).
- **Permissions:** — · **Audit Events:** `EXTERNAL_ACTION_DISPATCHED` `EXTERNAL_ACTION_FAILED` (Audit).

### E04-07 · Provider-Event-Inbox + Dedupe
**Epic:** 04 · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-provider-inbox

- **Ziel:** Eingehende externe Events werden vor jeder Regelauswertung persistiert und dedupliziert.
- **Fachlicher Hintergrund:** ADR-0011: „Provider-event inbox … deduplicated before any trigger/rule evaluation"; `.ai/TECHNICAL_TRIGGERS.md`.
- **Scope:** `provider_event_inbox` (id, provider, provider_event_id, dedupe_key unique, raw_ref/hash, normalized jsonb, received_at, processed_at); `ingest(provider_event)` → persistiert + gibt „neu/duplikat" zurück.
- **Nicht im Scope:** Trigger-Engine (Epic 15); provider-spezifische Normalisierung (Epics 11/16).
- **Abhängigkeiten:** E03-01.
- **Acceptance Criteria:** Zweites Event mit gleichem `dedupe_key` → als Duplikat markiert, keine erneute Verarbeitung; fehlende stabile ID → deterministischer Dedupe-Key aus dokumentierten Feldern.
- **Tests:** Integration: Duplikat-Erkennung; deterministischer Key; Reconnect-Replay erzeugt keine Zweitverarbeitung.
- **Security-Auswirkung:** Rohpayload nur referenziert/gehasht, nicht in Business-Rules.
- **HA-Auswirkung:** Beide Knoten können dasselbe externe Event sehen → Inbox garantiert Einmal-Verarbeitung.
- **Permissions:** — · **Audit Events:** —

### E04-08 · Singleton-Worker per etcd-Lease
**Epic:** 04 · **Phase:** 2-vorbereitend · **Area:** backend, infra · **Branch:** feature/<nr>-worker-singleton

- **Ziel:** Outbox-Dispatcher (und weitere Singletons) laufen clusterweit genau einmal, gewählt per kurzlebiger etcd-Lease.
- **Fachlicher Hintergrund:** ADR-0018: „Application leader-election … uses a separate `/bbz` prefix with short-lived leases + keepalive."
- **Scope:** Leader-Election-Bibliothek (`/bbz/leader/<name>`, TTL + Keepalive, sauberer Verzicht bei Verbindungsverlust); Outbox-Worker nutzt sie; lokaler Fallback (Single-Node-Dev) ohne etcd.
- **Nicht im Scope:** CUCM CONTROL_LEADER (E12-07 nutzt dieselbe Lib); Patroni.
- **Abhängigkeiten:** E04-06; etcd verfügbar (Dev-Compose hat es).
- **Acceptance Criteria:** Bei zwei laufenden App-Knoten dispatcht nur der Leader; Lease-Verlust → sofortiger Stopp, anderer Knoten übernimmt < 2×TTL; kein Doppel-Dispatch im Umschaltfenster (Outbox-`dedupe_key` schützt zusätzlich).
- **Tests:** Integration mit echtem etcd (Compose): Leader-Kill → Failover; kein Doppel-Dispatch.
- **Security-Auswirkung:** etcd-Zugriff per Rolle/TLS (ADR-0018).
- **HA-Auswirkung:** Genau der Punkt — verhindert doppelte Seiteneffekte bei Active/Active.
- **Permissions:** — · **Audit Events:** `WORKER_LEADER_CHANGED` (Audit).

### E04-09 · Correlation-ID-Propagation Command → Event → Audit → Outbox
**Epic:** 04 · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-correlation-propagation

- **Ziel:** Eine `correlation_id` zieht sich nachweisbar durch Request, Domain-Events, Audit und Outbox.
- **Fachlicher Hintergrund:** MASTER_PROMPT §3/§17; ADR-0012: „All responses echo `X-Correlation-Id`."
- **Scope:** Contextvar-basierte Propagation; Übernahme in `append_event`, `write_audit`, Outbox-Insert; Response-Header; Logging-Feld.
- **Nicht im Scope:** OpenTelemetry-Trace-Verknüpfung (Epic 22).
- **Abhängigkeiten:** E03-02, E04-02, E04-06.
- **Acceptance Criteria:** Ein einzelner Command produziert Domain-Event(s), Audit und Outbox-Zeilen mit identischer `correlation_id`; fehlender Header → Server generiert und echot.
- **Tests:** Integration: End-to-End-Korrelation über alle vier Senken.
- **Security-Auswirkung:** Forensik/Nachvollziehbarkeit.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E04-10 · ADR + Umsetzung: Audit-Unveränderlichkeit
**Epic:** 04 · **Phase:** 1 · **Area:** db, security · **Branch:** feature/<nr>-audit-immutability

- **Ziel:** Audit-Einträge sind technisch gegen Änderung/Löschung geschützt; der Mechanismus ist als ADR festgehalten.
- **Fachlicher Hintergrund:** MASTER_PROMPT §17/§26.7; `.ai/CURRENT_STATE.md` offener Punkt „audit immutability mechanism (append-only + DB grants / hash-chain / WORM)".
- **Scope:** ADR-0020 (Entscheidung: DB-Rolle mit nur INSERT auf `audit_events`/`domain_events` + optionale Hash-Kette `prev_hash`); Migration für Grants; optional Hash-Chain-Spalte + Verifikationsjob.
- **Nicht im Scope:** WORM-Storage-Hardware; externe Log-Weiterleitung (Epic 22).
- **Abhängigkeiten:** E01-01, E04-01, E03-02.
- **Acceptance Criteria:** Applikations-DB-Rolle kann `audit_events` nicht UPDATE/DELETE (Test weist es nach); falls Hash-Chain: Verifikationsjob erkennt eine manipulierte Zeile.
- **Tests:** Integration: UPDATE/DELETE als App-Rolle → Fehler; Hash-Chain-Bruch erkannt.
- **Security-Auswirkung:** Kern der Audit-Vertrauenswürdigkeit.
- **HA-Auswirkung:** Grants/Chain replizieren mit der DB.
- **Permissions:** — · **Audit Events:** —

### E04-11 · Replay-/Catch-up-Konsistenztests
**Epic:** 04 · **Phase:** 1 · **Area:** backend, test · **Branch:** feature/<nr>-replay-consistency-tests

- **Ziel:** Automatisierte Tests belegen, dass Catch-up per `event_seq` und Inbox/Outbox-Replay keine Duplikate/Verluste erzeugen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §24 (recovery/catch-up), ADR-0011.
- **Scope:** Test-Harness: Events erzeugen, „Verbindungsabriss" simulieren, ab `after_seq` nachladen; Inbox-Event doppelt zustellen; Outbox-Worker mitten im Dispatch killen.
- **Nicht im Scope:** Voller HA-Cluster (Epic 06).
- **Abhängigkeiten:** E03-13, E04-06, E04-07.
- **Acceptance Criteria:** Kein verlorenes/doppeltes Event im Catch-up; Inbox-Doppelzustellung → eine Verarbeitung; Outbox-Kill → am Ende genau eine erfolgreiche Zustellung.
- **Tests:** ebendiese als CI-Suite.
- **Security-Auswirkung:** — · **HA-Auswirkung:** verifiziert die exactly-once-Zusagen. · **Permissions:** — · **Audit Events:** —

---

# EPIC 05 · EPK Workflow Engine

**Milestone:** `05 EPK Workflow Engine` · **Phase:** 1 · **Ziel des Epics:**
Serverseitige, versionierte Graph-Workflow-Engine (EPK: Event-/Funktionsknoten,
AND/OR/XOR) mit sicherer Rule-DSL, unveränderlichen publizierten Versionen und
klarer Schritt-für-Schritt-Operatoransicht. Verantwortung bleibt am GESAMTEN
Ereignis. Quellen: MASTER_PROMPT §33, `.ai/WORKFLOW_EPK.md`, ADR-0005, ADR-0010.

### E05-01 · Rule-DSL: `evaluate()` implementieren + Property/Fuzz-Tests
**Epic:** 05 · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-rule-dsl-evaluate

- **Ziel:** `bbz_rule_dsl.evaluate()` wertet strukturierte Ausdrücke sicher und total aus (heute `NotImplementedError`).
- **Fachlicher Hintergrund:** ADR-0010: strukturierte Daten statt Strings, feste Operator-Allowlist, kein eval; „delivered with a property/fuzz test suite in Phase 1".
- **Scope:** Auswertung für `eq ne in not_in lt lte gt gte and or not exists`; deterministisch, seiteneffektfrei; klare Fehler bei Typmismatch/unbekanntem Operator.
- **Nicht im Scope:** Feld-Kontext-Registry (E05-02); Einbindung in Workflow/Trigger (E05-10, E15-05).
- **Abhängigkeiten:** Epic 01 (Parser/Allowlist vorhanden).
- **Acceptance Criteria:** Alle Operatoren korrekt; unbekannter Operator/Feld → Exception, nie „still true"; Property-Tests (Kommutativität wo erwartet, Nicht-Absturz bei Zufallsbäumen); ≥ 95 % Branch-Coverage.
- **Tests:** Unit je Operator; Hypothesis-Fuzz über Zufalls-AST; Grenzwerte.
- **Security-Auswirkung:** Entfernt jede RCE-Fläche; totale Funktion verhindert DoS durch Endlosauswertung.
- **HA-Auswirkung:** Deterministisch → gleiche Entscheidung auf beiden Knoten.
- **Permissions:** — · **Audit Events:** —

### E05-02 · Rule-DSL: typisierte Kontext-Registry (`ALLOWED_FIELDS`)
**Epic:** 05 · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-rule-dsl-context

- **Ziel:** Feldreferenzen lösen nur gegen eine allowlistete, typisierte Kontextdefinition auf.
- **Fachlicher Hintergrund:** ADR-0010: „Field references resolve only against an allowlisted, typed context; unknown fields raise."
- **Scope:** Registry mit Feldname → Typ + Resolver; getrennte Kontexte für Workflow-Bedingungen und Trigger-Bedingungen (`.ai/TECHNICAL_TRIGGERS.md`-Feldliste); Validierung eines Ausdrucks gegen einen Kontext.
- **Nicht im Scope:** Neue Felder je Fachbereich (kommen per ADR-Touch in den Feature-Epics).
- **Abhängigkeiten:** E05-01.
- **Acceptance Criteria:** Ausdruck mit unbekanntem Feld → Validierungsfehler beim Publish, nicht erst zur Laufzeit; Typmismatch (z. B. `lt` auf String) → Fehler.
- **Tests:** Unit: Validierung gültig/ungültig; Kontext-Trennung Workflow vs. Trigger.
- **Security-Auswirkung:** Kein Zugriff auf nicht freigegebene Daten in Bedingungen.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E05-03 · DB-Schema: workflow_templates + workflow_template_versions
**Epic:** 05 · **Phase:** 1 · **Area:** db · **Branch:** feature/<nr>-schema-workflow-templates

- **Ziel:** Migration für Template-Kopf und unveränderliche Versionen.
- **Fachlicher Hintergrund:** `.ai/WORKFLOW_EPK.md` Lifecycle DRAFT/VALIDATED/PUBLISHED/DEPRECATED; ADR-0005: publizierte Versionen unveränderlich.
- **Scope:** `workflow_templates` (id, key, name, owner, created); `workflow_template_versions` (id, template_id, version_no, lifecycle, definition jsonb, changelog, published_at, published_by, immutable flag).
- **Nicht im Scope:** Knoten/Kanten-Normalisierung (E05-04); Instanzen (E05-05).
- **Abhängigkeiten:** E02-01.
- **Acceptance Criteria:** Migration up/down/up; publizierte Version per DB-Trigger/Check gegen UPDATE der `definition` geschützt; `(template_id, version_no)` unique.
- **Tests:** Migration; „UPDATE publizierte definition" schlägt fehl.
- **Security-Auswirkung:** Unveränderlichkeit publizierter Prozesse.
- **HA-Auswirkung:** expand-only.
- **Permissions:** — · **Audit Events:** —

### E05-04 · DB-Schema + Graphmodell: nodes, edges, JSON-Schema
**Epic:** 05 · **Phase:** 1 · **Area:** db, backend · **Branch:** feature/<nr>-workflow-graph-model

- **Ziel:** Graph-Definition als versioniertes strukturiertes JSON plus normalisierte Indextabellen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §33: Ereignis-/Funktions-/Connector-Knoten (AND/OR/XOR Split/Join); `.ai/WORKFLOW_EPK.md` Task-Kinds.
- **Scope:** JSON-Schema für `definition` (Knoten: `event|function|connector`; function-`kind` ∈ manual/confirmation/documentation/integration_action/notification/timer/event_update; Connector-`type` ∈ and/or/xor + `split|join`); `workflow_graph_nodes`/`workflow_graph_edges` als abgeleitete Indizes.
- **Nicht im Scope:** Publish-Validierung (E05-06); Runtime (E05-07 ff.).
- **Abhängigkeiten:** E05-03.
- **Acceptance Criteria:** Schema akzeptiert die EPK-Beispiele aus `.ai/WORKFLOW_EPK.md`; abgeleitete Indextabellen werden beim Speichern konsistent befüllt.
- **Tests:** Schema-Validierung (positiv/negativ); Index-Ableitung deterministisch.
- **Security-Auswirkung:** Bedingungen sind DSL-JSON, kein Code.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E05-05 · DB-Schema: instances, tokens, task_results, decisions
**Epic:** 05 · **Phase:** 1 · **Area:** db · **Branch:** feature/<nr>-schema-workflow-runtime

- **Ziel:** Laufzeittabellen der Engine.
- **Fachlicher Hintergrund:** `.ai/WORKFLOW_EPK.md` „Suggested persistence"; Instanz an unveränderliche Version gepinnt.
- **Scope:** `workflow_instances` (id, event_id, template_version_id, status, started_at), `workflow_tokens` (instance_id, node_id, state, entered_at), `workflow_task_results` (instance_id, node_id, result jsonb, by, at), `workflow_decisions` (instance_id, connector_node_id, chosen_branches, by/auto, at).
- **Nicht im Scope:** Engine-Logik (E05-07..09).
- **Abhängigkeiten:** E05-03, E05-04, E03-01.
- **Acceptance Criteria:** Migration up/down/up; `template_version_id` FK auf eine PUBLISHED-Version; ein Ereignis kann mehrere Instanzen haben (dokumentierte Policy).
- **Tests:** Migration; FK-Constraints.
- **Security-Auswirkung:** — · **HA-Auswirkung:** expand-only. · **Permissions:** — · **Audit Events:** —

### E05-06 · Publish-Validierung
**Epic:** 05 · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-workflow-publish-validation

- **Ziel:** Nur ein struktur- und semantisch gültiger Graph kann publiziert werden.
- **Fachlicher Hintergrund:** `.ai/WORKFLOW_EPK.md` „Publish validation"-Checkliste.
- **Scope:** Validator: definiertes Startverhalten, erreichbare End-Pfade, keine Orphan-Knoten, korrekte Split/Join-Kardinalität, XOR auflösbar, OR trackbar, Pflichteigenschaften, Integration-Actions referenzieren existierende Capabilities/Config, keine unbounded Rekursion.
- **Nicht im Scope:** Simulation (E05-11); Editor-UI (Epic 07).
- **Abhängigkeiten:** E05-02, E05-04.
- **Acceptance Criteria:** Jeder Checklistenpunkt hat einen Positiv- und Negativtest; ungültiger Graph → strukturierte Fehlerliste, kein Publish; gültiger Graph → `lifecycle=VALIDATED` möglich.
- **Tests:** Unit: je Regel ein Negativfall; Golden-Graph besteht alle.
- **Security-Auswirkung:** Verhindert fehlerhafte Prozesse im Betrieb.
- **HA-Auswirkung:** — · **Permissions:** `workflows.manage_templates` · **Audit Events:** `WORKFLOW_TEMPLATE_VALIDATED`.

### E05-07 · Lifecycle & Immutability der Template-Versionen
**Epic:** 05 · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-workflow-lifecycle

- **Ziel:** DRAFT → VALIDATED → PUBLISHED → DEPRECATED mit erzwungener Unveränderlichkeit ab PUBLISHED.
- **Fachlicher Hintergrund:** ADR-0005: „Published versions are immutable; each running instance is pinned to its template version."
- **Scope:** Zustandsübergänge + API (`.../versions/{id}/validate|publish|deprecate`), Changelog Pflicht beim Publish, neue Änderung = neue DRAFT-Version.
- **Nicht im Scope:** Migration laufender Instanzen (bewusst später, separat auditiert).
- **Abhängigkeiten:** E05-03, E05-06.
- **Acceptance Criteria:** Publish ohne vorherige Validierung → abgelehnt; Änderung an PUBLISHED → 409 + Hinweis „neue Version anlegen"; DEPRECATED bleibt für laufende Instanzen nutzbar.
- **Tests:** API: alle Übergänge, verbotene Änderungen, Changelog-Pflicht.
- **Security-Auswirkung:** `workflows.manage_templates`; jede Änderung auditiert.
- **HA-Auswirkung:** Idempotent.
- **Permissions:** `workflows.view` `workflows.manage_templates` · **Audit Events:** `WORKFLOW_TEMPLATE_PUBLISHED` `WORKFLOW_TEMPLATE_DEPRECATED`.

### E05-08 · Engine: AND-Split/Join + Token-Semantik
**Epic:** 05 · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-workflow-engine-and

- **Ziel:** Die Kern-Token-Engine aktiviert/vervollständigt parallele Zweige korrekt.
- **Fachlicher Hintergrund:** `.ai/WORKFLOW_EPK.md`: AND = alle Zweige aktivieren / alle erforderlichen vor Join abschließen.
- **Scope:** Token-Modell, Node-Aktivierung, AND-Split erzeugt Token je Zweig, AND-Join wartet auf alle; deterministische Verarbeitung; Persistenz in `workflow_tokens`.
- **Nicht im Scope:** XOR/OR (E05-09); Task-Ausführung (E05-10).
- **Abhängigkeiten:** E05-05.
- **Acceptance Criteria:** AND-Join feuert genau dann, wenn alle Eingangs-Token da sind; Wiederanlauf der Engine (Crash) führt Instanz konsistent fort (idempotente Schrittverarbeitung).
- **Tests:** Unit/Integration: Diamant-Graph; Crash-Recovery mittendrin.
- **Security-Auswirkung:** — · **HA-Auswirkung:** Schrittverarbeitung idempotent, damit Failover sie fortsetzt. · **Permissions:** — · **Audit Events:** `ACTION_STEP_COMPLETED`.

### E05-09 · Engine: XOR- und OR-Split/Join
**Epic:** 05 · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-workflow-engine-xor-or

- **Ziel:** XOR (genau ein Zweig, auto per DSL oder Operatorentscheidung) und OR (ein/mehrere Zweige, Join wartet auf die aktivierte Menge).
- **Fachlicher Hintergrund:** `.ai/WORKFLOW_EPK.md` Connector-Semantik.
- **Scope:** XOR-Auswahl via Rule-DSL (E05-01/02) oder `workflow_decisions`-Eintrag durch Operator; OR-Aktivierungsmenge tracken; Joins entsprechend.
- **Nicht im Scope:** Operator-UI der Entscheidung (Epic 07).
- **Abhängigkeiten:** E05-08, E05-02.
- **Acceptance Criteria:** XOR wählt deterministisch genau einen Zweig; fehlende auflösbare Bedingung ohne Operatorentscheidung → Instanz wartet, kein Fehlpfad; OR-Join wartet exakt auf die aktivierte Zweigmenge dieser Instanz.
- **Tests:** §35-Fälle: „XOR Pfad korrekt", „OR Mehrfachpfad korrekt".
- **Security-Auswirkung:** — · **HA-Auswirkung:** deterministisch/idempotent. · **Permissions:** `workflows.execute` (Operatorentscheidung) · **Audit Events:** `WORKFLOW_DECISION_MADE`.

### E05-10 · Task-Kinds-Laufzeit (manual/confirmation/documentation/timer + integration/notification/event_update)
**Epic:** 05 · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-workflow-task-kinds

- **Ziel:** Alle Funktions-Knoten-Typen sind ausführbar; externe Wirkung läuft über die Outbox.
- **Fachlicher Hintergrund:** `.ai/WORKFLOW_EPK.md` Task-Kinds; ADR-0011 Outbox für Seiteneffekte.
- **Scope:** Handler je Kind: manual/confirmation/documentation (Operator-Eingabe), timer/wait (geplante Reaktivierung), integration_action/notification/event_update (über `external_action_outbox`, idempotent).
- **Nicht im Scope:** Konkrete Integrationsziele (deren Epics registrieren Outbox-Handler).
- **Abhängigkeiten:** E05-08, E04-06.
- **Acceptance Criteria:** integration/notification-Tasks erzeugen genau eine Outbox-Zeile mit stabilem dedupe_key (`instance_id + node_id + attempt-0`); timer feuert nach konfigurierter Zeit auch nach Serverneustart; documentation-Task blockt Fortschritt bis Eingabe.
- **Tests:** Integration je Kind; Outbox-Idempotenz; Timer über simulierten Neustart.
- **Security-Auswirkung:** Keine willkürlichen Skripte; nur typisierte Actions (MASTER_PROMPT §33/§29).
- **HA-Auswirkung:** Seiteneffekte exactly-once über Outbox + Singleton.
- **Permissions:** `workflows.execute` · **Audit Events:** `ACTION_STEP_COMPLETED`, ggf. `EXTERNAL_ACTION_DISPATCHED`.

### E05-11 · Instanz-Pinning & Start aus einem Ereignis
**Epic:** 05 · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-workflow-instance-start

- **Ziel:** Eine Workflow-Instanz wird an ein Ereignis und eine unveränderliche PUBLISHED-Version gebunden.
- **Fachlicher Hintergrund:** ADR-0005: „Publishing v4 must not silently change instances running on v3."
- **Scope:** `POST /events/{id}/workflow` (template_key) → Instanz auf aktueller PUBLISHED-Version; Bindung unveränderlich; spätere Template-Publishes ändern laufende Instanz nicht.
- **Nicht im Scope:** Auto-Start via Trigger (Epic 15 ruft diesen Pfad).
- **Abhängigkeiten:** E05-05, E05-07, E03-06.
- **Acceptance Criteria:** §35-Fall „neue Template-Version verändert laufende Instanz nicht" ist grün; Start ohne PUBLISHED-Version → Fehler.
- **Tests:** Integration: Instanz starten, Template v+1 publizieren, Instanz läuft unverändert weiter.
- **Security-Auswirkung:** `workflows.execute`.
- **HA-Auswirkung:** Idempotent.
- **Permissions:** `workflows.execute` · **Audit Events:** `WORKFLOW_INSTANCE_STARTED`.

### E05-12 · Instanz-API: aktuelle Schritte, Schritt abschließen, Entscheidung treffen
**Epic:** 05 · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-workflow-instance-api

- **Ziel:** Der Operator kann den Graphen abarbeiten: sehen, was dran ist, Schritte abschließen, Entscheidungen treffen.
- **Fachlicher Hintergrund:** `.ai/WORKFLOW_EPK.md` „Operator behavior".
- **Scope:** `GET /events/{id}/workflow` (aktive/erledigte/wartende Schritte, nötige Entscheidungen, Fortschritt, Zeitstempel, Audit-Referenzen), `POST .../steps/{node}/complete`, `POST .../decisions/{connector}`.
- **Nicht im Scope:** UI-Rendering (Epic 07); Verantwortungslogik (bleibt am Ereignis, Epic 03).
- **Abhängigkeiten:** E05-08/09/10.
- **Acceptance Criteria:** Ansicht spiegelt Token-Zustand exakt; Schritt-Abschluss ohne Berechtigung/außer der Reihe → Fehler; Verantwortung wird NICHT pro Schritt verteilt (kein Assignee-Feld an Schritten).
- **Tests:** API: Abarbeitung eines AND-, XOR-, OR-Graphen; Rechteprüfung; Idempotenz.
- **Security-Auswirkung:** `workflows.execute`; `workflows.override` für Sonderpfade.
- **HA-Auswirkung:** Idempotente Schrittabschlüsse.
- **Permissions:** `workflows.view` `workflows.execute` `workflows.override` · **Audit Events:** `ACTION_STEP_COMPLETED` `WORKFLOW_DECISION_MADE`.

### E05-13 · Template-Admin-API: CRUD Draft, Changelog, Simulation
**Epic:** 05 · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-workflow-template-admin

- **Ziel:** Admins verwalten Templates per API inkl. Testlauf ohne echte Seiteneffekte.
- **Fachlicher Hintergrund:** MASTER_PROMPT §33.3: Editor mit Graphvalidierung, Simulation/Testlauf, Publish mit Version/Changelog.
- **Scope:** CRUD DRAFT-Templates/Versionen; `POST .../simulate` (führt Graph mit Testeingaben aus, Outbox im „dry-run"-Modus, keine realen Actions); Diff/Changelog-Erzeugung.
- **Nicht im Scope:** Grafischer Editor (Epic 07); Rule-DSL-Editor-UI.
- **Abhängigkeiten:** E05-06, E05-10.
- **Acceptance Criteria:** Simulation erzeugt keine realen Outbox-Zustellungen; Simulationsreport zeigt begangene Pfade/Entscheidungen; Publish erfordert Changelog.
- **Tests:** API: Simulation eines Alarm-Workflows ohne reale Kameraaktion; CRUD; Rechteprüfung.
- **Security-Auswirkung:** `workflows.manage_templates`; Dry-Run verhindert versehentliche echte Aktionen.
- **HA-Auswirkung:** Simulation zustandslos/isoliert.
- **Permissions:** `workflows.manage_templates` · **Audit Events:** `WORKFLOW_TEMPLATE_CREATED` `WORKFLOW_TEMPLATE_UPDATED` `WORKFLOW_SIMULATED`.

---

# EPIC 06 · HA Cluster

**Milestone:** `06 HA Cluster` · **Phase:** 2 · **Ziel des Epics:** Zwei aktive
App-Knoten, Patroni-gesteuerter PostgreSQL-Failover, 3-Member-etcd inkl. Witness,
ehrlicher `/cluster/status`, Client-Catch-up und getestete Failover-Szenarien.
Quellen: MASTER_PROMPT §2/§4/§5/§20/§21/§24, ADR-0001, ADR-0018,
`docs/runbooks/*`.

### E06-01 · deploy/: Per-Node-Compose (api, web, postgres, patroni, etcd, proxy)
**Epic:** 06 · **Phase:** 2 · **Area:** infra · **Branch:** feature/<nr>-deploy-node-compose

- **Ziel:** Ein reproduzierbares Compose/Manifest je BBZ-Server bringt den vollständigen Node-Stack hoch.
- **Fachlicher Hintergrund:** MASTER_PROMPT §20: je Server bbz-api/web/postgres/patroni/etcd/reverse-proxy; Quorum nur etcd.
- **Scope:** `deploy/node/` Compose mit allen Diensten, Umgebungs-/Secret-Templates, Volumes; `deploy/quorum/` nur etcd; klare Trennung zur Dev-`docker-compose.yml`.
- **Nicht im Scope:** Patroni-Tuning (E06-02); etcd-Cluster-Bootstrap (E06-03); Deployment-Automatik (Epic 24).
- **Abhängigkeiten:** Epic 01 (Images bauen), E01-04.
- **Acceptance Criteria:** `deploy/node` startet lokal als Ein-Knoten-Simulation; `deploy/quorum` enthält keine BBZ-Fachdienste; `docker compose config` in CI grün.
- **Tests:** CI `docker compose config` für alle Deploy-Profile; Smoke: Node-Stack hoch, `/health/ready` grün.
- **Security-Auswirkung:** Secrets als Files/Env injiziert (ADR-0015); keine Klartext-Creds im Compose.
- **HA-Auswirkung:** Grundlage der 2+1-Topologie.
- **Permissions:** — · **Audit Events:** —

### E06-02 · Patroni + PostgreSQL Primary/Standby + Sync-Modus-ADR
**Epic:** 06 · **Phase:** 2 · **Area:** infra, db · **Branch:** feature/<nr>-patroni-replication

- **Ziel:** Patroni verwaltet einen PostgreSQL-Primary mit Standby; Failover ist automatisch.
- **Fachlicher Hintergrund:** ADR-0001; `.ai/CURRENT_STATE.md` offene Frage „synchronous vs asynchronous replication".
- **Scope:** Patroni-Config (`/patroni`-Prefix in etcd), Replikation, Failover-Regeln; ADR-0021 „Replikationsmodus" (Entscheidung sync/async + Begründung Leitstelle); `docs/runbooks/db-failover.md` verifizieren.
- **Nicht im Scope:** Backup (E06-14); App-Reaktion auf Failover (E06-07).
- **Abhängigkeiten:** E06-01, E06-03, E01-01.
- **Acceptance Criteria:** Primary-Ausfall → automatischer Failover < definierter RTO; `event_seq` setzt auf neuem Primary lückentolerant fort; ADR-0021 `Accepted`.
- **Tests:** HA-Harness: Primary kill → Standby wird Primary, App bleibt schreibbar nach Reconnect.
- **Security-Auswirkung:** Replikations-/Superuser-Creds getrennt, per Secret.
- **HA-Auswirkung:** Kern des kontrollierten DB-Failovers (kein Multi-Master).
- **Permissions:** `system.cluster.view` · **Audit Events:** `DB_FAILOVER` (Audit, vom Cluster-Beobachter).

### E06-03 · etcd 3-Member-Cluster mit TLS (SRV01, SRV02, QUORUM01)
**Epic:** 06 · **Phase:** 2 · **Area:** infra · **Branch:** feature/<nr>-etcd-cluster

- **Ziel:** Ein produktiver 3-Member-etcd-Cluster mit TLS als einziger DCS.
- **Fachlicher Hintergrund:** ADR-0018: etcd v3.5.x, ein Member je Server + Witness, TLS, rollenskopierter Zugriff.
- **Scope:** etcd-Bootstrap (Peer/Client-TLS, Zertifikate), Member je Deploy-Ziel, Health/Backup-Hooks, `/patroni` + `/bbz` Prefix-Trennung + ACL.
- **Nicht im Scope:** App-Leader-Election-Lib (E04-08); Patroni-Anbindung (E06-02).
- **Abhängigkeiten:** E06-01.
- **Acceptance Criteria:** Cluster übersteht Ausfall eines Members (Quorum 2/3); TLS erzwungen; getrennte ACLs für Patroni- vs. App-Keys.
- **Tests:** HA-Harness: ein Member down → Cluster weiter beschlussfähig; Witness down → weiter beschlussfähig.
- **Security-Auswirkung:** mTLS zwischen Membern/Clients; kein anonymer Zugriff.
- **HA-Auswirkung:** Consensus-Basis für DB- und App-Failover.
- **Permissions:** `system.cluster.view` · **Audit Events:** —

### E06-04 · `/cluster/status` echte Implementierung
**Epic:** 06 · **Phase:** 2 · **Area:** backend, infra · **Branch:** feature/<nr>-cluster-status-real

- **Ziel:** `/cluster/status` liefert echte DCS-Health, Quorum, CONTROL_LEADER, Knotenrollen und Replication-Lag (heute ehrlicher Stub).
- **Fachlicher Hintergrund:** MASTER_PROMPT §4/§23; `.ai/CURRENT_STATE.md`: Stub ist bewusst gelabelt.
- **Scope:** Abfrage etcd + Patroni-REST + lokale DB-Rolle; Felder aus dem heutigen Stub mit echten Werten füllen; `stub:false`.
- **Nicht im Scope:** Metriken-Endpoint (E06-13); UI (Epic 07/22).
- **Abhängigkeiten:** E06-02, E06-03.
- **Acceptance Criteria:** Werte stimmen mit tatsächlichem Cluster-Zustand überein; bei DCS-Verlust ehrliche Degradation (`dcs_healthy:false`), kein 500.
- **Tests:** Integration gegen echtes etcd/Patroni (Compose); Degradations-Fall.
- **Security-Auswirkung:** `system.cluster.view` zum Lesen; keine internen Endpunkte/Secrets im Body.
- **HA-Auswirkung:** Beobachtbarkeit des HA-Zustands; Client nutzt es für Serverwahl.
- **Permissions:** `system.cluster.view` · **Audit Events:** —

### E06-05 · `/health/ready`-Gate an Cluster-/Datenstand koppeln
**Epic:** 06 · **Phase:** 2 · **Area:** backend · **Branch:** feature/<nr>-ready-gate-cluster

- **Ziel:** Ein Knoten meldet nur `ready`, wenn DB erreichbar UND Clusterstatus gültig ist.
- **Fachlicher Hintergrund:** MASTER_PROMPT §4: „App-Knoten wird erst `ready`, wenn Datenstand/Clusterstatus gültig ist."
- **Scope:** Readiness-Check erweitern: DB-Probe (vorhanden) + Patroni-Rolle bekannt + kein „starting/rejoin"-Zustand; Reihenfolge/Timeouts dokumentiert.
- **Nicht im Scope:** Client-Reaktion (E09-04).
- **Abhängigkeiten:** E06-04.
- **Acceptance Criteria:** Knoten im Rejoin/Replay meldet `not ready`; Reverse-Proxy nimmt ihn dann aus der Rotation.
- **Tests:** Integration: Knoten während Standby-Aufholphase → `503 not ready`.
- **Security-Auswirkung:** Keine.
- **HA-Auswirkung:** Verhindert Traffic auf inkonsistente Knoten.
- **Permissions:** — · **Audit Events:** —

### E06-06 · App-Leader-Election-Nutzung dokumentieren & zweiten Consumer anbinden
**Epic:** 06 · **Phase:** 2 · **Area:** backend · **Branch:** feature/<nr>-leader-election-consumers

- **Ziel:** Die Leader-Election-Lib (E04-08) ist als geteilte Infrastruktur nutzbar; Outbox-Dispatcher + Timer-Scheduler laufen als Singleton.
- **Fachlicher Hintergrund:** ADR-0018; ADR-0011 Dispatcher-Singleton.
- **Scope:** Registrierung benannter Singletons (`outbox-dispatcher`, `workflow-timer`, künftig `cucm-control-leader`), Health-Anzeige welcher Knoten welchen Leader hält; Doku in `docs/ARCHITECTURE_OVERVIEW.md`.
- **Nicht im Scope:** CUCM-Leader-Logik (E12-07).
- **Abhängigkeiten:** E04-08, E05-10.
- **Acceptance Criteria:** `/cluster/status` (oder Metrik) zeigt Leader je Singleton; Failover eines Leaders < 2×TTL; keine zwei aktiven Instanzen.
- **Tests:** Integration: Kill des Leader-Knotens → anderer übernimmt alle Singletons.
- **Security-Auswirkung:** etcd-ACL.
- **HA-Auswirkung:** Verhindert doppelte Hintergrundarbeit.
- **Permissions:** `system.cluster.view` · **Audit Events:** `WORKER_LEADER_CHANGED`.

### E06-07 · Client-Catch-up-Protokoll (last event_seq Handoff, Replay bei Failover)
**Epic:** 06 · **Phase:** 2 · **Area:** backend · **Branch:** feature/<nr>-client-catchup-protocol

- **Ziel:** Ein Client, der von SRV01 auf SRV02 wechselt, sendet seinen letzten `event_seq` und erhält lückenlos die verpassten Events.
- **Fachlicher Hintergrund:** MASTER_PROMPT §4: „Letzten bekannten `event_seq` mitsenden. Verpasste Events nachladen."
- **Scope:** Stream-Endpoints (E03-13/14) so absichern, dass `after_seq` auch über Knotengrenzen konsistent ist; Doku des Client-Handshakes; Toleranz gegen kurze `event_seq`-Lücken nach Failover.
- **Nicht im Scope:** Agent-Implementierung (Epic 09); Offline-Outbox (Epic 09).
- **Abhängigkeiten:** E03-13, E06-04.
- **Acceptance Criteria:** Reconnect gegen den anderen Knoten mit `after_seq` → identische, lückenlose Fortsetzung; Lücke durch Failover wird korrekt übersprungen ohne „fehlt"-Fehlalarm.
- **Tests:** HA-Harness: Stream offen, SRV01 kill, Reconnect SRV02, keine Events verloren/doppelt.
- **Security-Auswirkung:** Authz pro Reconnect neu.
- **HA-Auswirkung:** Der Kern der nahtlosen Client-Übernahme.
- **Permissions:** `events.view` · **Audit Events:** —

### E06-08 · Quorum-Node-Deployment (nur etcd)
**Epic:** 06 · **Phase:** 2 · **Area:** infra · **Branch:** feature/<nr>-quorum-node

- **Ziel:** `BBZ-QUORUM01` läuft ausschließlich als etcd-Member (+ optionales Monitoring), keine BBZ-Domänendienste.
- **Fachlicher Hintergrund:** MASTER_PROMPT §20/§2: „Keine Fachlogik im Quorum."
- **Scope:** `deploy/quorum/` finalisieren; Härtungs-Checkliste; expliziter Test/Assertion „keine bbz-api/web/postgres hier".
- **Nicht im Scope:** Monitoring-Stack (Epic 22).
- **Abhängigkeiten:** E06-03.
- **Acceptance Criteria:** Deploy-Definition enthält nur etcd(+Exporter); Doku/Runbook vorhanden.
- **Tests:** CI-Assertion über die Service-Liste des Quorum-Profils.
- **Security-Auswirkung:** Minimale Angriffsfläche auf dem Witness.
- **HA-Auswirkung:** Drittes Voting-Mitglied ohne Datenrisiko.
- **Permissions:** — · **Audit Events:** —

### E06-09 · Rolling-Update-Mechanismus (SRV02 → Health → SRV01)
**Epic:** 06 · **Phase:** 2 · **Area:** infra · **Branch:** feature/<nr>-rolling-update

- **Ziel:** Ein Skript/Runbook aktualisiert die Knoten nacheinander mit Health-Gates.
- **Fachlicher Hintergrund:** MASTER_PROMPT §21: Cluster gesund prüfen → Migration prüfen → SRV02 → Health → SRV01 → Cluster prüfen.
- **Scope:** `tools/rolling-update.*` mit Pre-Flight (Cluster grün, Migration rückwärtskompatibel), Node-Drain über Reverse-Proxy, Reihenfolge, Rollback-Abbruch; `docs/runbooks/rolling-update.md` verifizieren.
- **Nicht im Scope:** CI/CD-Trigger (Epic 24).
- **Abhängigkeiten:** E06-01, E06-05, E06-10.
- **Acceptance Criteria:** Update ohne Clientausfall in der Ein-Knoten→Zwei-Knoten-Simulation; Abbruch bei rotem Health lässt SRV01 unangetastet.
- **Tests:** HA-Harness: Update-Lauf mit laufenden Stream-Clients, keine 5xx.
- **Security-Auswirkung:** Nur signierte Image-Digests (E01-04).
- **HA-Auswirkung:** Wartung ohne Downtime.
- **Permissions:** `system.cluster.manage` · **Audit Events:** `ROLLING_UPDATE_STARTED/COMPLETED` (Audit).

### E06-10 · DB-Migrationsstrategie expand/migrate/contract + CI-Check
**Epic:** 06 · **Phase:** 2 · **Area:** db, infra · **Branch:** feature/<nr>-migration-strategy

- **Ziel:** Jede Migration ist während eines Rolling Updates mindestens eine Version rückwärtskompatibel; CI erzwingt das Muster.
- **Fachlicher Hintergrund:** MASTER_PROMPT §21; ADR-0011.
- **Scope:** Konvention (expand → deploy → migrate-data → deploy → contract); Migrations-Review-Checkliste; CI-Job, der die neueste Migration gegen die vorherige App-Version testet (alte App + neues Schema).
- **Nicht im Scope:** Konkrete Feature-Migrationen.
- **Abhängigkeiten:** E01-01.
- **Acceptance Criteria:** CI schlägt fehl, wenn eine Migration die vorherige App-Version bricht; `docs/CONVENTIONS.md` beschreibt das Muster.
- **Tests:** CI-Kompatibilitätsmatrix (N-1 App × N Schema).
- **Security-Auswirkung:** Keine.
- **HA-Auswirkung:** Zero-Downtime-Migrationen.
- **Permissions:** — · **Audit Events:** —

### E06-11 · HA-Failure-Szenario-Testharness
**Epic:** 06 · **Phase:** 2 · **Area:** test, infra · **Branch:** feature/<nr>-ha-test-harness

- **Ziel:** Wiederholbare Tests für SRV01-down, SRV02-down, DB-Primary-Loss, Netz-Isolation, Witness-down, Recovery, Client-Reconnect.
- **Fachlicher Hintergrund:** MASTER_PROMPT §24 „HA Simulation"; `.ai/TESTING.md`.
- **Scope:** Docker-basiertes Harness (Netzwerk-Partition per `iptables`/`pumba`), Szenario-Skripte, Assertions (kein Datenverlust, Failover-RTO, Split-Brain ausgeschlossen).
- **Nicht im Scope:** Chaos-Dauerbetrieb; Prod-Monitoring.
- **Abhängigkeiten:** E06-02..07.
- **Acceptance Criteria:** Alle sieben Szenarien laufen als benannte CI-(nightly)-Jobs grün; Split-Brain-Assertion (zwei Primarys unmöglich).
- **Tests:** ebendiese Szenarien.
- **Security-Auswirkung:** Keine.
- **HA-Auswirkung:** Nachweis der HA-Zusagen.
- **Permissions:** — · **Audit Events:** —

### E06-12 · Reverse Proxy (Caddy): TLS, Routing, Security-Header
**Epic:** 06 · **Phase:** 2 · **Area:** infra, security · **Branch:** feature/<nr>-reverse-proxy

- **Ziel:** Produktiver Reverse-Proxy terminiert TLS, routet api/web und setzt Security-Header; nimmt `not ready`-Knoten aus der Rotation.
- **Fachlicher Hintergrund:** MASTER_PROMPT §20/§22; vorhandene `deploy/reverse-proxy/Caddyfile`.
- **Scope:** Caddyfile finalisieren: TLS (interne PKI), Upstream-Healthchecks gegen `/health/ready`, HSTS/CSP/X-Content-Type-Options/Frame-Options, WebSocket-Passthrough.
- **Nicht im Scope:** CSP-Feinschliff Web/Electron (Epic 23).
- **Abhängigkeiten:** E06-05.
- **Acceptance Criteria:** `not ready`-Upstream erhält keinen Traffic; Security-Header per Test vorhanden; WS-Streams funktionieren durch den Proxy.
- **Tests:** Integration: Header-Assertions; Failover-Routing; WS durch Proxy.
- **Security-Auswirkung:** TLS-Terminierung, Header-Baseline.
- **HA-Auswirkung:** Lastverteilung + Health-basiertes Draining.
- **Permissions:** — · **Audit Events:** —

### E06-13 · Cluster-/HA-Metriken-Endpoint
**Epic:** 06 · **Phase:** 2 · **Area:** backend, infra · **Branch:** feature/<nr>-ha-metrics

- **Ziel:** Prometheus-Metriken für Replication-Lag, aktiver Server, verbundene Clients, WS-Verbindungen, pending Offline-Commands.
- **Fachlicher Hintergrund:** MASTER_PROMPT §23 Metrik-Liste.
- **Scope:** `/metrics` (oder getrennter Port) mit den HA-relevanten Gauges/Counters; Doku welche Metrik was bedeutet.
- **Nicht im Scope:** Vollständige Observability (Epic 22 baut darauf auf).
- **Abhängigkeiten:** E06-04.
- **Acceptance Criteria:** Metriken vorhanden und korrekt bei simuliertem Lag/Failover; Endpoint nicht öffentlich (Netzscope/Basic-Auth).
- **Tests:** Integration: Metrikwerte unter Failover-Szenario.
- **Security-Auswirkung:** Endpoint zugriffsbeschränkt.
- **HA-Auswirkung:** Frühwarnung (Lag, Quorumverlust).
- **Permissions:** `system.cluster.view` · **Audit Events:** —

### E06-14 · Backup/Restore für PostgreSQL + etcd
**Epic:** 06 · **Phase:** 2 · **Area:** infra · **Branch:** feature/<nr>-backup-restore

- **Ziel:** Automatisierte, getestete Backups beider Zustandsspeicher mit dokumentiertem Restore.
- **Fachlicher Hintergrund:** MASTER_PROMPT §20/§24 (recovery); Betriebssicherheit einer Leitstelle.
- **Scope:** pgBackRest/WAL-Archivierung + etcd-Snapshots, Zeitplan, Aufbewahrung, verschlüsselte Ablage; `docs/runbooks/rollback.md` + neues Restore-Runbook mit echtem Restore-Test.
- **Nicht im Scope:** Offsite/DR-Standort (Epic 24).
- **Abhängigkeiten:** E06-02, E06-03.
- **Acceptance Criteria:** Restore aus Backup in Testumgebung erfolgreich; RPO dokumentiert; Backups verschlüsselt.
- **Tests:** Geplanter Restore-Test-Job (nightly/weekly) mit Integritätsprüfung.
- **Security-Auswirkung:** Backups verschlüsselt, Zugriff beschränkt (enthalten Fachdaten + Audit).
- **HA-Auswirkung:** Wiederherstellbarkeit nach Totalverlust.
- **Permissions:** `system.cluster.manage` · **Audit Events:** `BACKUP_COMPLETED` `RESTORE_PERFORMED` (Audit).

---

# EPIC 07 · Web UI / PrimeVue

**Milestone:** `07 Web UI / PrimeVue` · **Phase:** 3 · **Ziel des Epics:** Das
verbindliche Mockup in eine echte Vue-3/PrimeVue-Struktur überführen — ohne
UX-/Funktionsverlust, barrierefrei, mit den Pflicht-E2E-Tests. Quellen:
MASTER_PROMPT §13/§24, ADR-0013, `docs/mockup/` (E01-02).

### E07-01 · Mockup-Parity-Checkliste & Tracking
**Epic:** 07 · **Phase:** 3 · **Area:** frontend, documentation · **Branch:** docs/<nr>-parity-checklist

- **Ziel:** Jede Funktion aus `.ai/FEATURES.md`/§13 ist als überprüfbarer Parity-Punkt erfasst und wird pro UI-Issue abgehakt.
- **Fachlicher Hintergrund:** ADR-0013: „Mockup parity … tracked explicitly (checklist in `docs/`), not assumed."
- **Scope:** `docs/mockup-parity-checklist.md` vervollständigen (aus E01-02-Gerüst), je Punkt: Mockup-Referenz + Ziel-Route/Komponente + Status.
- **Nicht im Scope:** Implementierung.
- **Abhängigkeiten:** E01-02.
- **Acceptance Criteria:** Alle §13/`FEATURES.md`-Punkte gelistet; jeder verweist auf das Issue, das ihn umsetzt.
- **Tests:** Doc-Link-Check.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E07-02 · Auth-UI: Login, Provider-Wahl, Session, Logout, TOTP-Prompt
**Epic:** 07 · **Phase:** 3 · **Area:** frontend · **Branch:** feature/<nr>-ui-auth

- **Ziel:** Anmeldefluss inkl. optionalem zweiten Faktor; Session-Handling im SPA.
- **Fachlicher Hintergrund:** MASTER_PROMPT §11; ADR-0013.
- **Scope:** Login-Seite, Provider-Auswahl (nur `local` aktiv), TOTP-Challenge-Schritt, Force-Password-Change, Logout, Session-Ablauf-Handling (Redirect + Wiederaufnahme).
- **Nicht im Scope:** OIDC-Redirect-Flow (Epic 21); „Passwort vergessen" per Mail.
- **Abhängigkeiten:** E02-05, E02-13.
- **Acceptance Criteria:** Abgelaufene Session → Re-Login ohne Datenverlust im offenen Formular wo möglich; TOTP-Pflicht korrekt erzwungen; a11y-Lint grün.
- **Tests:** Vitest-Komponenten; Playwright: Login→Logout, TOTP-Pfad.
- **Security-Auswirkung:** Kein Token im `localStorage` (HttpOnly-Cookie bevorzugt); CSRF-Header.
- **HA-Auswirkung:** Session übersteht Server-Failover (E02-05).
- **Permissions:** — · **Audit Events:** — (Server auditiert).

### E07-03 · App-Shell finalisieren (Topbar-Uhr, Leitungen, Sidebar-Resize)
**Epic:** 07 · **Phase:** 3 · **Area:** frontend, a11y · **Branch:** feature/<nr>-ui-appshell

- **Ziel:** Die vorhandene Shell erfüllt §13.1/§13.2 vollständig.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.1: gemeinsame Topbar, große Uhr mit Sekunden, verfügbare Leitungen, Monitor-Layout-Button; persistierte, tastatur- und mausbedienbare Sidebarbreite.
- **Scope:** Topbar (Uhr/Sekunden, Leitungsstatus-Platzhalter, Monitor-Button), linke Sidebar (Branding, Arbeitsplatz aktiv, Systeme betriebsbereit, Navigation, User/Rolle), rechte Komm-Sidebar resizebar (Maus + Tastatur, `localStorage`), reduced-motion-Contract global.
- **Nicht im Scope:** Leitungsdaten echt (Epic 11); Monitor-Dialog (Epic 19).
- **Abhängigkeiten:** E02-05.
- **Acceptance Criteria:** Sidebarbreite via Tastatur änderbar und persistent; Uhr driftet nicht; a11y-Lint + axe grün.
- **Tests:** Vitest (vorhandene Shell-Tests erweitern); Playwright: Resize per Tastatur.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E07-04 · Generischer API-Client (Command-Envelope, 409, Correlation-ID)
**Epic:** 07 · **Phase:** 3 · **Area:** frontend · **Branch:** feature/<nr>-ui-api-client

- **Ziel:** Ein Client kapselt Command-Envelope, Idempotenz-Retry, 409-Behandlung und den Fehler-Envelope.
- **Fachlicher Hintergrund:** ADR-0012.
- **Scope:** `src/api/` ausbauen: `X-Command-Id`-Generierung, `X-Expected-Version`, `X-Client-Id`/`X-Workplace-Id`, `X-Correlation-Id`; 409 → aktuellen Stand übernehmen + Nutzerhinweis; einheitliche Fehleranzeige.
- **Nicht im Scope:** Offline-Queue (Epic 09).
- **Abhängigkeiten:** E03-03, E03-08.
- **Acceptance Criteria:** Doppel-Klick erzeugt keinen Doppeleffekt (gleiche Command-Id bei Retry); 409 führt zu klarer „Daten wurden geändert"-UX, kein stiller Overwrite.
- **Tests:** Vitest: Envelope-Header, 409-Handling, Retry-Idempotenz.
- **Security-Auswirkung:** CSRF-Header; keine sensiblen Daten im Log.
- **HA-Auswirkung:** Retry über Failover mit stabiler Command-Id.
- **Permissions:** — · **Audit Events:** —

### E07-05 · Event-Stream-Client + Sync-Statusanzeige
**Epic:** 07 · **Phase:** 3 · **Area:** frontend · **Branch:** feature/<nr>-ui-event-stream

- **Ziel:** Das SPA abonniert den Event-Stream, macht Catch-up ab `after_seq` und zeigt `UNSYNCED/SYNCING/SYNCED/CONFLICT`.
- **Fachlicher Hintergrund:** MASTER_PROMPT §5/§16.
- **Scope:** SSE/WS-Client, `after_seq`-Persistenz, Reconnect/Backoff, Pinia-Store für Live-Ereignisse, sichtbarer Sync-Status.
- **Nicht im Scope:** Offline-Cache (Epic 09).
- **Abhängigkeiten:** E03-13/14.
- **Acceptance Criteria:** Nach Netzabriss + Reconnect sind keine Ereignisse „verschwunden"; Status wechselt korrekt; UI blockiert kritische Schreibaktionen im Zustand `CONFLICT` bis Auflösung.
- **Tests:** Vitest (Store); Playwright: Netz aus/an, Liste konsistent.
- **Security-Auswirkung:** — · **HA-Auswirkung:** Client-Catch-up-Verhalten. · **Permissions:** `events.view` · **Audit Events:** —

### E07-06 · Ereignisspeicher (Arbeitswarteschlange)
**Epic:** 07 · **Phase:** 3 · **Area:** frontend, a11y · **Branch:** feature/<nr>-ui-event-queue

- **Ziel:** Die gemeinsame Warteschlange oben auf der Arbeitsplatzseite mit immer sichtbaren Aktionen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.3: Aktionen Annehmen/Quittieren/Bearbeiten/Archivieren immer sichtbar; Klick öffnet die Meldung unten.
- **Scope:** Queue-Komponente, Prioritäts-Badges, Aktionen mit Rechteprüfung (aus `/auth/me`), Klick → Detailpanel; Sortierung nach Priorität.
- **Nicht im Scope:** Animation (E07-07); Detailpanel (E07-08).
- **Abhängigkeiten:** E03-07, E03-12, E07-05.
- **Acceptance Criteria:** Aktion ohne Recht ist sichtbar-aber-deaktiviert mit Tooltip (kein Verstecken der Fachlichkeit); Server bleibt Autorität (403 sauber behandelt).
- **Tests:** Vitest; Playwright: Annehmen aus der Queue.
- **Security-Auswirkung:** UI-Gating nur kosmetisch; Enforcement serverseitig.
- **HA-Auswirkung:** — · **Permissions:** `events.view/accept/acknowledge/edit/archive` · **Audit Events:** —

### E07-07 · Prioritäts-Animation (kritisch/hoch) + reduced-motion
**Epic:** 07 · **Phase:** 3 · **Area:** frontend, a11y · **Branch:** feature/<nr>-ui-priority-animation

- **Ziel:** Kritische/hohe Ereignisse sind deutlich animiert, respektieren aber `prefers-reduced-motion`.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.3/§26.13.
- **Scope:** Animations-Tokens, `@media (prefers-reduced-motion: reduce)`-Fallback (statische, farblich starke Hervorhebung), Intensität hoch < kritisch.
- **Nicht im Scope:** Anrufwarteschlangen-Animation (Epic 14).
- **Abhängigkeiten:** E07-06.
- **Acceptance Criteria:** Bei reduced-motion keine Bewegung, aber weiterhin klar erkennbar; kein Layout-Shift.
- **Tests:** Playwright mit `reduced-motion`-Emulation; visuelle Regression optional.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E07-08 · Ereignisdetail / Meldungs-Panel
**Epic:** 07 · **Phase:** 3 · **Area:** frontend · **Branch:** feature/<nr>-ui-event-detail

- **Ziel:** Klick auf ein Ereignis öffnet die Meldung unten im Content mit allen Details.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.3/§13.5.
- **Scope:** Detailpanel (Kopf, Statushistorie, Assignee, Notizen), Bearbeiten-Formular (Optimistic Concurrency über E07-04), Platzhalter-Slot für Maßnahmen (E07-09).
- **Nicht im Scope:** Maßnahmen-Panel selbst (E07-09).
- **Abhängigkeiten:** E03-12, E07-06.
- **Acceptance Criteria:** 409 beim Speichern → Nutzer sieht neuen Stand, kein Datenverlust; Panel per Tastatur vollständig bedienbar.
- **Tests:** Vitest; Playwright: Öffnen, Bearbeiten, Konflikt.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `events.view/edit` · **Audit Events:** —

### E07-09 · Maßnahmen-Panel (Workflow-Ausführungsansicht)
**Epic:** 07 · **Phase:** 3 · **Area:** frontend, a11y · **Branch:** feature/<nr>-ui-measures-panel

- **Ziel:** Nach Öffnen des Ereignisses erscheinen die Maßnahmen als klare Schritt-für-Schritt-Ausführung des Graphen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.5/§33; nur bearbeitbar wenn angenommen+quittiert+berechtigt; Verantwortung bleibt am Ereignis.
- **Scope:** Anzeige aktive/erledigte/wartende Schritte, Zeitstempel, Fortschritt, benötigte Entscheidungen; Schritt-abschließen/Entscheidung-treffen (E05-12); XOR/OR-Entscheidungs-UI.
- **Nicht im Scope:** Grafischer Editor (E07-19).
- **Abhängigkeiten:** E05-12, E07-08.
- **Acceptance Criteria:** Bearbeitung gesperrt bis Ereignis angenommen+quittiert; Schrittansicht spiegelt Token-Zustand; keine Schritt-Zuweisung an Einzelpersonen.
- **Tests:** Playwright: AND/XOR/OR-Graph abarbeiten.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `workflows.view/execute` · **Audit Events:** —

### E07-10 · Ereignisverantwortung-UI (Übertragen, Präsenz, Übernehmen)
**Epic:** 07 · **Phase:** 3 · **Area:** frontend · **Branch:** feature/<nr>-ui-event-ownership

- **Ziel:** Verantwortung übertragen, eigenen Präsenzstatus setzen, Ereignis übernehmen (mit Bestätigung).
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.4.
- **Scope:** Assignee-Anzeige/-Wechsel, Präsenz-Umschalter (verfügbar/Pause/offline), „Übernehmen"-Button nur sichtbar/aktiv wenn Verantwortlicher Pause/offline, Bestätigungsdialog + optional Grund.
- **Nicht im Scope:** Server-Logik (E03-09/10).
- **Abhängigkeiten:** E03-09/10, E02-11.
- **Acceptance Criteria:** Übernahme-Aktion ohne Pause/offline nicht möglich; Bestätigung Pflicht; Audit serverseitig.
- **Tests:** Playwright: Präsenz auf Pause → anderer Nutzer übernimmt.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `events.assign/takeover` `users.view` · **Audit Events:** — (Server).

### E07-11 · Archiv-Ansicht + Nachbearbeitungsnotizen
**Epic:** 07 · **Phase:** 3 · **Area:** frontend · **Branch:** feature/<nr>-ui-archive-view

- **Ziel:** Ereignisse-Ansicht chronologisch inkl. Archiv, vollständige Detailsicht, Nachbearbeitungsnotizen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.6.
- **Scope:** Listenansicht (Filter/Datum), Detailsicht archivierter Ereignisse (read-only außer Postprocess-Notizen), Notiz-Editor.
- **Nicht im Scope:** Reaktivierung (E07-12); Export-PDF (Epic 20).
- **Abhängigkeiten:** E03-12, E20-02/03/04.
- **Acceptance Criteria:** Archivierte Ereignisse nicht in der Arbeitswarteschlange, aber hier vollständig einsehbar; Notizen auditiert (Server).
- **Tests:** Playwright: Archiv öffnen, Detail ansehen, Notiz hinzufügen.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `events.view/postprocess` · **Audit Events:** — (Server).

### E07-12 · Reaktivierungs-Bestätigungsdialog
**Epic:** 07 · **Phase:** 3 · **Area:** frontend · **Branch:** feature/<nr>-ui-reactivate-confirm

- **Ziel:** Reaktivierung nur über explizites Warn-/Bestätigungspopup.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.6/§26.8: „niemals Ein-Klick".
- **Scope:** Modaler Dialog mit Warntext, Grundfeld, Doppelbestätigung, Rechteprüfung; sendet `confirm=true` (E03-11).
- **Nicht im Scope:** Server-Logik.
- **Abhängigkeiten:** E03-11.
- **Acceptance Criteria:** Kein Pfad reaktiviert ein Ereignis ohne diesen Dialog; Dialog tastaturbedienbar; Abbruch ist Default-Fokus.
- **Tests:** Playwright: Reaktivierung nur nach Bestätigung.
- **Security-Auswirkung:** verhindert Fehlbedienung. · **HA-Auswirkung:** — · **Permissions:** `events.reactivate` · **Audit Events:** — (Server).

### E07-13 · Globale Topbar-Prioritätswarnung
**Epic:** 07 · **Phase:** 3 · **Area:** frontend, a11y · **Branch:** feature/<nr>-ui-priority-topbar-alert

- **Ziel:** Auf allen Seiten außer Arbeitsplatz zeigt die Topbar eine auffällige rote Warnung vor der Uhr, wenn ein hohes/kritisches Ereignis unangenommen ist; Klick springt zum Ereignis.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.7.
- **Scope:** Warnkomponente gebunden an `/events/priority-alert` (E03-15) + Stream; Klick → Route Arbeitsplatz + Ereignis öffnen; reduced-motion-konform.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E03-15, E07-05, E07-08.
- **Acceptance Criteria:** Warnung erscheint nicht auf der Arbeitsplatzseite; verschwindet nach Annahme; Klick öffnet exakt das betreffende Ereignis.
- **Tests:** Playwright: high-Event erzeugen → Warnung auf „Wetterlage", Klick → Arbeitsplatz+Detail.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `events.view` · **Audit Events:** —

### E07-14 · i18n: DE-Locale vollständig + Missing-Key-Lint
**Epic:** 07 · **Phase:** 3 · **Area:** frontend · **Branch:** feature/<nr>-ui-i18n

- **Ziel:** Alle UI-Strings laufen über vue-i18n; DE ist vollständig; fehlende Keys brechen den Build.
- **Fachlicher Hintergrund:** ADR-0013 (DE launch locale); MASTER_PROMPT §6 „i18n vorbereiten".
- **Scope:** Key-Extraktion, `de.json` vervollständigen, Lint-Regel/Test für fehlende/ungenutzte Keys, Format für Datum/Zeit (Europe/Berlin, ADR-0017).
- **Nicht im Scope:** Weitere Sprachen.
- **Abhängigkeiten:** E07-03.
- **Acceptance Criteria:** Kein hartkodierter sichtbarer String; CI meldet fehlende Keys; Zeit-/Datumsformat konsistent.
- **Tests:** Unit: i18n-Key-Vollständigkeit; Lint.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E07-15 · Accessibility-Baseline (Tastaturpfade, a11y-Lint error, axe-E2E)
**Epic:** 07 · **Phase:** 3 · **Area:** frontend, a11y · **Branch:** feature/<nr>-ui-a11y-baseline

- **Ziel:** Jede bedienbare Funktion hat einen tastaturerreichbaren Nicht-Drag-Pfad; a11y-Verstöße brechen den Build.
- **Fachlicher Hintergrund:** `.ai/RULES.md`: „Accessibility is a functional requirement"; MASTER_PROMPT §26.14.
- **Scope:** `eslint-plugin-vuejs-accessibility` auf error, axe-Checks in Playwright für Kernseiten, Fokus-Management/Skip-Links, Kontrast gegen Design-Tokens.
- **Nicht im Scope:** Feature-spezifische a11y (in den jeweiligen UI-Issues, hier die Baseline + CI-Gate).
- **Abhängigkeiten:** E07-03.
- **Acceptance Criteria:** CI schlägt bei a11y-Lint-Fehler fehl; axe ohne kritische Verstöße auf Arbeitsplatz/Ereignisse/Wetterlage; Drag-only-Funktionen haben Alternative.
- **Tests:** Playwright+axe; Lint.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E07-16 · Pflicht-E2E: Ereignis-Lebenszyklus
**Epic:** 07 · **Phase:** 3 · **Area:** frontend, test · **Branch:** feature/<nr>-e2e-event-lifecycle

- **Ziel:** Der komplette §24-E2E-Ablauf läuft grün.
- **Fachlicher Hintergrund:** MASTER_PROMPT §24: erzeugen → annehmen → quittieren → bearbeiten → übertragen → übernehmen → Maßnahmen abschließen → archivieren → Archivdetails → reaktivieren per Bestätigung.
- **Scope:** Playwright-Spec über echten Backend-Stack (Compose), Testdaten-Seed, Assertions inkl. Audit-Sichtprüfung via API.
- **Nicht im Scope:** Telefonie-E2E (Epic 11).
- **Abhängigkeiten:** E07-06..12, E03-*, E05-*.
- **Acceptance Criteria:** Alle 10 Schritte automatisiert grün; Reaktivierung nur nach Bestätigung; Audit-Einträge vorhanden.
- **Tests:** ebendieser E2E-Flow (CI, nightly + PR-smoke-Teilmenge).
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** div. · **Audit Events:** verifiziert.

### E07-17 · Theme-Tokens (light/dark, data-theme)
**Epic:** 07 · **Phase:** 3 · **Area:** frontend · **Branch:** feature/<nr>-ui-theme-tokens

- **Ziel:** Vollständige Token-Palette, hell/dunkel über `prefers-color-scheme` + `data-theme`-Override.
- **Fachlicher Hintergrund:** ADR-0013.
- **Scope:** `src/theme/tokens.css` ausbauen (Farben/Abstände/Radius/Elevation), PrimeVue-Aura-Preset anbinden, Kontrast-Prüfung.
- **Nicht im Scope:** DB-Branding-Assets-Beschaffung.
- **Abhängigkeiten:** E07-03.
- **Acceptance Criteria:** Kein Hardcoded-Hex in Komponenten; dunkel/hell konsistent; Kontrast AA für Text.
- **Tests:** Lint (kein Inline-Hex); visuelle Stichprobe.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E07-18 · Komm-Sidebar-Gerüst (Tabs Telefon/Gespräch/Telefonbuch/Historie)
**Epic:** 07 · **Phase:** 3 · **Area:** frontend · **Branch:** feature/<nr>-ui-comms-sidebar-shell

- **Ziel:** Struktur der rechten Sidebar mit den vier Tabs, ohne Fachlogik.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.8.
- **Scope:** Tab-Container, leere Panels mit Platzhaltern, Zustandserhalt beim Tab-Wechsel, Resize-Interaktion (aus E07-03).
- **Nicht im Scope:** Telefonie-Funktionen (Epic 11); Telefonbuch (Epic 14).
- **Abhängigkeiten:** E07-03.
- **Acceptance Criteria:** Tabs tastaturbedienbar; Panel-Zustand bleibt beim Wechsel erhalten.
- **Tests:** Vitest; Playwright: Tabwechsel.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E07-19 · Grafischer EPK-Editor (Admin)
**Epic:** 07 · **Phase:** 3 · **Area:** frontend, a11y · **Branch:** feature/<nr>-ui-epk-editor

- **Ziel:** Admins bauen Workflow-Graphen visuell (Drag & Drop) mit vollständiger Tastaturalternative, Eigenschaftenpanel, Graphvalidierung, Simulation, Publish.
- **Fachlicher Hintergrund:** MASTER_PROMPT §33.3.
- **Scope:** Canvas mit Knoten/Kanten, Palette (Event/Function-Kinds/Connector AND-OR-XOR), Eigenschaftenpanel inkl. Rule-DSL-Bedingungseditor (strukturiert, kein Freitext-Code), Inline-Validierungsanzeige (E05-06), Simulationslauf (E05-13), Publish-Dialog mit Changelog; Nicht-Drag-Bedienung (Knoten hinzufügen/verbinden per Menü/Tastatur).
- **Nicht im Scope:** Engine (Epic 05).
- **Abhängigkeiten:** E05-06, E05-13.
- **Acceptance Criteria:** §35 „ungültiger Graph nicht publizierbar" auch über die UI; jede Editoraktion ist ohne Maus möglich; Bedingungseditor erzeugt nur DSL-JSON.
- **Tests:** Playwright: Graph bauen (nur Tastatur), validieren, simulieren, publish blockiert bei Fehler.
- **Security-Auswirkung:** Kein Code-Eval im Editor; `workflows.manage_templates`.
- **HA-Auswirkung:** — · **Permissions:** `workflows.view/manage_templates` · **Audit Events:** — (Server).

---

# EPIC 08 · BBZ Desktop Client

**Milestone:** `08 BBZ Desktop Client` · **Phase:** 4 · **Ziel des Epics:**
Chromium/Electron-Kiosk-Client, der die Web-UI einbettet, an den lokalen
Client-Agent koppelt und signiert aktualisiert wird. Quellen: MASTER_PROMPT §6
(Desktop Client), ADR-0013 („Electron only embeds it").

### E08-01 · Electron-Scaffold in apps/bbz-kiosk, bettet Web-Build ein
**Epic:** 08 · **Phase:** 4 · **Area:** frontend, agent · **Branch:** feature/<nr>-kiosk-scaffold
- **Ziel:** Ein Electron-Projekt lädt die Vue-Web-UI in einem BrowserWindow.
- **Fachlicher Hintergrund:** MASTER_PROMPT §6; `apps/bbz-kiosk` ist heute Placeholder.
- **Scope:** Electron-Grundprojekt, `contextIsolation`, kein `nodeIntegration` im Renderer, Preload-Bridge minimal, Laden der Web-UI (URL konfigurierbar).
- **Nicht im Scope:** Kiosk-Modus (E08-02); Update (E08-05); Agent-IPC (E08-04).
- **Abhängigkeiten:** Epic 07 (lauffähige Web-UI).
- **Acceptance Criteria:** Startet lokal gegen den Dev-Stack; Renderer ohne Node-Zugriff; Lint/Typecheck grün.
- **Tests:** Smoke: App startet, lädt `/`, zeigt Login.
- **Security-Auswirkung:** Renderer-Sandbox, strikte Preload-API, keine Remote-Module.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E08-02 · Kiosk-/Autostart-Modus + Single-Instance + Display-Config
**Epic:** 08 · **Phase:** 4 · **Area:** agent · **Branch:** feature/<nr>-kiosk-mode
- **Ziel:** Vollbild-Kiosk, Autostart, genau eine Instanz, konfigurierbares Ziel-Display.
- **Fachlicher Hintergrund:** MASTER_PROMPT §6 „Autostart/Kiosk-Modus".
- **Scope:** Kiosk-Fenster (kein Chrome-UI), Single-Instance-Lock, Display-Auswahl, Sperre gegen Verlassen (konfigurierbar), Autostart-Registrierung (Windows).
- **Nicht im Scope:** Watchdog (E08-06).
- **Abhängigkeiten:** E08-01.
- **Acceptance Criteria:** Zweiter Start fokussiert die bestehende Instanz; Kiosk lässt sich nur über definierten Weg beenden.
- **Tests:** Manuell/Smoke: Kiosk-Start, Single-Instance.
- **Security-Auswirkung:** Kein Ausbruch in andere Anwendungen über die UI.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E08-03 · Client-ID / Arbeitsplatz-ID-Provisionierung
**Epic:** 08 · **Phase:** 4 · **Area:** agent · **Branch:** feature/<nr>-kiosk-client-id
- **Ziel:** Der Client kennt seine `client_id`/`workplace_id` aus lokaler Konfiguration und sendet sie im Command-Envelope.
- **Fachlicher Hintergrund:** MASTER_PROMPT §6/§15 (`X-Client-Id`, `X-Workplace-Id`).
- **Scope:** Konfig-Datei/Provisionierungsschritt, Übergabe an die Web-UI via Preload, Validierung.
- **Nicht im Scope:** Enrollment/Zertifikat (Epic 09).
- **Abhängigkeiten:** E08-01.
- **Acceptance Criteria:** Fehlt die Konfig → klarer Provisionierungs-Screen, kein anonymer Betrieb; IDs erscheinen in den API-Headern.
- **Tests:** Smoke: Header-Prüfung; fehlende Konfig → Fehlerscreen.
- **Security-Auswirkung:** Bindung von Aktionen an Arbeitsplatz.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E08-04 · Kopplung an den lokalen BBZ-Client-Agent
**Epic:** 08 · **Phase:** 4 · **Area:** agent · **Branch:** feature/<nr>-kiosk-agent-ipc
- **Ziel:** Kiosk und lokaler Agent kommunizieren über localhost-IPC (Health, Serverwahl, Offline-Status).
- **Fachlicher Hintergrund:** MASTER_PROMPT §6; ARCHITECTURE: „BBZ Client and BKU Agent do not trust/control each other directly."
- **Scope:** IPC-Kanal (localhost, authentifiziert), Weitergabe des vom Agent gewählten aktiven Servers + Sync-Status an die UI.
- **Nicht im Scope:** Agent-Logik (Epic 09).
- **Abhängigkeiten:** E08-01, E09-03.
- **Acceptance Criteria:** UI zeigt Agent-Status; fällt der Agent aus, degradiert die UI kontrolliert (Direktverbindung als Fallback konfigurierbar).
- **Tests:** Integration mit Agent-Stub.
- **Security-Auswirkung:** localhost-only, Token-gesichert; kein Browser-zu-Agent-Direktvertrauen für privilegierte Kommandos.
- **HA-Auswirkung:** Agent liefert die Serverwahl.
- **Permissions:** — · **Audit Events:** —

### E08-05 · Signierter Update-Mechanismus
**Epic:** 08 · **Phase:** 4 · **Area:** agent, security · **Branch:** feature/<nr>-kiosk-updater
- **Ziel:** Der Kiosk aktualisiert sich aus einer signierten Quelle.
- **Fachlicher Hintergrund:** MASTER_PROMPT §6 „Update-Mechanismus".
- **Scope:** electron-updater gegen internes Repo, Signaturprüfung, gestaffeltes Rollout, Update nur außerhalb aktiver Alarmlage (konfigurierbar).
- **Nicht im Scope:** Server-Deployment (Epic 24).
- **Abhängigkeiten:** E08-01, E24-01 (Artefaktquelle).
- **Acceptance Criteria:** Unsigniertes/verändertes Paket wird abgelehnt; Downgrade-Schutz.
- **Tests:** Update-Simulation: gültig akzeptiert, manipuliert abgelehnt.
- **Security-Auswirkung:** Supply-Chain am Endpoint; Codesignatur.
- **HA-Auswirkung:** — · **Permissions:** `bku.device.restart`-analog nicht nötig; Update ist Client-lokal. · **Audit Events:** `CLIENT_UPDATED` (Audit vom Server bei Versionsmeldung).

### E08-06 · Crash-/Relaunch-Supervision (Watchdog)
**Epic:** 08 · **Phase:** 4 · **Area:** agent · **Branch:** feature/<nr>-kiosk-watchdog
- **Ziel:** Stürzt der Renderer/Kiosk ab, wird er automatisch neu gestartet und der Vorfall gemeldet.
- **Fachlicher Hintergrund:** MASTER_PROMPT §6 (Client-Agent: „Kiosk-Prozessüberwachung").
- **Scope:** Renderer-Crash-Handler, exponentielles Relaunch-Backoff, Vorfallsmeldung an den Agent/Server; „black screen"-Erkennung.
- **Nicht im Scope:** Agent-seitige Prozessüberwachung (E09-10) — hier die App-interne Seite.
- **Abhängigkeiten:** E08-01, E08-04.
- **Acceptance Criteria:** Erzwungener Renderer-Crash → automatischer Relaunch < 5 s; Ereignis wird gemeldet.
- **Tests:** Crash-Injection-Test.
- **Security-Auswirkung:** Verfügbarkeit des Arbeitsplatzes.
- **HA-Auswirkung:** Arbeitsplatz bleibt bedienbar.
- **Permissions:** — · **Audit Events:** `CLIENT_CRASH_RECOVERED` (Audit).

### E08-07 · Load-Strategie-ADR + Umsetzung (Server-Build vs. Bundle) & signierter CI-Build
**Epic:** 08 · **Phase:** 4 · **Area:** agent, infra · **Branch:** feature/<nr>-kiosk-load-strategy-build
- **Ziel:** Entscheidung, ob die Web-UI vom Server geladen oder gebündelt wird, plus signierter Windows-Build in CI.
- **Fachlicher Hintergrund:** `.ai/CURRENT_STATE.md` offene Frage „Electron: load web build from server vs bundle".
- **Scope:** ADR-0022 mit Entscheidung + Begründung (Offline-Fähigkeit vs. Update-Einfachheit); Umsetzung der gewählten Variante; `apps/bbz-kiosk`-Build-Job in CI mit Codesignatur.
- **Nicht im Scope:** Auto-Update-Server (E08-05).
- **Abhängigkeiten:** E08-01, E01-04.
- **Acceptance Criteria:** ADR-0022 `Accepted`; CI erzeugt ein signiertes Installationspaket; gewählte Ladevariante implementiert und dokumentiert.
- **Tests:** CI-Build; Signaturprüfung.
- **Security-Auswirkung:** Codesignatur; klare Herkunft der UI-Assets.
- **HA-Auswirkung:** Bundle-Variante erhöht Offline-Robustheit (Epic 09).
- **Permissions:** — · **Audit Events:** —

---

# EPIC 09 · BBZ Client Agent

**Milestone:** `09 BBZ Client Agent` · **Phase:** 4 · **Ziel des Epics:**
Lokaler Windows-Dienst am BBZ-Arbeitsplatz: Server-Discovery, Health, Failover,
verschlüsselter Cache, Offline-Outbox, Geräteidentität, Kiosk-Überwachung.
Quellen: MASTER_PROMPT §6/§5, ADR-0009.

### E09-01 · ADR-0009 bestätigen (Go) → Accepted
**Epic:** 09 · **Phase:** 4 · **Area:** documentation, agent · **Branch:** docs/<nr>-adr-0009-accept
- **Ziel:** Die Sprachwahl für beide Agents ist final entschieden.
- **Fachlicher Hintergrund:** ADR-0009 „Proposed — decision pending"; `.ai/CURRENT_STATE.md` offene Frage „Go vs Rust".
- **Scope:** Review, ggf. kleiner PoC-Vergleich (Windows-Service, Signatur), Status auf `Accepted` (oder begründet `Rust`), Konsequenzen für geteilte Libs.
- **Nicht im Scope:** Agent-Implementierung.
- **Abhängigkeiten:** —
- **Acceptance Criteria:** ADR-0009 `Accepted`; geteilte-Lib-Strategie (discovery/outbox/command-envelope) benannt.
- **Tests:** Doc-only.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E09-02 · Agent-Scaffold + Windows-Service-Lebenszyklus
**Epic:** 09 · **Phase:** 4 · **Area:** agent · **Branch:** feature/<nr>-client-agent-scaffold
- **Ziel:** Ein installierbarer Dienst mit Start/Stop/Restart, Logging, Konfiguration.
- **Fachlicher Hintergrund:** MASTER_PROMPT §6.
- **Scope:** `agents/bbz-client-agent` Go-Projekt, Service-Wrapper, strukturierte Logs, Config-Datei (`BBZ_`-analog), Health-Selbstreport.
- **Nicht im Scope:** Discovery/Failover (E09-03/04).
- **Abhängigkeiten:** E09-01.
- **Acceptance Criteria:** Dienst installiert/deinstalliert sauber; überlebt Neustart; Konfig-Reload dokumentiert.
- **Tests:** Service-Lifecycle-Test (CI-Runner Windows); Config-Parsing.
- **Security-Auswirkung:** Dienst läuft mit minimalen Rechten.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E09-03 · Server-Discovery + Health-Polling
**Epic:** 09 · **Phase:** 4 · **Area:** agent · **Branch:** feature/<nr>-client-agent-discovery
- **Ziel:** Der Agent kennt SRV01/SRV02 und pollt `/health/live`, `/health/ready`, `/cluster/status`.
- **Fachlicher Hintergrund:** MASTER_PROMPT §4.
- **Scope:** Konfigurierbare Serverliste, Poll-Intervalle, Bewertung „erreichbar/ready", Auswahl des aktiven Servers, Bereitstellung an den Kiosk (E08-04).
- **Nicht im Scope:** Umschalt-Datenfluss (E09-04).
- **Abhängigkeiten:** E09-02, E06-04.
- **Acceptance Criteria:** Nicht-`ready`-Server wird nicht ausgewählt; Statuswechsel wird an die UI gemeldet.
- **Tests:** Integration gegen zwei Fake-Server (einer nicht ready).
- **Security-Auswirkung:** TLS-Validierung der Serverendpunkte.
- **HA-Auswirkung:** Grundlage der Client-seitigen Serverwahl.
- **Permissions:** — · **Audit Events:** —

### E09-04 · Failover-Logik (Serverwechsel + last event_seq)
**Epic:** 09 · **Phase:** 4 · **Area:** agent · **Branch:** feature/<nr>-client-agent-failover
- **Ziel:** Fällt der aktive Server aus, schaltet der Agent sofort um und der Client macht Catch-up ab dem letzten `event_seq`.
- **Fachlicher Hintergrund:** MASTER_PROMPT §4 (Schritte 1–5).
- **Scope:** Umschaltentscheidung, Übergabe `after_seq` an den Stream-Client, UI-Zustandserhalt, „offene UI-Arbeit soweit möglich erhalten".
- **Nicht im Scope:** Offline-Modus beider Server (E09-06/07).
- **Abhängigkeiten:** E09-03, E06-07.
- **Acceptance Criteria:** Serverausfall → Umschaltung < konfiguriertem Timeout, keine verlorenen Events, laufende Formulареingaben bleiben erhalten.
- **Tests:** Integration: aktiver Server weg → Reconnect am anderen, Stream lückenlos.
- **Security-Auswirkung:** Re-Auth am neuen Server.
- **HA-Auswirkung:** Kern der nahtlosen Übernahme.
- **Permissions:** — · **Audit Events:** — (Server ggf. `CLIENT_FAILOVER`).

### E09-05 · Verschlüsselter lokaler Cache (gelesene Ereignisse)
**Epic:** 09 · **Phase:** 4 · **Area:** agent, security · **Branch:** feature/<nr>-client-agent-cache
- **Ziel:** Bereits geladene Ereignisse sind verschlüsselt lokal verfügbar, wenn beide Server fehlen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §5: „lokaler Client-Agent hält einen verschlüsselten lokalen Cache."
- **Scope:** Verschlüsselter Store (Schlüssel aus Geräteidentität/OS-Keystore), Cache gelesener Ereignisse + Stammdaten, Größen-/Retention-Limits.
- **Nicht im Scope:** Schreibende Offline-Aktionen (E09-06).
- **Abhängigkeiten:** E09-02, E09-08.
- **Acceptance Criteria:** Ohne Serververbindung sind zuletzt geladene Ereignisse lesbar; Cache-Datei ist ohne Geräteschlüssel unbrauchbar.
- **Tests:** Integration: offline → Lesezugriff; Datei-at-rest verschlüsselt (Negativtest ohne Schlüssel).
- **Security-Auswirkung:** Fachdaten at rest verschlüsselt; Schlüssel nicht im Klartext auf Platte.
- **HA-Auswirkung:** Degraded-Read-Betrieb.
- **Permissions:** — · **Audit Events:** —

### E09-06 · Offline-Outbox (pending Commands)
**Epic:** 09 · **Phase:** 4 · **Area:** agent · **Branch:** feature/<nr>-client-agent-outbox
- **Ziel:** Bei Totalausfall erzeugte Schreibvorgänge werden lokal als Pending-Commands mit `command_id/client_timestamp/offline=true/lokale Sequenz` gehalten.
- **Fachlicher Hintergrund:** MASTER_PROMPT §5 (erlaubte Offline-Schreibvorgänge; eingeschränkte Operationen).
- **Scope:** Lokale Outbox, Whitelist erlaubter Offline-Operationen (Gesprächsdoku, Freitextnotizen, lokale Pending-Commands), Sperre der eingeschränkten Operationen (Verantwortungswechsel, Archiv/Reaktivierung, Rollen).
- **Nicht im Scope:** Server-seitige Konfliktprüfung (E09-07).
- **Abhängigkeiten:** E09-05.
- **Acceptance Criteria:** Nur Whitelist-Operationen offline möglich; jede Offline-Schreibaktion trägt die vier Pflichtfelder; eingeschränkte Aktionen sind klar blockiert.
- **Tests:** Unit/Integration: Offline-Erzeugung, Whitelist-Enforcement.
- **Security-Auswirkung:** Verhindert riskante Operationen ohne Serverautorität.
- **HA-Auswirkung:** Degraded-Write mit späterer idempotenter Sync.
- **Permissions:** — · **Audit Events:** —

### E09-07 · Reconnect + idempotente Sync + Konfliktanzeige
**Epic:** 09 · **Phase:** 4 · **Area:** agent, backend · **Branch:** feature/<nr>-client-agent-sync
- **Ziel:** Nach Reconnect synchronisiert der Agent die Outbox idempotent; Konflikte werden als `CONFLICT` sichtbar.
- **Fachlicher Hintergrund:** MASTER_PROMPT §5: „idempotent synchronisieren, Konfliktprüfung serverseitig, UI zeigt UNSYNCED/SYNCING/SYNCED/CONFLICT".
- **Scope:** Sync-Reihenfolge nach lokaler Sequenz, Wiederverwendung der `command_id` (E03-03 dedupliziert), Konflikt-Ergebnis → UI-Status, manuelle Auflösung.
- **Nicht im Scope:** Konfliktauflösungs-Policy im Detail (`.ai/CURRENT_STATE.md` offene Frage — hier nur Sichtbarmachen + einfache „Server gewinnt / lokal verwerfen"-Optionen).
- **Abhängigkeiten:** E09-06, E03-03, E07-05.
- **Acceptance Criteria:** Doppelte Sync erzeugt keinen Doppeleffekt; Konflikt blockiert kritische Weiterarbeit bis Auflösung; Statusübergänge korrekt.
- **Tests:** Integration: Offline-Aktion + zwischenzeitliche Serveränderung → CONFLICT; erneute Sync idempotent.
- **Security-Auswirkung:** Server bleibt Autorität.
- **HA-Auswirkung:** Sichere Wiedereingliederung.
- **Permissions:** — · **Audit Events:** Server auditiert die letztlich angewandten Commands.

### E09-08 · Geräteidentität / Zertifikats-Enrollment (mTLS vorbereiten)
**Epic:** 09 · **Phase:** 4 · **Area:** agent, security · **Branch:** feature/<nr>-client-agent-identity
- **Ziel:** Der Agent enrollt mit kurzlebigem Token und erhält eine eindeutige Geräteidentität/Zertifikat.
- **Fachlicher Hintergrund:** `.ai/SECURITY.md` „Agents enroll with short-lived token and receive a unique device identity/certificate."
- **Scope:** Enrollment-Endpoint (Server), Schlüsselerzeugung am Gerät, Zertifikatsausstellung, Nutzung für API-Auth (mTLS-fähig, mind. Bearer-Client-Cred), Rotationspfad.
- **Nicht im Scope:** BKU-Enrollment (Epic 10) — teilt aber Code.
- **Abhängigkeiten:** E02-05, E09-02.
- **Acceptance Criteria:** Enrollment-Token einmalig; danach nur Geräteidentität; Rotation ohne Re-Enrollment möglich; Sperrung serverseitig wirksam.
- **Tests:** Integration: Enroll → API-Call mit Geräteidentität → Sperrung → 401.
- **Security-Auswirkung:** Kern der Agent-Authentifizierung; Private Key im OS-Keystore.
- **HA-Auswirkung:** Identität gegen beide Server gültig.
- **Permissions:** `bku.agent.manage`-analog für Client-Agents (`agents.manage`, neu im Katalog ergänzen).
- **Audit Events:** `AGENT_ENROLLED` `AGENT_IDENTITY_ROTATED` `AGENT_REVOKED` (Audit).

### E09-09 · Hardware-/OS-Info-Reporting
**Epic:** 09 · **Phase:** 4 · **Area:** agent · **Branch:** feature/<nr>-client-agent-inventory
- **Ziel:** Der Agent meldet Geräte-/OS-Basisdaten für Betrieb/Diagnose.
- **Fachlicher Hintergrund:** MASTER_PROMPT §6.
- **Scope:** Erfassung (OS-Version, Hostname, Agent-Version, Kiosk-Version, Netz), periodischer Report, Anzeige in Admin/Diagnostics.
- **Nicht im Scope:** Detailliertes Asset-Management.
- **Abhängigkeiten:** E09-08.
- **Acceptance Criteria:** Report erscheint in der Admin-Ansicht; keine sensiblen Daten (keine User-Dateien).
- **Tests:** Integration: Report empfangen/angezeigt.
- **Security-Auswirkung:** Datensparsamkeit.
- **HA-Auswirkung:** — · **Permissions:** `system.cluster.view` (Anzeige) · **Audit Events:** —

### E09-10 · Kiosk-Prozessüberwachung + Command-Envelope-Lib + Agent-E2E
**Epic:** 09 · **Phase:** 4 · **Area:** agent, test · **Branch:** feature/<nr>-client-agent-watchdog-e2e
- **Ziel:** Der Agent überwacht den Kiosk-Prozess, teilt die Command-Envelope-/Replay-Lib mit dem BKU-Agent und besteht den Failover-E2E-Test.
- **Fachlicher Hintergrund:** MASTER_PROMPT §6; `.ai/TESTING.md` „agent failover SRV01 → SRV02".
- **Scope:** Prozess-Watchdog (Kiosk hängt/tot → Neustart anfordern), geteilte Go-Lib `command envelope + replay protection`, E2E „SRV01 aus → Agent arbeitet über SRV02 weiter".
- **Nicht im Scope:** BKU-spezifische Kommandos (Epic 10).
- **Abhängigkeiten:** E09-04, E08-06.
- **Acceptance Criteria:** Kiosk-Hang → Neustart ausgelöst + gemeldet; E2E-Failover grün; Envelope-Lib von beiden Agents genutzt.
- **Tests:** E2E (Compose + Agent): SRV01 kill, Weiterarbeit; Watchdog-Injection.
- **Security-Auswirkung:** Replay-Schutz zentral.
- **HA-Auswirkung:** verifiziert Agent-Failover.
- **Permissions:** — · **Audit Events:** `CLIENT_CRASH_RECOVERED`.

---

# EPIC 10 · BKU Agent

**Milestone:** `10 BKU Agent` · **Phase:** 4 · **Ziel des Epics:** Eigenständiger
Agent auf dem BKU-Arbeitsplatz, per Enrollment 1:1 an einen BBZ-Arbeitsplatz
gebunden, mit strikt typisierter Kommando-Allowlist, zentralem App-Katalog und
auditiertem Logout/Restart. Quellen: MASTER_PROMPT §28, `.ai/BKU_AGENT.md`,
ADR-0003, ADR-0009.

### E10-01 · DB-Schema: bku_agents, bku_agent_enrollments, bku_agent_commands
**Epic:** 10 · **Phase:** 4 · **Area:** db · **Branch:** feature/<nr>-schema-bku-agent
- **Ziel:** Migration für Agent-Registrierung, Enrollment und Kommandohistorie.
- **Fachlicher Hintergrund:** MASTER_PROMPT §34; `.ai/BKU_AGENT.md`.
- **Scope:** `bku_agents` (agent_id, workplace_id unique, device_pubkey, generation, status), `bku_agent_enrollments` (token_hash, workplace_id, expires_at, used_at), `bku_agent_commands` (command_id, agent_id, type, payload, issued_at, expires_at, requested_by, status, result).
- **Nicht im Scope:** Command-Bus (E10-04); Katalog (E10-02).
- **Abhängigkeiten:** E02-01.
- **Acceptance Criteria:** Migration up/down/up; ein aktiver Agent je `workplace_id`; Enrollment-Token nur gehasht.
- **Tests:** Migration; Constraint „ein Agent je Workplace".
- **Security-Auswirkung:** Kein Klartext-Token; Bindung an Workplace.
- **HA-Auswirkung:** expand-only. · **Permissions:** — · **Audit Events:** —

### E10-02 · DB-Schema: application_catalog + application_catalog_scopes
**Epic:** 10 · **Phase:** 4 · **Area:** db · **Branch:** feature/<nr>-schema-app-catalog
- **Ziel:** Migration für den zentral verwalteten Web-App-/Link-Katalog.
- **Fachlicher Hintergrund:** MASTER_PROMPT §28.2; `.ai/BKU_AGENT.md` „Application / Link Catalog".
- **Scope:** `application_catalog` (app_id, name, description, icon, url, browser_profile, launch_mode `window|app_window|tab`, enabled, sort_order, version, target_monitor_hint?), `application_catalog_scopes` (app_id, role/scope, workplace/site scope).
- **Nicht im Scope:** Admin-API (E10-10).
- **Abhängigkeiten:** E02-02.
- **Acceptance Criteria:** Migration up/down/up; URL-Feld validiert (Schema http/https); Scoping-Zeilen optional.
- **Tests:** Migration; URL-Validierung.
- **Security-Auswirkung:** Nur zentral gepflegte URLs (Basis der Allowlist).
- **HA-Auswirkung:** expand-only. · **Permissions:** — · **Audit Events:** —

### E10-03 · Enrollment: kurzlebiges Token, Geräteschlüssel, unveränderliche Bindung
**Epic:** 10 · **Phase:** 4 · **Area:** backend, agent, security · **Branch:** feature/<nr>-bku-enrollment
- **Ziel:** Ein BKU-Client enrollt sich für genau einen Arbeitsplatz und erhält unveränderliche `agent_id`/`workplace_id`.
- **Fachlicher Hintergrund:** `.ai/BKU_AGENT.md` „Enrollment / binding" (5 Schritte).
- **Scope:** Admin erzeugt Enrollment; Server gibt kurzlebiges Token; Agent erzeugt Schlüsselmaterial + enrollt; Server vergibt IDs; danach nur Geräteidentität; Token-Reuse ausgeschlossen.
- **Nicht im Scope:** Agent-Kommandos (E10-06 ff.).
- **Abhängigkeiten:** E10-01, E02-05, E09-08 (geteilte Identitätslib).
- **Acceptance Criteria:** Token einmalig + zeitlich begrenzt; zweiter Enrollment für belegten Workplace → abgelehnt (oder expliziter Re-Enroll-Flow mit Audit); Geräteidentität danach für alle Calls.
- **Tests:** Integration: Enroll-Happy-Path; Token-Reuse abgelehnt; Doppelbindung abgelehnt.
- **Security-Auswirkung:** Kern der Agent-Vertrauensbasis.
- **HA-Auswirkung:** Identität gegen SRV01/SRV02 gültig.
- **Permissions:** `bku.agent.manage` · **Audit Events:** `BKU_AGENT_ENROLLED` `BKU_AGENT_REENROLLED` `BKU_AGENT_REVOKED`.

### E10-04 · Agent-Command-Bus (server-geroutet, autorisiert, auditiert)
**Epic:** 10 · **Phase:** 4 · **Area:** backend · **Branch:** feature/<nr>-agent-command-bus
- **Ziel:** Kommandos vom BBZ-Client laufen über `BBZ API (authorize/audit) → Command Bus → gepaarter BKU-Agent → Ergebnis-Event`.
- **Fachlicher Hintergrund:** `.ai/BKU_AGENT.md` „Trust model"; `.ai/SECURITY.md` „routed through BBZ server authorization, not browser-to-agent direct trust".
- **Scope:** Command-Persistenz (E10-01), Zustellung an den verbundenen Agent (WS/long-poll), Ergebnis-Rückkanal als Domain-Event, Timeout/Expiry, Idempotenz (`command_id`), erwartete Agent-Generation.
- **Nicht im Scope:** Konkrete Kommandotypen (E10-06..09).
- **Abhängigkeiten:** E10-03, E03-03, E04-02.
- **Acceptance Criteria:** Kein Kommando erreicht den Agent ohne vorherige Server-Autorisierung + Audit; abgelaufenes Kommando wird nicht ausgeführt; doppeltes `command_id` → keine Doppelausführung.
- **Tests:** Integration: autorisiert→zugestellt→Ergebnis; unautorisiert→403, nichts zugestellt; Replay abgelehnt.
- **Security-Auswirkung:** Zentrale Kontroll-/Auditstelle; kein Direktvertrauen.
- **HA-Auswirkung:** Agent hält Verbindung zu beiden Servern; Zustellung idempotent.
- **Permissions:** je Kommando (E10-06..09) · **Audit Events:** `BKU_COMMAND_ISSUED` `BKU_COMMAND_RESULT`.

### E10-05 · BKU-Agent-Scaffold (Go), redundante SRV01/SRV02-Verbindung
**Epic:** 10 · **Phase:** 4 · **Area:** agent · **Branch:** feature/<nr>-bku-agent-scaffold
- **Ziel:** Installierbarer Windows-Dienst, der sich redundant mit beiden Servern verbindet und den überlebenden nutzt.
- **Fachlicher Hintergrund:** `.ai/BKU_AGENT.md` „connects redundantly to BBZ-SRV01/SRV02".
- **Scope:** Go-Projekt `agents/bku-agent`, Service-Lifecycle, Doppelverbindung, geteilte Libs aus E09 (discovery/outbox/envelope), Session-/Generation-Handling.
- **Nicht im Scope:** Kommando-Handler (E10-06..09).
- **Abhängigkeiten:** E09-01, E09-10 (geteilte Libs), E10-04.
- **Acceptance Criteria:** Dienst-Lifecycle sauber; Ausfall eines Servers → Weiterbetrieb über den anderen; nur eine effektive Kommandoquelle.
- **Tests:** Integration: SRV01 weg → Kommandos über SRV02.
- **Security-Auswirkung:** Minimalrechte-Dienst.
- **HA-Auswirkung:** Agent-Failover.
- **Permissions:** — · **Audit Events:** —

### E10-06 · Agent-Kommando: get_status / get_session_state / ping
**Epic:** 10 · **Phase:** 4 · **Area:** agent, backend · **Branch:** feature/<nr>-bku-cmd-status
- **Ziel:** Der BBZ-Client sieht Onlinezustand und interaktive Session-Info des gepaarten BKU-Clients.
- **Fachlicher Hintergrund:** MASTER_PROMPT §28.3; `.ai/BKU_AGENT.md` „Required commands".
- **Scope:** Agent-Erkennung „interaktive BKU-Session vorhanden", Health, Ping-RTT; Bereitstellung an die UI (E10-15).
- **Nicht im Scope:** Lifecycle-Aktionen (E10-08/09).
- **Abhängigkeiten:** E10-04, E10-05.
- **Acceptance Criteria:** Session-Status korrekt (aktiv/keine Session); Offline-Agent klar erkennbar; `bku.status.view` erforderlich.
- **Tests:** Integration: Session an/aus → Status; Agent offline → Status.
- **Security-Auswirkung:** Nur lesend; keine sensiblen Session-Inhalte.
- **HA-Auswirkung:** — · **Permissions:** `bku.status.view` · **Audit Events:** — (Statusabfrage nicht auditpflichtig).

### E10-07 · Agent-Kommando: launch/focus/close catalog_app (nur Allowlist)
**Epic:** 10 · **Phase:** 4 · **Area:** agent, backend, security · **Branch:** feature/<nr>-bku-cmd-launch
- **Ziel:** Zentral definierte Web-Apps (z. B. LeiDis/ARAMIS) werden im Unternehmensbrowser auf dem BKU-Client gestartet/fokussiert/geschlossen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §28.1/§28.2; `.ai/SECURITY.md` „only centrally allowlisted catalog entries".
- **Scope:** Kommando nimmt nur `app_id` (keine URL) entgegen; Server löst `app_id` → Katalogeintrag auf und übergibt geprüfte URL + launch_mode; Agent startet Chrome/Chromium-Fenster; Fokus/Schließen soweit unterstützt.
- **Nicht im Scope:** Katalogverwaltung (E10-10).
- **Abhängigkeiten:** E10-02, E10-04, E10-05.
- **Acceptance Criteria:** Beliebige URL/Shell/Executable im Payload → abgelehnt (E10-12); nur `enabled` + scope-erlaubte Apps startbar; Start erzeugt Ergebnis-Event.
- **Tests:** Integration: erlaubte App startet; URL-Payload abgelehnt; deaktivierte App abgelehnt.
- **Security-Auswirkung:** Kern der „keine willkürlichen URLs"-Regel.
- **HA-Auswirkung:** Idempotent (erneutes Launch fokussiert statt doppelt zu öffnen).
- **Permissions:** `bku.apps.launch` `bku.apps.close`
- **Audit Events:** `BKU_APP_LAUNCHED` `BKU_APP_CLOSED`.

### E10-08 · Agent-Kommando: logout_interactive_user (Permission + Bestätigung + Audit)
**Epic:** 10 · **Phase:** 4 · **Area:** agent, backend, security · **Branch:** feature/<nr>-bku-cmd-logout
- **Ziel:** Berechtigte Nutzer melden bei Schichtwechsel die noch aktive BKU-Sitzung ab — nach expliziter Bestätigung.
- **Fachlicher Hintergrund:** MASTER_PROMPT §28.3; `.ai/BKU_AGENT.md` „Shift change".
- **Scope:** Server prüft `bku.session.logout`, erzwingt Bestätigungs-/Grund-Flag, sendet Kommando; Agent führt OS-Logout der interaktiven Sitzung aus; Ergebnis-Event.
- **Nicht im Scope:** Restart (E10-09).
- **Abhängigkeiten:** E10-04, E10-06.
- **Acceptance Criteria:** Ohne Bestätigung → abgelehnt; ohne Permission → 403; Aktion + Ergebnis auditiert; keine Wirkung wenn keine interaktive Session.
- **Tests:** Integration: Bestätigung fehlt → abgelehnt; Happy-Path → Session weg + Audit.
- **Security-Auswirkung:** Hochwirksame Aktion; Doppelabsicherung.
- **HA-Auswirkung:** Idempotent (mehrfaches Logout unschädlich).
- **Permissions:** `bku.session.logout`
- **Audit Events:** `BKU_SESSION_LOGOUT` (Pflicht-Audit mit Grund/Schichtkontext).

### E10-09 · Agent-Kommando: restart_workstation (Permission + Bestätigung + Audit)
**Epic:** 10 · **Phase:** 4 · **Area:** agent, backend, security · **Branch:** feature/<nr>-bku-cmd-restart
- **Ziel:** Berechtigte Nutzer starten den BKU-Client nach expliziter Bestätigung neu.
- **Fachlicher Hintergrund:** MASTER_PROMPT §28.3.
- **Scope:** wie E10-08, aber OS-Neustart; Ankündigung/Timeout; Wiederverbindungs-Erwartung des Agents.
- **Nicht im Scope:** BBZ-Kiosk-Neustart (Epic 08).
- **Abhängigkeiten:** E10-08.
- **Acceptance Criteria:** Ohne Bestätigung/Permission → abgelehnt; Neustart auditiert; Agent meldet sich nach Reboot mit gleicher Identität wieder.
- **Tests:** Integration (VM): Neustart ausgelöst, Agent kommt zurück; Audit vorhanden.
- **Security-Auswirkung:** Sehr hochwirksam; strengste Absicherung.
- **HA-Auswirkung:** Idempotenz über `command_id` + Generation (kein Doppel-Reboot bei Retry).
- **Permissions:** `bku.device.restart`
- **Audit Events:** `BKU_DEVICE_RESTART` (Pflicht-Audit).

### E10-10 · Application-Catalog-Admin-API + Scopes
**Epic:** 10 · **Phase:** 4 · **Area:** backend, api · **Branch:** feature/<nr>-app-catalog-admin
- **Ziel:** Admins pflegen den App-Katalog (CRUD, Scopes, enable/disable, Sortierung, Version).
- **Fachlicher Hintergrund:** MASTER_PROMPT §28.2; `.ai/BKU_AGENT.md`.
- **Scope:** CRUD `/api/v1/app-catalog`, Scoping (Rollen/Workplace/Site), Aktiv-Toggle, Versionierung, URL-Validierung.
- **Nicht im Scope:** Client-Rendering (E10-11).
- **Abhängigkeiten:** E10-02, E02-08.
- **Acceptance Criteria:** `bku.catalog.manage` Pflicht; Änderung sofort wirksam für neue Launches; jede Änderung auditiert.
- **Tests:** API-CRUD; Scope-Filter; Audit.
- **Security-Auswirkung:** Definiert die Allowlist — hochprivilegiert.
- **HA-Auswirkung:** DB-basiert, sofort auf beiden Knoten.
- **Permissions:** `bku.catalog.view` `bku.catalog.manage`
- **Audit Events:** `BKU_CATALOG_CREATED/UPDATED/DELETED`.

### E10-11 · Katalog-Konsum-API + Client-Buttons
**Epic:** 10 · **Phase:** 4 · **Area:** backend, frontend · **Branch:** feature/<nr>-app-catalog-consume
- **Ziel:** Der BBZ-Client zeigt die für Rolle/Arbeitsplatz freigegebenen Katalogeinträge als zentral gepflegte Buttons.
- **Fachlicher Hintergrund:** MASTER_PROMPT §28.2: „Individuelle Browser-Lesezeichen sind nicht erforderlich."
- **Scope:** `GET /api/v1/app-catalog?for=me` (scope-gefiltert), UI-Buttons (Icon/Name/Sortierung), Klick → `launch_catalog_app(app_id)` (E10-07).
- **Nicht im Scope:** Verwaltung (E10-10).
- **Abhängigkeiten:** E10-07, E10-10, E07-03.
- **Acceptance Criteria:** Nutzer sieht nur erlaubte Apps; Klick startet auf dem gepaarten BKU-Client; deaktivierte Apps verschwinden.
- **Tests:** Playwright: Button sichtbar/nicht sichtbar je Rolle; Klick → Launch-Kommando.
- **Security-Auswirkung:** Scope-Filter serverseitig.
- **HA-Auswirkung:** — · **Permissions:** `bku.catalog.view` `bku.apps.launch` · **Audit Events:** — (Launch in E10-07).

### E10-12 · Ablehnung beliebiger URL / Shell / Executable (Enforcement + Tests)
**Epic:** 10 · **Phase:** 4 · **Area:** agent, security, test · **Branch:** feature/<nr>-bku-reject-arbitrary
- **Ziel:** Weder Server noch Agent akzeptieren beliebige URLs, Shell-/PowerShell-Kommandos oder Executable-Pfade von normalen Nutzern.
- **Fachlicher Hintergrund:** MASTER_PROMPT §28.1; `.ai/SECURITY.md`; `.ai/TESTING.md` „arbitrary URL/shell command rejection".
- **Scope:** Agent-Kommando-Schema strikt typisiert (nur bekannte Typen + `app_id`), Server-Validierung, Agent-seitige zweite Prüfung, negative Tests.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E10-04, E10-07.
- **Acceptance Criteria:** Payload mit `url`/`cmd`/`path` → 400/abgelehnt an beiden Stellen; kein Codepfad führt Freitext aus; Fuzz-Test findet keinen Bypass.
- **Tests:** Unit/Integration: umfangreiche Negativ-/Fuzz-Fälle; Contract-Test der Kommando-Enum.
- **Security-Auswirkung:** Zentrale Härtung gegen Remote-Code-Ausführung am Endpoint.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** `BKU_COMMAND_REJECTED` (Audit).

### E10-13 · Kommando-Zuverlässigkeit (Envelope, Expiry, Generation, Replay-Schutz)
**Epic:** 10 · **Phase:** 4 · **Area:** agent, backend · **Branch:** feature/<nr>-bku-cmd-reliability
- **Ziel:** Jedes Kommando trägt `command_id/workplace_id/agent_id/issued_at/expires_at/requested_by/Generation` und ist replay-geschützt.
- **Fachlicher Hintergrund:** `.ai/BKU_AGENT.md` „Reliability"; `.ai/SECURITY.md` „Commands contain command_id, nonce/sequence, expiry and are replay protected."
- **Scope:** Envelope-Definition, Ablaufprüfung, Generation-Match (nach Reboot/Re-Enroll alte Kommandos ungültig), Nonce/Sequence-Replay-Schutz.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E10-04.
- **Acceptance Criteria:** Abgelaufenes/gerätefremdes/älteres-Generation-Kommando → abgelehnt; Replay eines gültigen Kommandos → keine zweite Ausführung.
- **Tests:** Integration: Expiry, Generation-Wechsel, Replay.
- **Security-Auswirkung:** Verhindert verzögerte/wiederholte Fremdkommandos.
- **HA-Auswirkung:** Idempotenz über Failover.
- **Permissions:** — · **Audit Events:** — (siehe E10-04).

### E10-14 · BKU-Permissions-Seed
**Epic:** 10 · **Phase:** 4 · **Area:** db · **Branch:** feature/<nr>-bku-permissions-seed
- **Ziel:** Alle `bku.*`-Permissions sind im Katalog und Standardrollen sinnvoll zugeordnet.
- **Fachlicher Hintergrund:** MASTER_PROMPT §28.3; `docs/domain/permission-catalog.md` (BKU-Zeile).
- **Scope:** Daten-Migration: `bku.status.view/apps.launch/apps.close/session.logout/device.restart/catalog.view/catalog.manage/agent.manage`; Zuordnung (z. B. `device.restart`/`session.logout` nur Sichtleiter/Administrator).
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E02-14, E10-01.
- **Acceptance Criteria:** Alle acht Keys vorhanden; „Nur Lesen" hat höchstens `bku.status.view`/`bku.catalog.view`.
- **Tests:** Migration up/down; Assertion Rollen-Mapping.
- **Security-Auswirkung:** Least-Privilege-Defaults für hochwirksame Aktionen.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E10-15 · BKU-UI (Session-Status, Launch-Buttons, Schichtwechsel-Dialoge)
**Epic:** 10 · **Phase:** 4 · **Area:** frontend · **Branch:** feature/<nr>-bku-ui
- **Ziel:** Der BBZ-Client zeigt den gepaarten BKU-Zustand und bietet die (berechtigten) Aktionen mit Bestätigung.
- **Fachlicher Hintergrund:** MASTER_PROMPT §28.3.
- **Scope:** Statusanzeige (online/Session), Katalog-Buttons (E10-11), Dialoge „BKU-Benutzer abmelden"/„BKU-Client neu starten" mit Warnung + Grund + Doppelbestätigung.
- **Nicht im Scope:** Server-Logik.
- **Abhängigkeiten:** E10-06, E10-08, E10-09, E10-11.
- **Acceptance Criteria:** Aktionen nur sichtbar/aktiv bei Berechtigung + vorhandener Session; kein Ein-Klick-Logout/Restart; a11y grün.
- **Tests:** Playwright: Statusanzeige; Logout/Restart nur nach Bestätigung.
- **Security-Auswirkung:** UI-Gating kosmetisch; Enforcement serverseitig.
- **HA-Auswirkung:** — · **Permissions:** `bku.status.view/apps.launch/session.logout/device.restart` · **Audit Events:** — (Server).

### E10-16 · BKU-E2E-Suite (§35)
**Epic:** 10 · **Phase:** 4 · **Area:** test · **Branch:** feature/<nr>-bku-e2e
- **Ziel:** Der vollständige §35-BKU-Ablauf ist automatisiert grün.
- **Fachlicher Hintergrund:** MASTER_PROMPT §35 „BKU" (8 Schritte).
- **Scope:** E2E über Compose + BKU-Agent-Stub/VM: enroll → online im BBZ-Client → LeiDis über Katalogbutton → nicht freigegebene URL abgelehnt → Schichtwechsel-Logout mit Bestätigung → Neustart mit Bestätigung → Audit vorhanden → SRV01-Ausfall → Weiterbetrieb über SRV02.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E10-03..15.
- **Acceptance Criteria:** Alle 8 Schritte grün; Audit-Assertions via API; URL-Ablehnung nachgewiesen.
- **Tests:** ebendiese E2E-Suite (nightly).
- **Security-Auswirkung:** — · **HA-Auswirkung:** verifiziert Agent-Failover. · **Permissions:** div. · **Audit Events:** verifiziert.

---

# EPIC 11 · Telephony Core

**Milestone:** `11 Telephony Core` · **Phase:** 5 · **Ziel des Epics:**
Herstellerneutraler Telefonie-Kern: normalisiertes Event-Modell, Provider-
Protocol, Call-Aggregat mit Lebenszyklus, `telephony_mock`, Pflicht-
Anrufdokumentation, Komm-Sidebar-Funktionen. Quellen: MASTER_PROMPT §8.4/§8.12/
§13.8/§13.10, `packages/event-schemas`, ADR-0002.

### E11-01 · DB-Schema: calls, call_participants, call_documentation, lines
**Epic:** 11 · **Phase:** 5 · **Area:** db · **Branch:** feature/<nr>-schema-calls
- **Ziel:** Migration für Anruf-Kernobjekte.
- **Fachlicher Hintergrund:** MASTER_PROMPT §14.
- **Scope:** `calls` (id, bbz_call_id, provider, source_call_id, direction, state, line_id, started/ended, workplace_id), `call_participants` (call_id, number, display_name, role), `call_documentation` (call_id, category, free_text, by, at, mandatory_done), `lines` (id, provider, external_id, label, state).
- **Nicht im Scope:** Provider-Logik (E11-02+); UI.
- **Abhängigkeiten:** E02-01.
- **Acceptance Criteria:** Migration up/down/up; eigene BBZ-Call-ID unabhängig von `source_call_id`; `category` als Enum.
- **Tests:** Migration; Constraints.
- **Security-Auswirkung:** Rufnummern sind personenbeziehbar → Scope/Retention beachten.
- **HA-Auswirkung:** expand-only. · **Permissions:** — · **Audit Events:** —

### E11-02 · Telephony-Provider-Protocol finalisieren
**Epic:** 11 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-telephony-provider-protocol
- **Ziel:** Das `bbz_integration_sdk`-Telephony-Protocol deckt alle §8.12-Methoden ab; Capabilities im Manifest.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.12; SDK enthält bereits Protocol-Grundgerüst.
- **Scope:** `initialize/health/list_lines/get_line_state/subscribe_call_events/get_active_calls/dial/answer/hangup/hold/resume/transfer/conference/send_dtmf/resolve_caller/reconcile`; Capability-Modell (answer/hold/transfer/conference/dtmf/device_monitoring/media_termination).
- **Nicht im Scope:** Provider-Implementierungen (Epics 12/13, E11-05).
- **Abhängigkeiten:** Epic 01 (SDK-Paket).
- **Acceptance Criteria:** Protocol vollständig + typisiert; Mock (E11-05) erfüllt es; `mypy --strict` clean; import-linter: kein Core→SDK außerhalb `integrations_host`.
- **Tests:** Protocol-Konformitätstest gegen Mock.
- **Security-Auswirkung:** Keine Cisco-/Vendor-Typen im Core.
- **HA-Auswirkung:** `reconcile()` als Vertrag für Leaderwechsel (Epic 12).
- **Permissions:** — · **Audit Events:** —

### E11-03 · Normalisierte Telefonie-Event-Ingestion → Inbox → Dedupe
**Epic:** 11 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-telephony-ingest
- **Ziel:** Provider liefern normalisierte Telefonie-Events (`CALL_OFFERED`…`CTI_PROVIDER_OUT_OF_SERVICE`), die über die Provider-Inbox dedupliziert werden.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.4; `packages/event-schemas/telephony_event.v1.json`; ADR-0011 Inbox.
- **Scope:** Ingestion-Endpoint/Bus für Provider-Events, Validierung gegen Schema, `provider_event_inbox` (E04-07) mit `source_call_id`-basiertem Dedupe-Key, Weitergabe an das Call-Aggregat.
- **Nicht im Scope:** CUCM-Gateway (Epic 12).
- **Abhängigkeiten:** E04-07, E11-02, E04-05.
- **Acceptance Criteria:** Doppeltes Provider-Event (gleiche `source_call_id` + Typ) → einmal verarbeitet; Schemaverstoß → Reject; kein Vendor-Feld im Core-Payload.
- **Tests:** Integration: Duplikat-/Reconnect-Replay; Schema-Negativfall.
- **Security-Auswirkung:** Rohpayload nicht in Business-Rules.
- **HA-Auswirkung:** Beide Knoten können dasselbe Provider-Event sehen → Inbox garantiert Einmal-Verarbeitung.
- **Permissions:** — · **Audit Events:** —

### E11-04 · Call-Aggregat & Lebenszyklus (Mapping auf CALL_RINGING/ANSWERED/ENDED)
**Epic:** 11 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-call-aggregate
- **Ziel:** Ein Call-Aggregat führt den Zustand über normalisierte Events und erzeugt die fachlichen Domain-Events.
- **Fachlicher Hintergrund:** MASTER_PROMPT §3 (CALL_RINGING/ANSWERED/ENDED/DOCUMENTED), §8.4.
- **Scope:** Zustandsautomat (offered→ringing→connected→held/resumed→disconnected/failed), Mapping normalisierte→fachliche Events, stabile BBZ-Call-ID, Zuordnung Leitung/Arbeitsplatz.
- **Nicht im Scope:** Steuerkommandos (E11-06); Doku-Pflicht (E11-09/10).
- **Abhängigkeiten:** E11-03, E03-04-Muster.
- **Acceptance Criteria:** Jeder gültige Übergang → korrektes Domain-Event; unerwartete Provider-Sequenz → definierter Fehlerzustand, kein Absturz; Branch-Coverage hoch.
- **Tests:** Unit: Übergangsmatrix; „chaotische" Provider-Sequenzen.
- **Security-Auswirkung:** — · **HA-Auswirkung:** deterministisch. · **Permissions:** — · **Audit Events:** `CALL_RINGING` `CALL_ANSWERED` `CALL_ENDED`.

### E11-05 · `telephony_mock`-Provider vollständig implementieren
**Epic:** 11 · **Phase:** 5 · **Area:** integration, backend · **Branch:** feature/<nr>-telephony-mock-full
- **Ziel:** Der Mock erfüllt das Protocol komplett und simuliert realistische Szenarien für Dev/CI/E2E.
- **Fachlicher Hintergrund:** MASTER_PROMPT §7/§25 Phase 5 „mock provider"; heute nur Grundgerüst.
- **Scope:** Simulierbare Szenarien: eingehender Anruf (bekannt/unbekannt), mehrere wartende Anrufe, Annehmen/Auflegen/Halten/Transfer, DTMF, Provider OOS→IS, Reconnect/Replay.
- **Nicht im Scope:** Echte PBX (E13).
- **Abhängigkeiten:** E11-02, E11-03.
- **Acceptance Criteria:** Alle Protocol-Methoden funktionsfähig; Szenarien per API/Config auslösbar; deterministisch für Tests.
- **Tests:** Nutzung in E11-17 und E14/E15/E17-E2E.
- **Security-Auswirkung:** — · **HA-Auswirkung:** unterstützt Replay-Tests. · **Permissions:** — · **Audit Events:** —

### E11-06 · Call-Control-API (answer/dial/hangup/hold/resume/transfer)
**Epic:** 11 · **Phase:** 5 · **Area:** backend, api · **Branch:** feature/<nr>-call-control-api
- **Ziel:** Steuerkommandos als permission-geschützte, idempotente Endpoints.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.8/§15; Permission-Katalog `calls.*`.
- **Scope:** `POST /calls/{id}/answer|hangup|hold|resume|transfer`, `POST /calls/dial`; Command-Envelope; Übersetzung in Provider-Aufrufe über den aktiven Provider.
- **Nicht im Scope:** CUCM-CONTROL_LEADER (Epic 12); Doku-Guard (E11-10).
- **Abhängigkeiten:** E11-04, E02-08.
- **Acceptance Criteria:** Ohne Recht → 403; doppelter `answer`-Command → keine zweite Provider-Aktion; Transfer erfordert Zielangabe.
- **Tests:** API gegen Mock: Happy-Path je Kommando, Idempotenz, Rechteprüfung.
- **Security-Auswirkung:** `calls.*` scoped auf Arbeitsplatz/Leitung.
- **HA-Auswirkung:** Idempotenz kritisch (kein doppeltes „answer"); bei CUCM zusätzlich Leader-Gate (Epic 12).
- **Permissions:** `calls.answer` `calls.dial` `calls.hangup` `calls.hold` `calls.transfer`
- **Audit Events:** `CALL_CONTROL_ACTION` (Audit, Aktion + Ergebnis).

### E11-07 · Leitungsstatus-API + LINE_IN/OUT_OF_SERVICE
**Epic:** 11 · **Phase:** 5 · **Area:** backend, api · **Branch:** feature/<nr>-line-state
- **Ziel:** Verfügbare Leitungen und ihr Status sind abfragbar und im Stream.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.1 „verfügbare Leitungen"; §8.4.
- **Scope:** `GET /lines`, Statuspflege aus normalisierten Events, Domain-Events `LINE_IN_SERVICE`/`LINE_OUT_OF_SERVICE`.
- **Nicht im Scope:** Weytec-Monitor (Epic 19).
- **Abhängigkeiten:** E11-03.
- **Acceptance Criteria:** Leitungsausfall → sichtbar in `GET /lines` + Stream; `calls.view` erforderlich.
- **Tests:** Integration: Mock setzt Leitung OOS → API/Stream reflektieren.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `calls.view` · **Audit Events:** —

### E11-08 · Caller-Resolution (Rufnummer → Kontakt + Priorität)
**Epic:** 11 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-caller-resolution
- **Ziel:** Ein eingehender Anruf wird anhand der Rufnummer automatisch Kontakt und Priorität zugeordnet.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.9: „Eingehende Anrufe werden anhand Rufnummer automatisch Kontakt und Priorität zugeordnet."
- **Scope:** `resolve_caller`-Implementierung im Core (E.164-Normalisierung, Longest-Match gegen `contact_numbers`), Rückgabe Kontakt + Priorität + „unbekannt".
- **Nicht im Scope:** Kontaktverwaltung (Epic 14); technische Endpunkte (Epic 15).
- **Abhängigkeiten:** E14-04 (Matching-Service) — oder umgekehrt: dieses Issue liefert den Hook, Epic 14 die Daten. Reihenfolge: E14-01/04 zuerst.
- **Acceptance Criteria:** Bekannte Nummer → Kontakt+Priorität; unbekannte → als „unbekannt" markiert; Normalisierung robust (führende 0/+49/Durchwahl).
- **Tests:** Unit: Normalisierung/Match-Fälle; Integration mit Mock-Anruf.
- **Security-Auswirkung:** Rufnummern-Abgleich; kein Leak fremder Kontakte über Scope hinweg.
- **HA-Auswirkung:** Reine Leseauflösung.
- **Permissions:** `contacts.view` (implizit) · **Audit Events:** —

### E11-09 · Pflicht-Anrufdokumentation: Kategorien + Freitext
**Epic:** 11 · **Phase:** 5 · **Area:** backend, api · **Branch:** feature/<nr>-call-doc-model
- **Ziel:** Jeder angenommene Anruf kann während/nach dem Gespräch kategorisiert und mit Freitext dokumentiert werden.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.10: Kategorien Auskunftsersuchen / Technische Störung / Reinigungsmeldung Kunde / EVU & EVI Mitteilung / Anderes; optionaler Freitext.
- **Scope:** `PUT /calls/{id}/documentation` (category, free_text), Kategorie-Enum, Inline-Speichern während des Gesprächs, `CALL_DOCUMENTED` erst wenn Kategorie gesetzt.
- **Nicht im Scope:** Hangup-Guard (E11-10); UI (E11-15).
- **Abhängigkeiten:** E11-01, E11-04.
- **Acceptance Criteria:** Kategorie außerhalb des Enums → 422; Freitext optional; mehrfaches Speichern überschreibt (letzter Stand), auditiert.
- **Tests:** API: gültige/ungültige Kategorie; Inline-Update.
- **Security-Auswirkung:** `calls.document`; Freitext kann sensibel sein → Scope/Retention.
- **HA-Auswirkung:** Idempotent (letzter Stand gewinnt).
- **Permissions:** `calls.document`
- **Audit Events:** `CALL_DOCUMENTED` (Pflicht-Audit).

### E11-10 · Hangup-Guard: kein Abschluss ohne Kategorie (Pflicht-Popup-Flow)
**Epic:** 11 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-call-hangup-guard
- **Ziel:** Wird beim Auflegen keine Kategorie gesetzt, ist der Call erst nach Dokumentation „abgeschlossen"; der Server erzwingt das.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.10/§26.9: „Keine Anrufbeendigung ohne Pflichtkategorisierung."
- **Scope:** Call-Zustand `ended_pending_documentation`; `hangup` beendet die Verbindung, aber der Call bleibt „offen" bis Doku; Query „meine offenen Doku-Pflichten".
- **Nicht im Scope:** UI-Popup (E11-15).
- **Abhängigkeiten:** E11-06, E11-09.
- **Acceptance Criteria:** Auflegen ohne Kategorie → Call in `ended_pending_documentation`, erscheint in der Pflichtliste; nach Kategorie → `CALL_DOCUMENTED` + `CALL_ENDED` final; kein Bypass.
- **Tests:** Integration: Auflegen ohne Kategorie → Pflichtzustand; Doku nachziehen → final.
- **Security-Auswirkung:** Server-Enforcement (nicht nur UI).
- **HA-Auswirkung:** Zustand in DB; auf beiden Knoten sichtbar.
- **Permissions:** `calls.document` · **Audit Events:** `CALL_DOCUMENTED`.

### E11-11 · Call-History-API
**Epic:** 11 · **Phase:** 5 · **Area:** backend, api · **Branch:** feature/<nr>-call-history-api
- **Ziel:** Rufhistorie mit Kontakt-/Doku-Verknüpfung abfragbar.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.8 (Tab „Historie"); Permission `calls.view_history`.
- **Scope:** `GET /calls` (Filter: Zeitraum, Richtung, Nummer, Kategorie), Pagination, Scope-Filter.
- **Nicht im Scope:** CDR-Reconciliation (Epic 12).
- **Abhängigkeiten:** E11-01, E11-09.
- **Acceptance Criteria:** `calls.view_history` erforderlich; scope-gefiltert; deterministische Ordnung.
- **Tests:** API: Filter, Rechte, Pagination.
- **Security-Auswirkung:** Historie personenbeziehbar → strenge Rechte/Scope.
- **HA-Auswirkung:** Read-only. · **Permissions:** `calls.view_history` · **Audit Events:** —

### E11-12 · Mehrere wartende Anrufe + Prioritätssortierung (Backend)
**Epic:** 11 · **Phase:** 5 · **Area:** backend, api · **Branch:** feature/<nr>-call-queue
- **Ziel:** Der Server stellt die Warteschlange wartender Anrufe nach Priorität sortiert bereit.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.8/§13.9: „mehrere wartende Anrufe", „Sortierung nach Priorität".
- **Scope:** `GET /calls?state=ringing` mit Prioritäts-Sortierung (aus E11-08), Stream-Signal bei Änderung.
- **Nicht im Scope:** UI-Animation (E14-09).
- **Abhängigkeiten:** E11-04, E11-08.
- **Acceptance Criteria:** Reihenfolge hoch→niedrig, dann Wartezeit; Änderungen live.
- **Tests:** Integration: mehrere Mock-Anrufe unterschiedlicher Priorität → korrekte Reihenfolge.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `calls.view` · **Audit Events:** —

### E11-13 · Komm-Sidebar-UI: Keypad, wartende Anrufe, Steuerung, Dauer, Leitungsstatus
**Epic:** 11 · **Phase:** 5 · **Area:** frontend · **Branch:** feature/<nr>-ui-phone-panel
- **Ziel:** Der Telefon-Tab bietet Wählfeld, Anrufliste, Annehmen/Ablehnen/Auflegen, Gesprächsdauer, Leitungsstatus.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.8.
- **Scope:** Keypad, Liste wartender Anrufe (bekannt/unbekannt), Aktionsbuttons (E11-06), laufende Dauer, Leitungsanzeige (E11-07); alles tastaturbedienbar.
- **Nicht im Scope:** Telefonbuch (Epic 14); Doku-UI (E11-15).
- **Abhängigkeiten:** E11-06, E11-07, E11-12, E07-18.
- **Acceptance Criteria:** Eingehender Mock-Anruf erscheint sofort; Annehmen/Auflegen funktioniert; Dauer läuft korrekt; a11y grün.
- **Tests:** Playwright gegen Mock: incoming → answer → hangup.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `calls.view/answer/hangup/dial` · **Audit Events:** —

### E11-14 · Anrufdokumentations-UI (inline + Pflicht-Popup beim Auflegen)
**Epic:** 11 · **Phase:** 5 · **Area:** frontend · **Branch:** feature/<nr>-ui-call-doc
- **Ziel:** Kategorie/Freitext während des Gesprächs erfassbar; beim Auflegen ohne Kategorie erscheint ein blockierendes Pflicht-Popup.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.10.
- **Scope:** Inline-Doku-Formular im Gespräch-Tab, Pflicht-Popup (nicht schließbar ohne Kategorie), Anzeige „offene Doku-Pflichten" (E11-10).
- **Nicht im Scope:** Server-Guard (E11-10).
- **Abhängigkeiten:** E11-09, E11-10.
- **Acceptance Criteria:** Auflegen ohne Kategorie → Popup, Abschluss erst nach Auswahl; Popup tastaturbedienbar; offene Pflichten sichtbar.
- **Tests:** Playwright: incoming → answer → hangup ohne Kategorie → Popup → Kategorie → abgeschlossen.
- **Security-Auswirkung:** UI-Ergänzung zum Server-Enforcement.
- **HA-Auswirkung:** — · **Permissions:** `calls.document` · **Audit Events:** — (Server).

### E11-15 · Kurzwahl-Dialog („Kurzwahl öffnen"-Overlay)
**Epic:** 11 · **Phase:** 5 · **Area:** frontend · **Branch:** feature/<nr>-ui-quickdial
- **Ziel:** Kein permanentes Kurzwahlgitter; ein Button öffnet ein Dialog/Overlay mit den Kurzwahlkontakten.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.11.
- **Scope:** Button „Kurzwahl öffnen", Overlay mit Kurzwahlkontakten (aus Epic 14), Klick → `dial`.
- **Nicht im Scope:** Kurzwahl-Datenpflege (Epic 14).
- **Abhängigkeiten:** E11-13, E14-06.
- **Acceptance Criteria:** Kein Dauergitter im Layout; Overlay tastaturbedienbar; Wahl startet Anruf.
- **Tests:** Playwright: Overlay öffnen, Kontakt wählen.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `calls.dial` `contacts.view` · **Audit Events:** —

### E11-16 · Telefonie-E2E (§24)
**Epic:** 11 · **Phase:** 5 · **Area:** test · **Branch:** feature/<nr>-e2e-telephony
- **Ziel:** Der §24-Telefon-E2E-Ablauf ist automatisiert grün.
- **Fachlicher Hintergrund:** MASTER_PROMPT §24: incoming → Priorität erkennen → annehmen → Kategorie setzen → Freitext → auflegen → Audit prüfen.
- **Scope:** Playwright über Compose + `telephony_mock`, Assertions inkl. `CALL_DOCUMENTED`-Audit via API.
- **Nicht im Scope:** CUCM (Epic 12).
- **Abhängigkeiten:** E11-08, E11-13, E11-14.
- **Acceptance Criteria:** Alle 7 Schritte grün; Auflegen ohne Kategorie wird blockiert; Audit vorhanden.
- **Tests:** ebendieser E2E-Flow.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** div. · **Audit Events:** verifiziert.

---

# EPIC 12 · Cisco CUCM

**Milestone:** `12 Cisco CUCM` · **Phase:** 5 · **Ziel des Epics:** `telephony_cucm`
als eigener Provider + separater Java-JTAPI-Gateway-Dienst, CONTROL_LEADER-
Wahl, AXL/RisPort/UDS/CDR-Adapter, Integration-Health, Failure-Szenario-Tests.
**Keine produktive Anbindung ohne die §8.18-Kundendaten.** Quellen: MASTER_PROMPT
§8, `.ai/INTEGRATIONS_CUCM.md`, ADR-0002, ADR-0018.

### E12-01 · services/cucm-cti-gateway: Java-Scaffold, Dockerfile, Health-API
**Epic:** 12 · **Phase:** 5 · **Area:** integration, infra · **Branch:** feature/<nr>-cucm-gateway-scaffold
- **Ziel:** Ein separater Java-8-Dienst mit Build, Container, Health-API — ohne `jtapi.jar` im Repo.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.3; ADR-0002 §12: „Cisco proprietary JTAPI binaries are not committed."
- **Scope:** `services/cucm-cti-gateway/` (Maven/Gradle), Struktur `api/ jtapi/ state/ health/`, Dockerfile, `jtapi.jar` als externe versionsgebundene Abhängigkeit (Doku, Bereitstellung per Volume/Artifact-Store), interne REST/gRPC-API-Definition.
- **Nicht im Scope:** JTAPI-Verbindung (E12-02); Übersetzung (E12-03).
- **Abhängigkeiten:** E01-01 (ADR-0002 Baseline), E01-04 (Image-Pipeline erweitern).
- **Acceptance Criteria:** Build ohne `jtapi.jar` schlägt mit klarer Meldung fehl (Abhängigkeit dokumentiert); Health-API antwortet; gitleaks findet keine Cisco-Binärdaten.
- **Tests:** Build-CI (mock-Modus ohne jtapi); Health-Smoke.
- **Security-Auswirkung:** Keine Vendor-Binärdaten im öffentlichen Repo.
- **HA-Auswirkung:** Ein Gateway je Server (E12-08).
- **Permissions:** — · **Audit Events:** —

### E12-02 · JTAPI-Verbindung + CTI-Manager-Multi-Node-Failover
**Epic:** 12 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-cucm-jtapi-connect
- **Ziel:** Das Gateway verbindet sich per JTAPI und nutzt Ciscos redundanten CTI-Manager-Failover (mehrere Subscriber).
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.7; ADR-0002 §9.
- **Scope:** `cti_managers`-Liste (Config), Provider-Init, automatischer CTI-Failover, Status (primary/backup CTI, provider state, last reconnect, reconnect count).
- **Nicht im Scope:** Steuerkommandos (E12-04).
- **Abhängigkeiten:** E12-01.
- **Acceptance Criteria:** Ausfall eines CTI-Managers → Gateway wechselt automatisch, BBZ-Telefonie nicht dauerhaft unterbrochen; Status im Gateway-Health sichtbar.
- **Tests:** Gegen JTAPI-Simulator/Mock: CTI-Node-Ausfall → Failover; Provider OOS→IS.
- **Security-Auswirkung:** Technischer Account `bbz-cucm-cti` mit Minimalrechten (E12-17).
- **HA-Auswirkung:** CTI-Redundanz innerhalb der BBZ-Redundanz.
- **Permissions:** — · **Audit Events:** `CTI_PROVIDER_STATE_CHANGED` (normalisiert).

### E12-03 · JTAPI-Event-Übersetzung → normalisierte BBZ-Telefonie-Events
**Epic:** 12 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-cucm-event-translation
- **Ziel:** Cisco-JTAPI-Objekte werden im Gateway in das normalisierte BBZ-Modell übersetzt; kein Cisco-Typ verlässt das Gateway.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.3/§8.4: `CallCtlConnOfferedEv` → `CALL_OFFERED` usw.
- **Scope:** Mapping-Tabelle JTAPI-Event → normalisiertes Event + Pflichtfelder (`provider`, `provider_cluster_id`, `source_call_id`, `line_id`, `device_id`, Nummern, Zeiten, `raw_event_type`, `correlation_id`).
- **Nicht im Scope:** BBZ-Core-Verarbeitung (E11-03).
- **Abhängigkeiten:** E12-02, E11-03.
- **Acceptance Criteria:** Für jedes unterstützte JTAPI-Event existiert ein Mapping + Test; Ausgabe validiert gegen `telephony_event.v1.json`; keine Cisco-Klasse im Output-Schema.
- **Tests:** Unit im Gateway: je JTAPI-Event ein Mapping-Test; Contract-Test gegen BBZ-Schema.
- **Security-Auswirkung:** Isolation der Vendor-Details.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** normalisierte Telefonie-Events.

### E12-04 · Call-Control-Kommandos über JTAPI (answer/dial/hangup/hold/resume/transfer/conference)
**Epic:** 12 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-cucm-call-control
- **Ziel:** Das Gateway führt Steuerkommandos gegen CUCM aus — nur wenn es CONTROL_LEADER ist.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.6: „Nur der CONTROL_LEADER darf steuernde Commands ausführen."
- **Scope:** Umsetzung der Provider-Steuermethoden auf JTAPI, Leader-Gate (E12-07), Idempotenz/Retry-Semantik (Cisco-CallID-basiert).
- **Nicht im Scope:** DTMF (E12-05); Reconcile (E12-09).
- **Abhängigkeiten:** E12-02, E12-07.
- **Acceptance Criteria:** Kommando am Nicht-Leader → abgelehnt/weitergereicht; Retry eines `answer` erzeugt keine zweite Annahme; Transfer/Conference nur wenn Capability freigegeben.
- **Tests:** JTAPI-Sim: je Kommando Happy-Path; Retry-Idempotenz; Nicht-Leader-Ablehnung.
- **Security-Auswirkung:** Least-Privilege-CTI-Account; nur BBZ-relevante Geräte.
- **HA-Auswirkung:** Kernpunkt „keine doppelten Cisco-Steuerbefehle".
- **Permissions:** `calls.*` (im BBZ-Core geprüft) · **Audit Events:** `CALL_CONTROL_ACTION`.

### E12-05 · `send_dtmf`-Capability auf MediaTerminalConnection
**Epic:** 12 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-cucm-dtmf
- **Ziel:** Der CUCM-Provider bietet `send_dtmf()`, wenn der kontrollierte Call/Media dies unterstützt (Grundlage für Siedle).
- **Fachlicher Hintergrund:** MASTER_PROMPT §30; `.ai/INTEGRATIONS_SIEDLE.md`: „JTAPI supports DTMF generation on a MediaTerminalConnection."
- **Scope:** DTMF-Erzeugung über JTAPI, Capability-Flag im Manifest, Fehlerfall „DTMF nicht verfügbar".
- **Nicht im Scope:** Tür-Öffnungs-Flow (Epic 17).
- **Abhängigkeiten:** E12-04.
- **Acceptance Criteria:** DTMF wird genau einmal gesendet; fehlende Media-/DTMF-Fähigkeit → klarer Fehler, kein stiller Retry; Klartext-Codes nie geloggt.
- **Tests:** JTAPI-Sim: DTMF-Sequenz; „nicht unterstützt"-Fall.
- **Security-Auswirkung:** DTMF-Profile sind Secrets (Epic 17) — Gateway loggt nur „Profil-ID gesendet".
- **HA-Auswirkung:** Exactly-once über Outbox/Idempotenz-Key (Epic 17).
- **Permissions:** `door.open` (im Core) · **Audit Events:** — (Audit im Core, ohne Code).

### E12-06 · Stabile `source_call_id` aus CiscoCallID (CallManagerID + GlobalCallID)
**Epic:** 12 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-cucm-callid
- **Ziel:** Eine stabile, deduplizierbare `source_call_id` aus den JTAPI-CiscoCallID-Werten.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.5: „Keine Identifikation nur anhand Nummer/Startzeit/UI-ID."
- **Scope:** Bildung `source_call_id` = f(CallManagerID, GlobalCallID); Stabilität über Call-Legs; Doku des Verfahrens.
- **Nicht im Scope:** BBZ-eigene Call-ID (E11-01, bleibt unabhängig).
- **Abhängigkeiten:** E12-03.
- **Acceptance Criteria:** Gleicher Anruf über mehrere Events → gleiche `source_call_id`; verschiedene Anrufe → verschieden; Dedupe in E11-03 greift.
- **Tests:** Unit: ID-Bildung; Leg-Übergänge; Kollisionstest.
- **Security-Auswirkung:** — · **HA-Auswirkung:** Grundlage exactly-once bei Telefonie. · **Permissions:** — · **Audit Events:** —

### E12-07 · CONTROL_LEADER-Wahl (etcd-Lease, kurze TTL)
**Epic:** 12 · **Phase:** 5 · **Area:** integration, infra · **Branch:** feature/<nr>-cucm-control-leader
- **Ziel:** Genau ein logischer CONTROL_LEADER je CUCM-Cluster, gewählt über die geteilte Leader-Election-Lib.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.6; ADR-0002 §8; ADR-0018.
- **Scope:** Nutzung von E04-08 mit Key `/bbz/leader/cucm-control-<cluster>`, kurze TTL + Keepalive, Leader/Standby-Anzeige, sauberer Verzicht bei Verbindungsverlust.
- **Nicht im Scope:** Reconcile-Ablauf (E12-09).
- **Abhängigkeiten:** E04-08, E12-02.
- **Acceptance Criteria:** Zwei Gateways laufen, nur einer steuert; Leader-Ausfall → Standby wird Leader < 2×TTL; im Umschaltfenster keine steuernden Kommandos.
- **Tests:** Integration mit echtem etcd: Leader-Kill → Failover; kein Doppelkommando.
- **Security-Auswirkung:** etcd-ACL für `/bbz`-Prefix.
- **HA-Auswirkung:** Verhindert doppelte Cisco-Steuerbefehle bei Active/Active.
- **Permissions:** `system.cluster.view` · **Audit Events:** `CUCM_CONTROL_LEADER_CHANGED` (Audit).

### E12-08 · Standby-Gateway: Warm-State, Health, keine steuernden Kommandos
**Epic:** 12 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-cucm-standby
- **Ziel:** Beide Gateways halten eine CUCM-Verbindung; der Standby beobachtet nur.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.6: „Standby hält Provider-/Call-State warm, führt keine steuernden Commands aus, publiziert keine doppelten Transitions."
- **Scope:** Standby-Modus: Provider-/Call-/Line-State mitführen, Health, Unterdrückung doppelter fachlicher Transitions (der Leader publiziert).
- **Nicht im Scope:** Leaderwahl (E12-07).
- **Abhängigkeiten:** E12-07.
- **Acceptance Criteria:** Standby erzeugt keine Steuer-Kommandos und keine doppelten `CALL_*`-Transitions im Core; nach Leaderwechsel sofort steuerbereit (nach Reconcile).
- **Tests:** Integration: beide Gateways verbunden → nur eine Transition-Quelle im Core.
- **Security-Auswirkung:** — · **HA-Auswirkung:** schneller Failover ohne Doppelevents. · **Permissions:** — · **Audit Events:** —

### E12-09 · Leaderwechsel-Reconciliation + TELEPHONY_RECONCILED
**Epic:** 12 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-cucm-reconcile
- **Ziel:** Nach Leaderwechsel gleicht der neue Leader Calls/Lines ab, bevor er Steuerkommandos freigibt.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.6 (Schritte 1–5): neuen Lease → Provider-State prüfen → Calls/Lines reconciliieren → `TELEPHONY_RECONCILED` → dann Steuerung.
- **Scope:** `reconcile()`-Implementierung, `get_active_calls`/`list_lines`-Abgleich, `TELEPHONY_RECONCILED`-Domain-Event, Freigabe-Gate für Steuerkommandos.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E12-04, E12-07.
- **Acceptance Criteria:** Steuerkommandos vor abgeschlossenem Reconcile → abgelehnt; `TELEPHONY_RECONCILED` genau einmal je Wechsel; aktive Calls bleiben nach Serverwechsel bedienbar.
- **Tests:** §8.15-Fall „aktiver Call während BBZ-Serverwechsel"; „Reconnect mit bestehenden Calls".
- **Security-Auswirkung:** — · **HA-Auswirkung:** verhindert inkonsistente Steuerung nach Failover. · **Permissions:** — · **Audit Events:** `TELEPHONY_RECONCILED`.

### E12-10 · AXL-Adapter (Inventar, read-only, rate-limited, WSDL-pinned)
**Epic:** 12 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-cucm-axl
- **Ziel:** AXL nur für Konfigurations-/Inventarabfragen (Geräte/Lines/Route Points/DNs), nie für Live-Call-State.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.2 AXL; ADR-0002 §3.
- **Scope:** SOAP/HTTPS-Client, versionsgebundenes WSDL, Rate-Limiting, Caching, technischer Account `bbz-cucm-axl` (`Standard AXL API Access`).
- **Nicht im Scope:** Automatisierte Provisionierung (nur nach expliziter Freigabe, separates Issue).
- **Abhängigkeiten:** E12-01.
- **Acceptance Criteria:** Keine hochfrequenten AXL-Abfragen (Rate-Limit erzwungen); Ergebnisse gecacht; AXL-Ausfall bricht Live-Telefonie nicht.
- **Tests:** Gegen AXL-Mock/aufgezeichnete WSDL-Responses; Rate-Limit-Test; „AXL down, Telefonie ok" (§8.15).
- **Security-Auswirkung:** Eigener Least-Privilege-Account; TLS-Verify an.
- **HA-Auswirkung:** Von Live-Pfad entkoppelt.
- **Permissions:** `integrations.diagnostics` · **Audit Events:** —

### E12-11 · RisPort70-Adapter (Registrierungs-/Gerätestatus, Health only)
**Epic:** 12 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-cucm-risport
- **Ziel:** RisPort70 liefert technische Statusinfos (Phone registriert, CTI-Device-Status, IP, Modell, Registration Node).
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.2 RisPort70; „Nicht als Call-Control-Schnittstelle."
- **Scope:** RisPort-Client mit begrenztem Polling / StateInfo-Inkrement, Mapping in Integration-Health, Account `bbz-cucm-serviceability`.
- **Nicht im Scope:** Call Control.
- **Abhängigkeiten:** E12-01.
- **Acceptance Criteria:** Polling begrenzt; Statusänderungen erscheinen in der Integration-Health (E12-15); kein Call-Control-Pfad.
- **Tests:** Gegen RisPort-Mock; Polling-Limit.
- **Security-Auswirkung:** Eigener Serviceability-Account, minimale Rechte.
- **HA-Auswirkung:** — · **Permissions:** `integrations.diagnostics` · **Audit Events:** —

### E12-12 · UDS-Adapter (optional, Directory-Anreicherung)
**Epic:** 12 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-cucm-uds
- **Ziel:** Optionale Directory-Suche zur Kontaktanreicherung; das BBZ-Telefonbuch bleibt eigenes Domainobjekt.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.2 UDS.
- **Scope:** UDS-Client (Directory Search, Benutzer/Geräte/Extensions), Anreicherungs-Hook für Kontakte (opt-in), klare Kennzeichnung „aus UDS".
- **Nicht im Scope:** Zwangs-Synchronisation; Ersatz des BBZ-Telefonbuchs.
- **Abhängigkeiten:** E12-01, E14-02.
- **Acceptance Criteria:** UDS-Daten überschreiben keine gepflegten BBZ-Kontaktfelder ohne explizite Aktion; Feature abschaltbar.
- **Tests:** Gegen UDS-Mock; „BBZ-Feld bleibt erhalten".
- **Security-Auswirkung:** Personenbezogene Directory-Daten — Scope/Zweckbindung.
- **HA-Auswirkung:** — · **Permissions:** `contacts.edit` (für Anreicherung) · **Audit Events:** `CONTACT_ENRICHED_FROM_UDS`.

### E12-13 · CDRonDemand-Adapter (optional, Nachbearbeitung)
**Epic:** 12 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-cucm-cdr
- **Ziel:** CDR/CMR als sekundäre Quelle für Nachbearbeitung/technische Reconciliation.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.2 CDRonDemand: „NICHT die Quelle für Live-Call-Control."
- **Scope:** CDRonDemand-Client, Abgleich Rufhistorie/Metadaten, Kennzeichnung als Zweitquelle.
- **Nicht im Scope:** Live-Pfad.
- **Abhängigkeiten:** E12-01, E11-11.
- **Acceptance Criteria:** CDR-Daten nur in Nachbearbeitungs-/Reconciliation-Views; kein Einfluss auf Live-Call-State.
- **Tests:** Gegen CDR-Mock; Reconciliation-Report.
- **Security-Auswirkung:** Call-Metadaten personenbeziehbar.
- **HA-Auswirkung:** — · **Permissions:** `calls.view_history` `integrations.diagnostics` · **Audit Events:** —

### E12-14 · `telephony_cucm`-Manifest, Capabilities, Config-Schema
**Epic:** 12 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-cucm-manifest
- **Ziel:** Vollständiges Integrations-Manifest + Config-Schema für CUCM.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.13; SDK-Manifest-Schema.
- **Scope:** `integrations/telephony_cucm/manifest.json` (id/name/domain/adapter/capabilities), `config_schema.json` (cti_managers, security mode, account-Refs, controlled devices/route points, Modus A/B), Validierung gegen SDK-Schema.
- **Nicht im Scope:** Reale Werte (Kundendaten, §8.18).
- **Abhängigkeiten:** E12-01, Epic 01 (SDK-Manifest-Schema).
- **Acceptance Criteria:** Manifest validiert; Capabilities spiegeln tatsächliche Gateway-Fähigkeiten; Config-Schema deckt Modus A und B ab.
- **Tests:** Schema-Validierung; Manifest-Discovery im Core.
- **Security-Auswirkung:** Account-Referenzen, keine Klartext-Creds.
- **HA-Auswirkung:** — · **Permissions:** `integrations.view/configure` · **Audit Events:** —

### E12-15 · Integration-Health-API/UI für CUCM
**Epic:** 12 · **Phase:** 5 · **Area:** integration, backend, frontend · **Branch:** feature/<nr>-cucm-health
- **Ziel:** Admin sieht CUCM-Version, JTAPI-Version, CTI-Provider-State, aktiven CTI-Manager, CONTROL_LEADER, Standby, AXL/RisPort-Status, letzte Reconciliation, aktive Calls, Fehler seit letztem Healthy.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.14.
- **Scope:** Health-Aggregation im Gateway + Core-Endpoint `GET /integrations/telephony_cucm/health`, Admin-UI-Kachel.
- **Nicht im Scope:** Generisches Observability-Dashboard (Epic 22).
- **Abhängigkeiten:** E12-02, E12-07, E12-09, E12-10, E12-11.
- **Acceptance Criteria:** Alle §8.14-Felder vorhanden und korrekt unter simulierten Störungen; CUCM-Version wird beim Onboarding erfasst und gespeichert.
- **Tests:** Integration: Störungen (CTI-Ausfall, AXL down) spiegeln sich korrekt.
- **Security-Auswirkung:** `integrations.diagnostics`; keine Secrets im Body.
- **HA-Auswirkung:** Beobachtbarkeit des Telefonie-HA-Zustands.
- **Permissions:** `integrations.view` `integrations.diagnostics` · **Audit Events:** —

### E12-16 · Secure CTI / TLS (Truststore als Secret, Zertifikatsvalidierung)
**Epic:** 12 · **Phase:** 5 · **Area:** integration, security · **Branch:** feature/<nr>-cucm-secure-cti
- **Ziel:** Secure CTI/TLS wird unterstützt; kein Verify-Disable in Produktion.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.11: `Standard CTI Secure Connection`, interne PKI/Truststore, Truststore als Secret/Volume.
- **Scope:** TLS-Konfiguration im Gateway, Truststore-Bereitstellung als Secret, Zertifikatsvalidierung erzwingen (Prod-Guard), Doku.
- **Nicht im Scope:** PKI-Aufbau (Betrieb).
- **Abhängigkeiten:** E12-02, E01-03 (Secret-Store).
- **Acceptance Criteria:** Prod-Profil verweigert Start bei deaktivierter Zertifikatsvalidierung; Truststore nie im Image/Repo.
- **Tests:** Gateway-Start mit/ohne gültigen Truststore; „verify off" in Prod → Fehler.
- **Security-Auswirkung:** Verschlüsselte CTI-Verbindung; kein MITM.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E12-17 · CUCM-Application-Users & Least Privilege (Doku + Config)
**Epic:** 12 · **Phase:** 5 · **Area:** integration, security, documentation · **Branch:** feature/<nr>-cucm-app-users
- **Ziel:** Getrennte technische Konten (`bbz-cucm-cti`, `-axl`, `-serviceability`) mit dokumentierten Minimalrechten.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.10; ADR-0002 §8.10: keine gemeinsamen Superuser-Credentials.
- **Scope:** `.ai/INTEGRATIONS_CUCM.md`/`docs/` erweitern: je Konto benötigte CUCM-Rollen, Begründung; Config referenziert Konten per Secret-ID.
- **Nicht im Scope:** Anlegen der Konten in CUCM (Kunde).
- **Abhängigkeiten:** E12-14.
- **Acceptance Criteria:** Doku nennt je Konto die minimale Rollenmenge; `Allow Control of All Devices` nur mit dokumentierter Begründung; keine geteilten Creds.
- **Tests:** Doc-Review; Config-Schema erzwingt getrennte Account-Refs.
- **Security-Auswirkung:** Least Privilege für die Telefonie-Integration.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E12-18 · Gateway-Mock-Modus (ohne echtes CUCM) für CI
**Epic:** 12 · **Phase:** 5 · **Area:** integration, test · **Branch:** feature/<nr>-cucm-mock-mode
- **Ziel:** Das Gateway läuft ohne CUCM/`jtapi.jar` in einem deterministischen Mock-Modus.
- **Fachlicher Hintergrund:** MASTER_PROMPT §25 Phase 5: „Cisco CUCM JTAPI gateway + mock mode".
- **Scope:** Mock-JTAPI-Schicht, konfigurierbare Szenarien (offered/ringing/answered/…; CTI-Failover; provider OOS→IS), CI-Job.
- **Nicht im Scope:** Reale CUCM-Tests (Kunde/§8.18).
- **Abhängigkeiten:** E12-01, E12-03.
- **Acceptance Criteria:** CI baut + testet das Gateway ohne Vendor-Binärdaten; Szenarien reproduzierbar.
- **Tests:** Gateway-Unit/Integration im Mock-Modus.
- **Security-Auswirkung:** — · **HA-Auswirkung:** ermöglicht E12-19. · **Permissions:** — · **Audit Events:** —

### E12-19 · CUCM-Failure-Szenario-Tests (§8.15)
**Epic:** 12 · **Phase:** 5 · **Area:** integration, test · **Branch:** feature/<nr>-cucm-failure-tests
- **Ziel:** Alle §8.15-Szenarien laufen als automatisierte Tests (im Mock-Modus + etcd).
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.15 (Liste).
- **Scope:** CTI-Manager-1-Ausfall→2 übernimmt; CONTROL_LEADER SRV01 down→SRV02 Lease; aktiver Call während Serverwechsel; Netzunterbrechung CUCM; Provider OOS→IS; doppelte Commands; `answer`-Retry; Reconnect mit bestehenden Calls; Publisher weg/CTI-Subscriber da; AXL unavailable ohne Live-Ausfall.
- **Nicht im Scope:** Reale CUCM-Version-Validierung (§8.18).
- **Abhängigkeiten:** E12-07, E12-09, E12-18.
- **Acceptance Criteria:** Jedes Szenario ein benannter grüner Test; kein Szenario erzeugt doppelte Steuerkommandos oder doppelte Core-Transitions.
- **Tests:** ebendiese Szenarien (nightly).
- **Security-Auswirkung:** — · **HA-Auswirkung:** Nachweis der Telefonie-HA. · **Permissions:** — · **Audit Events:** —

### E12-20 · Blocker-Doku: keine Produktivanbindung ohne §8.18-Daten
**Epic:** 12 · **Phase:** 5 · **Area:** documentation · **Branch:** docs/<nr>-cucm-pending-info
- **Ziel:** Ein klarer, referenzierbarer Blocker, der Produktiv-Wiring bis zur Bereitstellung der Kundendaten verhindert.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.18/§26.10: keine erfundenen CUCM-Details.
- **Scope:** `docs/` Blocker-Seite mit Checkliste (CUCM-Version/SU, Cluster-Topologie, CTI-Nodes, DNs, Rufnummernkonzept, CSS/Partitions, Modus A/B, Security Mode, Account-Freigaben, Zertifikatskette); Verweis aus `.ai/CURRENT_STATE.md` „Open external dependencies".
- **Nicht im Scope:** — .
- **Abhängigkeiten:** —
- **Acceptance Criteria:** Checkliste vollständig; Prod-Config-Profil trägt einen expliziten „requires §8.18 sign-off"-Marker.
- **Tests:** Doc-Review.
- **Security-Auswirkung:** Verhindert Fehlannahmen gegen Produktiv-CUCM.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

---

# EPIC 13 · SIP Provider

**Milestone:** `13 SIP Provider` · **Phase:** 5 · **Ziel des Epics:**
Herstellerneutrale SIP-Integration, unabhängig von Cisco-JTAPI — für einfache
Trunks, alternative PBX, Lab/Test, Migration/Fallback. Quellen: MASTER_PROMPT
§8.17, ADR-0002 §11.

### E13-01 · `telephony_sip`-Scaffold + Manifest (unabhängig von CUCM)
**Epic:** 13 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-sip-scaffold
- **Ziel:** Integrations-Grundgerüst + Manifest, das keinerlei CUCM-/JTAPI-Abhängigkeit hat.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.17: „darf NICHT von Cisco-JTAPI abhängen."
- **Scope:** `integrations/telephony_sip/` (manifest, config_schema, adapter-Stub), Capability-Modell, import-linter-Contract „telephony_sip ↛ telephony_cucm".
- **Nicht im Scope:** SIP-Stack (E13-02).
- **Abhängigkeiten:** E11-02.
- **Acceptance Criteria:** Manifest validiert; Contract-Test verhindert CUCM-Import; Provider im Core registrierbar.
- **Tests:** import-linter; Manifest-Schema.
- **Security-Auswirkung:** — · **HA-Auswirkung:** eigenständiger Provider. · **Permissions:** `integrations.view/configure` · **Audit Events:** —

### E13-02 · SIP/CTI-Gateway-Option (Asterisk oder FreeSWITCH) — Entscheidung + Minimal-Deployment
**Epic:** 13 · **Phase:** 5 · **Area:** integration, infra · **Branch:** feature/<nr>-sip-gateway-choice
- **Ziel:** Entscheidung für einen optionalen SIP/CTI-Gateway + minimales Deployment für Lab/Test.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.17: „Asterisk oder FreeSWITCH als optionaler SIP/CTI Gateway."
- **Scope:** ADR-0023 (Asterisk vs. FreeSWITCH, Begründung), Container-Deployment für Test, ARI/ESL-Anbindungspunkt.
- **Nicht im Scope:** Produktive SIP-Trunks (Kunde).
- **Abhängigkeiten:** E13-01.
- **Acceptance Criteria:** ADR-0023 `Accepted`; Test-Gateway startet in Compose.
- **Tests:** Compose-Smoke.
- **Security-Auswirkung:** Trunk-Creds als Secret.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E13-03 · SIP-Adapter → normalisiertes Provider-Interface
**Epic:** 13 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-sip-adapter
- **Ziel:** Der SIP-Adapter erfüllt das Telephony-Provider-Protocol; der Core spricht nur das normalisierte Interface.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.17: „Core spricht immer das normalisierte Telephony Provider Interface."
- **Scope:** Anbindung an das gewählte Gateway (ARI/ESL), Mapping SIP-Ereignisse → normalisierte Events, `initialize/health/subscribe_call_events/get_active_calls`.
- **Nicht im Scope:** Call-Control (E13-05).
- **Abhängigkeiten:** E13-02, E11-03.
- **Acceptance Criteria:** Registrierung + eingehendes Gespräch erzeugen normalisierte Events (validiert gegen Schema); Health korrekt.
- **Tests:** Integration gegen Test-Gateway.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** normalisierte Telefonie-Events.

### E13-04 · Registrierung + Call-Events → normalisierte Events
**Epic:** 13 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-sip-events
- **Ziel:** Vollständige Abdeckung der Lebenszyklus-Events (offered→disconnected, line in/out of service, device reg/unreg).
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.4.
- **Scope:** Event-Mapping für alle relevanten SIP-Zustände; Dedupe-Key aus SIP Call-ID.
- **Nicht im Scope:** DTMF (E13-06).
- **Abhängigkeiten:** E13-03.
- **Acceptance Criteria:** Alle Lebenszyklus-Events abgedeckt + getestet; stabile `source_call_id` aus SIP Call-ID.
- **Tests:** Integration: kompletter Anrufzyklus.
- **Security-Auswirkung:** — · **HA-Auswirkung:** Dedupe wie Epic 11. · **Permissions:** — · **Audit Events:** —

### E13-05 · Call-Control über SIP (dial/answer/hangup/hold/transfer)
**Epic:** 13 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-sip-call-control
- **Ziel:** Steuerkommandos über das SIP-Gateway.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.12.
- **Scope:** Umsetzung der Provider-Steuermethoden über ARI/ESL, Idempotenz über SIP-Call-ID.
- **Nicht im Scope:** CONTROL_LEADER (nur CUCM braucht das; SIP-Gateway-Redundanz separat, falls nötig).
- **Abhängigkeiten:** E13-04.
- **Acceptance Criteria:** Je Kommando Happy-Path + Retry-Idempotenz gegen das Test-Gateway.
- **Tests:** Integration.
- **Security-Auswirkung:** — · **HA-Auswirkung:** Idempotenz. · **Permissions:** `calls.*` (im Core) · **Audit Events:** `CALL_CONTROL_ACTION`.

### E13-06 · DTMF (RFC2833/INFO) → `send_dtmf`-Capability
**Epic:** 13 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-sip-dtmf
- **Ziel:** Der SIP-Provider bietet `send_dtmf()` (für Siedle als Alternative zu CUCM).
- **Fachlicher Hintergrund:** MASTER_PROMPT §30 (Siedle über Telefonie/DTMF); §8.17 Migration/Fallback.
- **Scope:** DTMF-Erzeugung über das Gateway, Capability-Flag, Fehlerbehandlung, kein Klartext-Logging der Codes.
- **Nicht im Scope:** Tür-Flow (Epic 17).
- **Abhängigkeiten:** E13-05.
- **Acceptance Criteria:** DTMF genau einmal; „nicht unterstützt" sauber; Codes nie geloggt.
- **Tests:** Integration: DTMF-Sequenz gegen Test-Gateway.
- **Security-Auswirkung:** DTMF-Profile = Secrets (Epic 17).
- **HA-Auswirkung:** Exactly-once über Outbox (Epic 17).
- **Permissions:** `door.open` (im Core) · **Audit Events:** —

### E13-07 · SIP-Config-Schema + Secrets
**Epic:** 13 · **Phase:** 5 · **Area:** integration, security · **Branch:** feature/<nr>-sip-config
- **Ziel:** Vollständiges Config-Schema für Trunks/Registrierungen mit Secret-Referenzen.
- **Fachlicher Hintergrund:** ADR-0015.
- **Scope:** `config_schema.json` (Trunk-Hosts, Auth, Codecs, DID-Zuordnung), Secret-Referenzen statt Klartext, Validierung.
- **Nicht im Scope:** Reale Trunk-Daten.
- **Abhängigkeiten:** E13-01, E01-03.
- **Acceptance Criteria:** Schema validiert; keine Klartext-Creds möglich (Schema erzwingt Ref).
- **Tests:** Schema-Validierung.
- **Security-Auswirkung:** Trunk-Creds geschützt.
- **HA-Auswirkung:** — · **Permissions:** `integrations.configure` · **Audit Events:** `INTEGRATION_CONFIGURED`.

### E13-08 · SIP-Integrationstests gegen containerisierte Test-PBX
**Epic:** 13 · **Phase:** 5 · **Area:** integration, test · **Branch:** feature/<nr>-sip-integration-tests
- **Ziel:** Automatisierte Tests des SIP-Providers gegen eine Test-PBX in CI.
- **Fachlicher Hintergrund:** MASTER_PROMPT §8.17 (Lab/Test); `.ai/TESTING.md`.
- **Scope:** Compose-Test-PBX + SIPp-Skripte, Szenarien (incoming/outgoing/hold/transfer/DTMF/Registrierungsverlust).
- **Nicht im Scope:** Last-/Performancetests.
- **Abhängigkeiten:** E13-03..06.
- **Acceptance Criteria:** Alle Szenarien grün in CI (nightly); Registrierungsverlust → Health degradiert, Recovery automatisch.
- **Tests:** ebendiese Szenarien.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

---

# EPIC 14 · Contacts / Call Priorities

**Milestone:** `14 Contacts / Call Priorities` · **Phase:** 6 · **Ziel des Epics:**
BBZ-eigenes Telefonbuch (Kontakte, Nummern, Prioritäten), automatische
Zuordnung eingehender Anrufe, Prioritäts-Visualisierung blau/orange/rot.
Quellen: MASTER_PROMPT §13.9/§13.10/§14.

### E14-01 · DB-Schema: contacts, contact_numbers, contact_priorities
**Epic:** 14 · **Phase:** 6 · **Area:** db · **Branch:** feature/<nr>-schema-contacts
- **Ziel:** Migration für das Telefonbuch-Datenmodell.
- **Fachlicher Hintergrund:** MASTER_PROMPT §14; §13.9 Prioritäten niedrig/mittel/hoch.
- **Scope:** `contacts` (id, name, org, notes, quick_dial bool, bbz_scope), `contact_numbers` (contact_id, e164, label, primary bool), `contact_priorities` (contact_id, priority `low|medium|high`, set_by, set_at).
- **Nicht im Scope:** Technische Endpunkte (Epic 15).
- **Abhängigkeiten:** E02-01.
- **Acceptance Criteria:** Migration up/down/up; `e164` normiert gespeichert; unique(contact_id, e164).
- **Tests:** Migration; Constraint-Tests.
- **Security-Auswirkung:** Personenbezogene Daten → Scope/Retention.
- **HA-Auswirkung:** expand-only. · **Permissions:** — · **Audit Events:** —

### E14-02 · Kontakte-CRUD-API
**Epic:** 14 · **Phase:** 6 · **Area:** backend, api · **Branch:** feature/<nr>-contacts-crud
- **Ziel:** Kontakte anlegen/bearbeiten/suchen/löschen per API.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.9; Permission-Katalog `contacts.*`.
- **Scope:** CRUD `/api/v1/contacts`, Suche (Name/Nummer/Org), Nummern-Unterressource, Soft-Delete, Command-Envelope.
- **Nicht im Scope:** Prioritätszuweisung (E14-03); UI (E14-07).
- **Abhängigkeiten:** E14-01, E02-08.
- **Acceptance Criteria:** `contacts.create/edit/delete` erforderlich; Suche performant (Index); Löschung soft; Idempotenz.
- **Tests:** API-CRUD, Suche, Rechte, Idempotenz.
- **Security-Auswirkung:** Scope-gefilterte Sicht; Audit von Änderungen.
- **HA-Auswirkung:** Idempotent. · **Permissions:** `contacts.view/create/edit/delete`
- **Audit Events:** `CONTACT_CREATED` `CONTACT_UPDATED` `CONTACT_DELETED`.

### E14-03 · Prioritätszuweisung + CONTACT_PRIORITY_CHANGED
**Epic:** 14 · **Phase:** 6 · **Area:** backend, api · **Branch:** feature/<nr>-contact-priority
- **Ziel:** Einem Kontakt eine Priorität (niedrig/mittel/hoch) zuweisen; Änderung ist ein auditiertes Domain-Event.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.9; `docs/domain/event-catalog.md` `CONTACT_PRIORITY_CHANGED`.
- **Scope:** `PUT /contacts/{id}/priority`, `contacts.assign_priority`, `CONTACT_PRIORITY_CHANGED` mit vorher/nachher.
- **Nicht im Scope:** Visualisierung (E14-08).
- **Abhängigkeiten:** E14-02.
- **Acceptance Criteria:** Ungültige Priorität → 422; Änderung erzeugt genau ein Event + Audit; Idempotenz (gleiche Priorität → No-Op ohne Event).
- **Tests:** API: Zuweisung, No-Op, Rechte.
- **Security-Auswirkung:** `contacts.assign_priority`.
- **HA-Auswirkung:** Idempotent. · **Permissions:** `contacts.assign_priority`
- **Audit Events:** `CONTACT_PRIORITY_CHANGED`.

### E14-04 · Nummer→Kontakt+Priorität-Matching-Service
**Epic:** 14 · **Phase:** 6 · **Area:** backend · **Branch:** feature/<nr>-number-matching
- **Ziel:** Ein Service normalisiert eine Rufnummer und liefert Kontakt + Priorität (oder „unbekannt").
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.9: automatische Zuordnung eingehender Anrufe.
- **Scope:** E.164-Normalisierung (nationale Präfixe, Durchwahlen), Longest-Suffix-Match gegen `contact_numbers`, Caching.
- **Nicht im Scope:** Technische Endpunkte (Epic 15 nutzt eigenen Matcher).
- **Abhängigkeiten:** E14-01.
- **Acceptance Criteria:** Robustes Matching (0.../+49.../interne Durchwahl); eindeutiges Ergebnis oder „unbekannt"; deterministisch.
- **Tests:** Unit-Matrix mit realistischen Nummernvarianten.
- **Security-Auswirkung:** Kein Cross-Scope-Leak.
- **HA-Auswirkung:** Reine Auflösung. · **Permissions:** — · **Audit Events:** —

### E14-05 · CONTACT_CREATED-Event + Audit-Verdrahtung
**Epic:** 14 · **Phase:** 6 · **Area:** backend · **Branch:** feature/<nr>-contact-events-audit
- **Ziel:** Kontaktänderungen erzeugen die Domain-Events und Audit-Einträge konsistent.
- **Fachlicher Hintergrund:** `docs/domain/event-catalog.md`; MASTER_PROMPT §17.
- **Scope:** Domain-Event-Ausgabe in E14-02/03 verankern, Audit-Diff, Contract-Test „Kontaktänderung → Event + Audit".
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E14-02, E14-03, E04-02.
- **Acceptance Criteria:** Jede CUD-Operation erzeugt genau ein Domain-Event + Audit; Diff im Audit.
- **Tests:** Integration je Operation.
- **Security-Auswirkung:** Nachvollziehbarkeit. · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** `CONTACT_*`.

### E14-06 · Kurzwahl-Flag + Abruf
**Epic:** 14 · **Phase:** 6 · **Area:** backend, api · **Branch:** feature/<nr>-contact-quickdial
- **Ziel:** Kontakte als Kurzwahl markieren und die Kurzwahlliste abrufen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.9/§13.11.
- **Scope:** `quick_dial`-Flag pflegen (E14-02), `GET /contacts?quick_dial=true` scope-gefiltert.
- **Nicht im Scope:** Overlay-UI (E11-15).
- **Abhängigkeiten:** E14-02.
- **Acceptance Criteria:** Kurzwahlliste enthält nur markierte, scope-sichtbare Kontakte; Sortierung stabil.
- **Tests:** API.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `contacts.view/edit` · **Audit Events:** —

### E14-07 · Telefonbuch-UI (Liste, Suche, CRUD-Formulare)
**Epic:** 14 · **Phase:** 6 · **Area:** frontend · **Branch:** feature/<nr>-ui-phonebook
- **Ziel:** Der Telefonbuch-Tab bietet Liste, Suche und Kontaktpflege.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.9.
- **Scope:** Kontaktliste mit Prioritätsfarbe, Suchfeld, Anlegen/Bearbeiten-Formulare, Nummern verwalten, Kurzwahl-Toggle; tastaturbedienbar.
- **Nicht im Scope:** Prioritäts-Visualisierung-Detail (E14-08); Queue (E14-09).
- **Abhängigkeiten:** E14-02, E14-06, E07-18.
- **Acceptance Criteria:** CRUD über UI; Suche live; a11y grün; Rechte-Gating.
- **Tests:** Playwright: Kontakt anlegen, suchen, Priorität setzen.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `contacts.*` · **Audit Events:** — (Server).

### E14-08 · Prioritäts-Visualisierung blau/orange/rot
**Epic:** 14 · **Phase:** 6 · **Area:** frontend, a11y · **Branch:** feature/<nr>-ui-contact-priority-viz
- **Ziel:** Kontaktprioritäten niedrig=blau, mittel=orange, hoch=rot, konsistent überall.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.9.
- **Scope:** Farb-Tokens + Badges, nicht-farbliche Zusatzkennzeichnung (Icon/Label) für Barrierefreiheit, einheitliche Nutzung in Telefonbuch/Anrufliste.
- **Nicht im Scope:** Animation (E14-09).
- **Abhängigkeiten:** E14-07, E07-17.
- **Acceptance Criteria:** Prioritätsstufe auch ohne Farbwahrnehmung erkennbar; Kontrast AA.
- **Tests:** Playwright/axe.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E14-09 · Anrufwarteschlange: Prioritätsfarbe + animierter Hintergrund + reduced-motion
**Epic:** 14 · **Phase:** 6 · **Area:** frontend, a11y · **Branch:** feature/<nr>-ui-call-queue-priority
- **Ziel:** Wartende Anrufe zeigen Prioritätsfarbe und animierten Hintergrund (hoch stärker), respektieren `prefers-reduced-motion`, sortiert nach Priorität.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.9 „Anrufwarteschlange".
- **Scope:** Queue-Komponente (bindet E11-12 + E14-04), Animationsstufen, reduced-motion-Fallback, Prioritätssortierung.
- **Nicht im Scope:** Ereignis-Prioritäts-Animation (E07-07).
- **Abhängigkeiten:** E11-12, E14-04.
- **Acceptance Criteria:** Sortierung hoch→niedrig; hoch stärkere Animation; reduced-motion → statisch aber klar; unbekannte Nummer wird angezeigt.
- **Tests:** Playwright mit reduced-motion-Emulation; Sortierprüfung.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `calls.view` · **Audit Events:** —

### E14-10 · Kontakt ↔ Rufhistorie-Verknüpfung (UI)
**Epic:** 14 · **Phase:** 6 · **Area:** frontend · **Branch:** feature/<nr>-ui-contact-history-link
- **Ziel:** Aus einem Kontakt die zugehörige Rufhistorie öffnen und umgekehrt.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.8 (Historie), §13.9.
- **Scope:** Verlinkung Kontakt↔Historie im UI (nutzt E11-11 + E14-02), Anzeige „letzter Kontakt".
- **Nicht im Scope:** Backend (vorhanden).
- **Abhängigkeiten:** E11-11, E14-07.
- **Acceptance Criteria:** Navigation in beide Richtungen; scope-konforme Sicht.
- **Tests:** Playwright.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `contacts.view` `calls.view_history` · **Audit Events:** —

---

# EPIC 15 · Technical Trigger Engine

**Milestone:** `15 Technical Trigger Engine` · **Phase:** 5–6 · **Ziel des Epics:**
Technische Endpunkte (getrennt vom Telefonbuch) + versionierte, typisierte
Trigger-Regeln auf normalisierten Signalen, mit exactly-once-Ausführung über
Inbox/Outbox. Deckt BMA, Grundlage für Siedle/Coda. Quellen: MASTER_PROMPT §29/
§32, `.ai/TECHNICAL_TRIGGERS.md`, ADR-0004, ADR-0010.

### E15-01 · DB-Schema: technical_endpoints, technical_endpoint_numbers
**Epic:** 15 · **Phase:** 5 · **Area:** db · **Branch:** feature/<nr>-schema-technical-endpoints
- **Ziel:** Migration für technische Endpunkte, getrennt von `contacts`.
- **Fachlicher Hintergrund:** MASTER_PROMPT §29: „Technische Systeme dürfen NICHT als normale Kontakte modelliert werden."
- **Scope:** `technical_endpoints` (id, name, site, type `door_station|bma|panic_button|video_alarm|alarm_dialer|custom`, provider_id, external_source_ids, default_priority, popup_profile, escalation_profile, workflow_selection_policy, enabled, active_config_version), `technical_endpoint_numbers` (endpoint_id, calling_pattern, called_pattern, cti_route_point).
- **Nicht im Scope:** Kamera-Mappings (Epic 16); Tür-Profile (Epic 17).
- **Abhängigkeiten:** E02-01.
- **Acceptance Criteria:** Migration up/down/up; klare Trennung zu `contacts`; `type` als Enum + `custom`.
- **Tests:** Migration; Constraints.
- **Security-Auswirkung:** — · **HA-Auswirkung:** expand-only. · **Permissions:** — · **Audit Events:** —

### E15-02 · DB-Schema: trigger_rules, trigger_rule_versions, trigger_executions
**Epic:** 15 · **Phase:** 5 · **Area:** db · **Branch:** feature/<nr>-schema-trigger-rules
- **Ziel:** Migration für versionierte Regeln + Ausführungsprotokoll.
- **Fachlicher Hintergrund:** `.ai/TECHNICAL_TRIGGERS.md`: „Published versions are immutable. New changes create a new version."
- **Scope:** `trigger_rules` (id, name, endpoint_id?, lifecycle), `trigger_rule_versions` (id, rule_id, version_no, conditions jsonb (DSL), actions jsonb, lifecycle, published_at), `trigger_executions` (id, provider_event_id, rule_version_id, action_index, status, result, unique(provider_event_id, rule_version_id, action_index)).
- **Nicht im Scope:** Engine (E15-09).
- **Abhängigkeiten:** E15-01.
- **Acceptance Criteria:** Migration up/down/up; publizierte Version unveränderlich (Trigger/Check); Unique-Constraint auf den Ausführungsschlüssel.
- **Tests:** Migration; „UPDATE publizierte Version" schlägt fehl; Unique-Konflikt.
- **Security-Auswirkung:** Bedingungen sind DSL-JSON, kein Code.
- **HA-Auswirkung:** Unique-Key = Basis exactly-once. · **Permissions:** — · **Audit Events:** —

### E15-03 · DB-Schema: external_action_outbox (Erweiterung), client_popup_events
**Epic:** 15 · **Phase:** 5 · **Area:** db · **Branch:** feature/<nr>-schema-outbox-popups
- **Ziel:** Outbox um trigger-spezifische Action-Typen erweitern; Client-Popup-Events persistieren.
- **Fachlicher Hintergrund:** MASTER_PROMPT §34; ADR-0011.
- **Scope:** Outbox-`action_type`-Werte erweitern (open_camera, answer_call, send_dtmf_profile, hangup_call, show_client_popup, notify); `client_popup_events` (id, workplace_id, kind, payload, expires_at, delivered_at, dismissed_at).
- **Nicht im Scope:** Outbox-Kern (E04-06, vorhanden).
- **Abhängigkeiten:** E04-06.
- **Acceptance Criteria:** Migration up/down/up; Popup-Events an `workplace_id` gebunden, mit Ablaufzeit.
- **Tests:** Migration.
- **Security-Auswirkung:** Popup nur an gebundenen Arbeitsplatz.
- **HA-Auswirkung:** expand-only. · **Permissions:** — · **Audit Events:** —

### E15-04 · Normalisiertes Inbound-Signal-Modell
**Epic:** 15 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-inbound-signal-model
- **Ziel:** Ein gemeinsames normalisiertes Signalmodell (`CALL_RINGING`, `TECHNICAL_ALARM_RAISED`, `PANIC_ALARM_RAISED`, `DOORBELL_RINGING`, `BMA_ALARM_CALL`) vor jeder Regelauswertung.
- **Fachlicher Hintergrund:** `.ai/TECHNICAL_TRIGGERS.md` „Provider-neutral inbound signal".
- **Scope:** Signal-Schema, Adapter-Hook (Telefonie/Video → normalisiertes Signal), Übergabe an die Inbox (E04-07).
- **Nicht im Scope:** provider-spezifische Erzeugung (Epics 11/16).
- **Abhängigkeiten:** E04-07, E04-05.
- **Acceptance Criteria:** Jedes Signal validiert gegen Schema; Core inspiziert keine Rohpayloads.
- **Tests:** Schema-Tests; Adapter-Contract.
- **Security-Auswirkung:** Vendor-Isolation.
- **HA-Auswirkung:** Inbox-Dedupe davor. · **Permissions:** — · **Audit Events:** —

### E15-05 · Trigger-Regel-Modell + versionierte Bedingungen (Rule DSL)
**Epic:** 15 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-trigger-rule-model
- **Ziel:** Regeln mit Bedingungen über allowlistete normalisierte Felder (provider, Signaltyp, ANI/DNIS, CTI Route Point, Endpoint-ID, Standort, Alarm-Subtyp, Severity, Richtung, Zeitfenster).
- **Fachlicher Hintergrund:** `.ai/TECHNICAL_TRIGGERS.md` „Trigger Rule"; ADR-0010.
- **Scope:** Trigger-Kontext-Registry (E05-02), Regelmodell, Matching-Reihenfolge/Priorität, Versionierung.
- **Nicht im Scope:** Actions (E15-06..08); Engine (E15-09).
- **Abhängigkeiten:** E05-01, E05-02, E15-02.
- **Acceptance Criteria:** Bedingung mit unbekanntem Feld → Publish-Fehler; deterministische Regelauswahl bei mehreren Treffern.
- **Tests:** Unit: Bedingungsauswertung; Mehrfachtreffer-Determinismus.
- **Security-Auswirkung:** Kein Code; nur allowlistete Felder.
- **HA-Auswirkung:** deterministisch. · **Permissions:** — · **Audit Events:** —

### E15-06 · Typisierte Actions: create_event, attach_workflow, show_client_popup, notify
**Epic:** 15 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-trigger-actions-core
- **Ziel:** Die Kern-Actions einer Regel sind implementiert und laufen über die Outbox (bzw. transaktional für create_event).
- **Fachlicher Hintergrund:** `.ai/TECHNICAL_TRIGGERS.md` „Actions are typed, not arbitrary scripts."
- **Scope:** `create_event` (genau ein Ereignis mit konfigurierter Priorität), `attach_workflow` (published EPK-Version binden, E05-11), `show_client_popup` (E15-14), `notify`.
- **Nicht im Scope:** Kamera/Call-Actions (E15-07/08).
- **Abhängigkeiten:** E15-05, E03-06, E05-11, E04-06.
- **Acceptance Criteria:** `create_event` erzeugt bei Wiederholung/Replay kein zweites Ereignis (Ausführungsschlüssel); Workflow-Bindung an published Version; Popup an den gebundenen Arbeitsplatz.
- **Tests:** Integration: Regel feuert → ein Ereignis + Workflow + Popup; Replay → keine Duplikate.
- **Security-Auswirkung:** — · **HA-Auswirkung:** exactly-once über E15-02-Key. · **Permissions:** — · **Audit Events:** `TRIGGER_EXECUTED` `EVENT_CREATED` (bei create_event).

### E15-07 · Typisierte Actions: integration_action, open_camera, open_camera_group
**Epic:** 15 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-trigger-actions-integration
- **Ziel:** Regel-Actions, die eine Integration ansteuern (v. a. Kamera öffnen), laufen als idempotente Outbox-Zustellung.
- **Fachlicher Hintergrund:** `.ai/TECHNICAL_TRIGGERS.md`; MASTER_PROMPT §31/§36.
- **Scope:** Generischer `integration_action`-Handler + `open_camera`/`open_camera_group` (Ziel: `coda_video`-Capability, Epic 16); Fehlertoleranz (Kamerafehler blockiert nichts).
- **Nicht im Scope:** Coda-Provider selbst (Epic 16).
- **Abhängigkeiten:** E04-06, E15-06.
- **Acceptance Criteria:** Kamera-Action-Fehler → Ereignis/Popup bleiben aktiv; Outbox-Retry für die Kamera; keine Doppelöffnung.
- **Tests:** Integration mit Coda-Mock: Erfolg + Fehlerfall.
- **Security-Auswirkung:** — · **HA-Auswirkung:** entkoppelter Side-Effect. · **Permissions:** — · **Audit Events:** `EXTERNAL_ACTION_DISPATCHED`.

### E15-08 · Typisierte Actions: answer_call, send_dtmf_profile, hangup_call
**Epic:** 15 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-trigger-actions-telephony
- **Ziel:** Telefonie-bezogene Regel-Actions (Grundlage Siedle-Tür).
- **Fachlicher Hintergrund:** `.ai/TECHNICAL_TRIGGERS.md`; MASTER_PROMPT §30.
- **Scope:** `answer_call`/`send_dtmf_profile`/`hangup_call` als Outbox-Actions gegen den aktiven Telefonie-Provider; DTMF-Profil per ID (Secret), nie im Payload/Audit.
- **Nicht im Scope:** Vollständiger Tür-Flow (Epic 17).
- **Abhängigkeiten:** E11-06, E12-05/E13-06, E04-06.
- **Acceptance Criteria:** DTMF genau einmal je Ausführungsschlüssel; Klartext-Code nie geloggt; Fehler sauber gemeldet.
- **Tests:** Integration mit `telephony_mock`: Sequenz answer→dtmf→hangup exactly-once.
- **Security-Auswirkung:** DTMF-Profile als Secret; Audit ohne Code.
- **HA-Auswirkung:** exactly-once. · **Permissions:** `door.open` (bei DTMF) · **Audit Events:** `EXTERNAL_ACTION_DISPATCHED` (ohne Secret).

### E15-09 · Rule-Execution-Engine (Key = provider_event_id + rule_version + action_index)
**Epic:** 15 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-trigger-engine
- **Ziel:** Die Engine wertet nach Inbox-Dedupe die Regeln aus und führt Actions exakt einmal aus.
- **Fachlicher Hintergrund:** `.ai/TECHNICAL_TRIGGERS.md` „Active/Active exactly-once protection".
- **Scope:** Ablauf: Inbox-Event (neu) → Regeln matchen → je Action `trigger_executions`-Zeile (unique) → Outbox/transaktionale Ausführung; Wiederaufnahme nach Crash.
- **Nicht im Scope:** Einzelne Action-Handler (E15-06..08).
- **Abhängigkeiten:** E04-07, E15-02, E15-05, E15-06.
- **Acceptance Criteria:** Doppelt zugestelltes Provider-Event → keine zweite Ausführung; Crash mitten in der Action-Sequenz → Wiederaufnahme ohne Duplikate; Reihenfolge der Actions deterministisch.
- **Tests:** §35-Fälle „duplicate provider event → keine zweite Öffnung/kein zweites Ereignis"; Crash-Recovery.
- **Security-Auswirkung:** — · **HA-Auswirkung:** Kern der exactly-once-Zusage. · **Permissions:** — · **Audit Events:** `TRIGGER_EXECUTED`.

### E15-10 · Trigger-Admin-API (Endpoints CRUD, Regeln Draft→Validate→Publish→Retire)
**Epic:** 15 · **Phase:** 6 · **Area:** backend, api · **Branch:** feature/<nr>-trigger-admin-api
- **Ziel:** Admins verwalten technische Endpunkte und Regeln inkl. Lifecycle.
- **Fachlicher Hintergrund:** `.ai/TECHNICAL_TRIGGERS.md` „Admin UI" (Punkte 1–10).
- **Scope:** CRUD `/api/v1/technical-endpoints`, `/api/v1/trigger-rules` + `/versions/{id}/validate|publish|retire`; Validierung (Bedingungen, Action-Referenzen existieren).
- **Nicht im Scope:** Admin-UI (separates Frontend-Issue je Bereich; hier API).
- **Abhängigkeiten:** E15-01, E15-02, E15-05, E02-08.
- **Acceptance Criteria:** `technical_endpoints.manage` Pflicht; Publish nur nach Validierung; Änderung an published → neue Version; alles auditiert.
- **Tests:** API: CRUD, Lifecycle, Validierungsfehler, Rechte.
- **Security-Auswirkung:** Hochprivilegiert (steuert automatische Türöffnung/Alarmerzeugung).
- **HA-Auswirkung:** DB-basiert, sofort wirksam. · **Permissions:** `technical_endpoints.view/manage` `door.configure`
- **Audit Events:** `TECHNICAL_ENDPOINT_*` `TRIGGER_RULE_PUBLISHED/RETIRED`.

### E15-11 · Simulations-/Testmodus (keine realen Seiteneffekte)
**Epic:** 15 · **Phase:** 6 · **Area:** backend, api · **Branch:** feature/<nr>-trigger-simulation
- **Ziel:** Admins testen Endpunkt-/Regelkonfiguration mit simulierten Signalen ohne echte Türöffnung/Alarme.
- **Fachlicher Hintergrund:** `.ai/TECHNICAL_TRIGGERS.md` „Test/simulation mode without real side effects".
- **Scope:** `POST /trigger-rules/simulate` mit synthetischem Signal; Actions im Dry-Run (Report statt Outbox-Zustellung).
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E15-09.
- **Acceptance Criteria:** Simulation erzeugt keine Outbox-Zustellung, kein Ereignis, keine DTMF; Report zeigt getroffene Regel + geplante Actions.
- **Tests:** Integration: Simulation eines Panic-Signals → Report, keine Realwirkung.
- **Security-Auswirkung:** Verhindert versehentliche Realauslösung beim Testen.
- **HA-Auswirkung:** isoliert. · **Permissions:** `technical_endpoints.manage` · **Audit Events:** `TRIGGER_SIMULATED`.

### E15-12 · Unmapped-Source-Queue + Diagnostics-API
**Epic:** 15 · **Phase:** 6 · **Area:** backend, api · **Branch:** feature/<nr>-trigger-unmapped-queue
- **Ziel:** Provider-Events ohne passende Endpoint-/Regelzuordnung landen in einer Diagnose-Queue für Admin-Mapping.
- **Fachlicher Hintergrund:** `.ai/TECHNICAL_TRIGGERS.md` „Unmapped-source queue for diagnostics/admin mapping".
- **Scope:** Persistenz nicht zugeordneter Signale, `GET /trigger/unmapped`, Aktion „Endpoint anlegen/zuordnen".
- **Nicht im Scope:** UI.
- **Abhängigkeiten:** E15-09.
- **Acceptance Criteria:** Nicht zugeordnetes Signal → Queue-Eintrag, kein Fehler; Zuordnung möglich; Zähler in Diagnostics.
- **Tests:** Integration: unbekannte Quelle → Queue.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `technical_endpoints.view/manage` · **Audit Events:** `TECHNICAL_ENDPOINT_MAPPED`.

### E15-13 · BMA-Flow: Nummernmatch → genau ein kritisches Ereignis → Workflow-Version
**Epic:** 15 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-bma-flow
- **Ziel:** Ein Anruf von der konfigurierten BMA-Nummer erzeugt exakt ein Ereignis (typisch kritisch) mit gebundener Workflow-Version und Prioritätswarnung.
- **Fachlicher Hintergrund:** MASTER_PROMPT §32 (Flow 1–7).
- **Scope:** `BMA_ALARM_CALL`-Signal, Endpoint-Typ `bma`, Regel mit `create_event`+`attach_workflow`, Prioritätswarnung (E03-15), Ereignis im Ereignisspeicher.
- **Nicht im Scope:** Siedle/Coda.
- **Abhängigkeiten:** E15-04, E15-06, E15-09.
- **Acceptance Criteria:** §35 „BMA": genau ein kritisches Ereignis, richtige Workflow-Version gebunden, im Ereignisspeicher sichtbar; Duplicate-Call-Event erzeugt kein zweites Ereignis.
- **Tests:** §35-BMA-Szenario (5 Schritte) automatisiert.
- **Security-Auswirkung:** — · **HA-Auswirkung:** exactly-once. · **Permissions:** — · **Audit Events:** `TRIGGER_EXECUTED` `EVENT_CREATED`.

### E15-14 · Client-Popup-Zustellung (unten rechts, zeitlich begrenzt)
**Epic:** 15 · **Phase:** 5 · **Area:** backend, frontend · **Branch:** feature/<nr>-client-popup-delivery
- **Ziel:** `show_client_popup`-Actions liefern ein zeitlich begrenztes Popup an den gebundenen BBZ-Client (unten rechts).
- **Fachlicher Hintergrund:** MASTER_PROMPT §30.1 (Klingel-Popup), §36 (Alarm-Popup); `.ai/FEATURES.md` „bottom-right BBZ client doorbell popup".
- **Scope:** `client_popup_events` (E15-03) über den Event-Stream an `workplace_id`, UI-Komponente unten rechts mit Timeout + Aktionen (kontextabhängig), Bestätigung/Verwerfen.
- **Nicht im Scope:** Tür-Öffnen-Logik (Epic 17).
- **Abhängigkeiten:** E15-03, E03-13, E07-05.
- **Acceptance Criteria:** Popup erscheint nur am gebundenen Arbeitsplatz; verschwindet nach Timeout; auch bei Coda-Ausfall (entkoppelt); tastaturbedienbar.
- **Tests:** Integration + Playwright: Popup erscheint/verfällt; Aktion löst Folgekommando aus.
- **Security-Auswirkung:** Popup-Payload ohne Secrets; nur an autorisierten Arbeitsplatz.
- **HA-Auswirkung:** Über Stream + Catch-up zustellbar.
- **Permissions:** kontextabhängig (`door.open`, `events.view`) · **Audit Events:** `CLIENT_POPUP_DELIVERED`.

### E15-15 · Trigger-Engine-E2E (BMA + Duplicate-Schutz)
**Epic:** 15 · **Phase:** 5 · **Area:** test · **Branch:** feature/<nr>-e2e-trigger-engine
- **Ziel:** Die §35-BMA-Fälle und der Duplicate-Provider-Event-Schutz laufen automatisiert grün.
- **Fachlicher Hintergrund:** MASTER_PROMPT §35 „BMA"; §29 Active/Active.
- **Scope:** E2E über Compose + `telephony_mock`: BMA-Call → ein Ereignis + Workflow; doppeltes Provider-Event → kein zweites Ereignis; SRV-Failover-Replay → kein Duplikat.
- **Nicht im Scope:** Siedle/Coda-E2E (Epics 16/17).
- **Abhängigkeiten:** E15-13, E15-09.
- **Acceptance Criteria:** Alle Assertions grün inkl. Audit.
- **Tests:** ebendiese E2E.
- **Security-Auswirkung:** — · **HA-Auswirkung:** verifiziert exactly-once. · **Permissions:** — · **Audit Events:** verifiziert.

---

# EPIC 16 · Coda Video / HxGN dC3 Video

**Milestone:** `16 Coda Video / HxGN dC3 Video` · **Phase:** 5+ · **Ziel des Epics:**
`coda_video` als kanonische Integration mit zwei Capability-Gruppen (Video +
Alarm-Ingress), Panik-/Überfall-Alarm → exakt ein kritisches Ereignis + EPK,
entkoppelte Kamera-Side-Effects. **Keine Vendor-Anbindung ohne offizielle
Coda/HxGN-dC3-Doku.** Quellen: MASTER_PROMPT §31/§36, `.ai/INTEGRATIONS_CODA_VIDEO.md`,
ADR-0006, ADR-0016.

### E16-01 · `coda_video`-Scaffold + Manifest (Video + Alarm-Ingress-Capabilities)
**Epic:** 16 · **Phase:** 5 · **Area:** integration · **Branch:** feature/<nr>-coda-scaffold
- **Ziel:** Formalisiertes Integrations-Scaffold mit getrennten Capability-Gruppen; Mock existiert bereits.
- **Fachlicher Hintergrund:** ARCHITECTURE: „two independent capability groups: video presentation/control, inbound alarm/event ingestion"; ADR-0016 kanonischer Name.
- **Scope:** `integrations/coda_video/` (manifest, config_schema), Capability-Deklaration (`video.*`, `alarm.*`), Legacy-Alias „Cayuga" nur als Display.
- **Nicht im Scope:** Vendor-API-Aufrufe (blockiert, E16-13).
- **Abhängigkeiten:** Epic 01 (Mock, SDK).
- **Acceptance Criteria:** Manifest validiert; beide Capability-Gruppen unabhängig aktivierbar; Name `coda_video` überall.
- **Tests:** Manifest-Schema; Discovery.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `integrations.view/configure` · **Audit Events:** —

### E16-02 · Normalisiertes Video-Capability-Interface
**Epic:** 16 · **Phase:** 5 · **Area:** integration, backend · **Branch:** feature/<nr>-coda-video-interface
- **Ziel:** `video.health/resolve_camera/open_camera/focus_camera/open_camera_group/open_alarm_context` als herstellerneutrales Interface.
- **Fachlicher Hintergrund:** `.ai/INTEGRATIONS_CODA_VIDEO.md` „Normalized BBZ capabilities / Video".
- **Scope:** Protocol-Definition im SDK, Registrierung als Video-Provider, Fehler-/Timeout-Semantik.
- **Nicht im Scope:** Alarm-Ingress (E16-03).
- **Abhängigkeiten:** E16-01.
- **Acceptance Criteria:** Interface vollständig + typisiert; Mock erfüllt es; keine Vendor-Objekt-IDs im Interface.
- **Tests:** Protocol-Konformität gegen Mock.
- **Security-Auswirkung:** Vendor-Isolation.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E16-03 · Normalisiertes Alarm-Ingress-Interface
**Epic:** 16 · **Phase:** 5 · **Area:** integration, backend · **Branch:** feature/<nr>-coda-alarm-interface
- **Ziel:** `alarm.subscribe/resolve_source/get_context/get_associated_cameras` als Interface; BBZ-Ack getrennt von Coda-Ack.
- **Fachlicher Hintergrund:** `.ai/INTEGRATIONS_CODA_VIDEO.md` „Alarm ingress"; „BBZ event acknowledgement and external Coda alarm acknowledgement must remain separate".
- **Scope:** Protocol, Registrierung als Alarm-Provider, optionale `alarm.acknowledge_external` nur falls offizielle Doku es hergibt (Feature-Flag).
- **Nicht im Scope:** Normalisierung/Persistenz (E16-04).
- **Abhängigkeiten:** E16-01.
- **Acceptance Criteria:** Interface vollständig; externes Ack ist strikt vom BBZ-Ack getrennt; Mock erfüllt es.
- **Tests:** Protocol-Konformität.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E16-04 · Alarm-Normalisierung → unveränderliches Provider-Event + Inbox-Dedupe
**Epic:** 16 · **Phase:** 5 · **Area:** integration, backend · **Branch:** feature/<nr>-coda-alarm-normalization
- **Ziel:** Jeder Coda-Alarm wird vor Regelauswertung in ein unveränderliches Provider-Event mit den definierten Feldern überführt und dedupliziert.
- **Fachlicher Hintergrund:** `.ai/INTEGRATIONS_CODA_VIDEO.md` „Alarm normalization" (Feldliste); ADR-0006.
- **Scope:** Normalisierung (provider, provider_event_id, provider_alarm_id, alarm_type/subtype, source_external_id, site_external_id, Zeiten, severity_external, state_external, Kamera-Refs, raw-hash, provider_instance_id), deterministischer Dedupe-Key falls keine stabile ID, Inbox (E04-07).
- **Nicht im Scope:** Runtime-Flow (E16-07).
- **Abhängigkeiten:** E16-03, E04-07, E15-04.
- **Acceptance Criteria:** Doppelter Alarm → einmal verarbeitet; Rohpayload nur referenziert/gehasht; alle Pflichtfelder vorhanden.
- **Tests:** Integration mit Mock: Duplikat, Reconnect-Replay, fehlende stabile ID.
- **Security-Auswirkung:** Rohpayload nicht in Business-Rules.
- **HA-Auswirkung:** exactly-once-Basis. · **Permissions:** — · **Audit Events:** —

### E16-05 · DB-Schema: integration_camera_mappings
**Epic:** 16 · **Phase:** 5 · **Area:** db · **Branch:** feature/<nr>-schema-camera-mappings
- **Ziel:** Migration für Endpoint-/Alarm-Quelle → Kamera(s)-Zuordnung.
- **Fachlicher Hintergrund:** MASTER_PROMPT §34; `.ai/INTEGRATIONS_CODA_VIDEO.md`.
- **Scope:** `integration_camera_mappings` (id, endpoint_id?, alarm_source_external_id?, camera_external_ref, ordinal, provider_instance_id).
- **Nicht im Scope:** Admin-API (E16-06).
- **Abhängigkeiten:** E15-01.
- **Acceptance Criteria:** Migration up/down/up; Mapping sowohl an Endpoint als auch an externe Alarm-Quelle möglich.
- **Tests:** Migration.
- **Security-Auswirkung:** — · **HA-Auswirkung:** expand-only. · **Permissions:** — · **Audit Events:** —

### E16-06 · Admin-Config je Coda-Alarmquelle
**Epic:** 16 · **Phase:** 5 · **Area:** backend, api · **Branch:** feature/<nr>-coda-alarm-source-admin
- **Ziel:** Pro Alarmquelle konfigurierbar: External Source ID → Technical Endpoint, Standort, Priorität (Default kritisch), Kameras, Popup-Profil, EPK-Version, Eskalation, enabled.
- **Fachlicher Hintergrund:** MASTER_PROMPT §36; `.ai/INTEGRATIONS_CODA_VIDEO.md` „Admin mapping".
- **Scope:** API zum Anlegen/Pflegen der Alarmquellen-Konfiguration (nutzt Technical-Endpoints E15 + Camera-Mappings E16-05 + Trigger-Regeln E15).
- **Nicht im Scope:** Vendor-Discovery der Quellen.
- **Abhängigkeiten:** E15-10, E16-05.
- **Acceptance Criteria:** Konfiguration vollständig gemäß §36-Liste; Default-Priorität für `panic_button` = kritisch, aber überschreibbar; alles auditiert.
- **Tests:** API-CRUD; Default-Priorität.
- **Security-Auswirkung:** Hochprivilegiert (definiert automatische kritische Ereigniserzeugung).
- **HA-Auswirkung:** DB-basiert. · **Permissions:** `technical_endpoints.manage` `integrations.configure`
- **Audit Events:** `CODA_ALARM_SOURCE_CONFIGURED`.

### E16-07 · Panik-/Überfall-Runtime-Flow (exakt ein kritisches Ereignis + EPK + Popup)
**Epic:** 16 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-coda-panic-flow
- **Ziel:** Ein Coda-Panik-Alarm erzeugt über die Trigger-Engine genau ein kritisches Ereignis, bindet die publizierte EPK-Version, löst Prioritätswarnung + Popup aus; Kamera ist entkoppelter Side-Effect.
- **Fachlicher Hintergrund:** MASTER_PROMPT §36 (Runtime flow 1–12).
- **Scope:** Verknüpfung E16-04 → E15-09 → E15-06 (`create_event`+`attach_workflow`+`show_client_popup`) + E15-07 (`open_camera_group`); Kamerafehler blockiert nichts.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E16-04, E15-06, E15-07, E15-09.
- **Acceptance Criteria:** Genau ein kritisches Ereignis je Alarm; EPK-Version korrekt gebunden; Popup + Prioritätswarnung; Kamerafehler → Ereignis/Popup bleiben; Duplikat/Failover → kein zweites Ereignis.
- **Tests:** §36.1-Szenario (10 Schritte) automatisiert.
- **Security-Auswirkung:** — · **HA-Auswirkung:** exactly-once + entkoppelte Side-Effects. · **Permissions:** — · **Audit Events:** `TRIGGER_EXECUTED` `EVENT_CREATED` `CLIENT_POPUP_DELIVERED`.

### E16-08 · Kamera-Öffnen als unabhängiger Outbox-Side-Effect
**Epic:** 16 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-coda-camera-sideeffect
- **Ziel:** Kamera-Actions laufen ausschließlich über die Outbox und können fehlschlagen, ohne Alarm/Ereignis/Popup zu beeinträchtigen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §31/§36: „Camera-open failure must never suppress event creation or the operator alarm popup."
- **Scope:** Outbox-Handler für `open_camera`/`open_camera_group` gegen `video.*`-Capability, Retry/Backoff, Statusanzeige „Kameraaktion fehlgeschlagen" im Ereignis.
- **Nicht im Scope:** Video-UI (E16-12).
- **Abhängigkeiten:** E16-02, E04-06, E15-07.
- **Acceptance Criteria:** Kamera-Provider down → Ereignis/Popup unbeeinflusst; Outbox retried die Kamera; kein doppeltes Öffnen.
- **Tests:** Integration: Kamera-Mock wirft Fehler → Ereignis aktiv, Retry sichtbar.
- **Security-Auswirkung:** — · **HA-Auswirkung:** Entkopplung. · **Permissions:** — · **Audit Events:** `EXTERNAL_ACTION_FAILED` (Kamera).

### E16-09 · `coda_video`-Mock-Provider (vollständige Simulation)
**Epic:** 16 · **Phase:** 5 · **Area:** integration, test · **Branch:** feature/<nr>-coda-mock-full
- **Ziel:** Der Mock simuliert Panic/Intrusion/generischen Alarm, 1/mehrere Kameras, unmapped Quelle, Duplikat, Reconnect-Replay, Kamerafehler.
- **Fachlicher Hintergrund:** `.ai/INTEGRATIONS_CODA_VIDEO.md` „Testing" (Liste).
- **Scope:** Mock erfüllt `video.*` + `alarm.*`, konfigurierbare Szenarien per API/Config.
- **Nicht im Scope:** Echte Coda-API.
- **Abhängigkeiten:** E16-02, E16-03.
- **Acceptance Criteria:** Alle in der Doku genannten Simulationsfälle auslösbar; deterministisch.
- **Tests:** Nutzung in E16-11.
- **Security-Auswirkung:** — · **HA-Auswirkung:** unterstützt Replay-Tests. · **Permissions:** — · **Audit Events:** —

### E16-10 · Coda-Diagnostics-API
**Epic:** 16 · **Phase:** 5 · **Area:** integration, backend · **Branch:** feature/<nr>-coda-diagnostics
- **Ziel:** Admin sieht Provider-Health, letztes Event, letzte erfolgreiche Kameraaktion, unmapped-Zähler, Duplicate-Zähler, Verarbeitungslatenz, Capabilities, Lizenzwarnungen.
- **Fachlicher Hintergrund:** `.ai/INTEGRATIONS_CODA_VIDEO.md` „Diagnostics".
- **Scope:** `GET /integrations/coda_video/diagnostics`; Aggregation aus Inbox/Outbox/Health.
- **Nicht im Scope:** Dashboard (Epic 22).
- **Abhängigkeiten:** E16-04, E16-08.
- **Acceptance Criteria:** Alle Felder korrekt unter simulierten Störungen; `integrations.diagnostics` Pflicht.
- **Tests:** Integration: Störungen spiegeln sich.
- **Security-Auswirkung:** keine Secrets im Body.
- **HA-Auswirkung:** — · **Permissions:** `integrations.diagnostics` · **Audit Events:** —

### E16-11 · Coda-Alarm-E2E (§36.1)
**Epic:** 16 · **Phase:** 5 · **Area:** test · **Branch:** feature/<nr>-e2e-coda-panic
- **Ziel:** Der §36.1-Pflichttest „Überfallalarm" läuft automatisiert grün (10 Schritte).
- **Fachlicher Hintergrund:** MASTER_PROMPT §36.1.
- **Scope:** E2E über Compose + `coda_video`-Mock: Panic → persist → Endpoint-Mapping → exakt ein kritisches Ereignis → korrekte EPK-Version → Popup → Kameraaktion → Kamerafehler toleriert → Duplikat sicher → SRV01-Ausfall/Replay über SRV02 ohne Duplikat.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E16-07, E16-08, E16-09, E06-11.
- **Acceptance Criteria:** Alle 10 Schritte grün inkl. Audit-Assertions.
- **Tests:** ebendieser E2E (nightly).
- **Security-Auswirkung:** — · **HA-Auswirkung:** verifiziert Replay-Sicherheit. · **Permissions:** — · **Audit Events:** verifiziert.

### E16-12 · Kamera-Ansicht-UI (Arbeitsplatz / Alarm-Kontext)
**Epic:** 16 · **Phase:** 5 · **Area:** frontend · **Branch:** feature/<nr>-ui-camera-view
- **Ziel:** Im Ereignis-/Alarm-Kontext werden zugeordnete Kameras dargestellt/fokussiert; Ausfall wird klar angezeigt.
- **Fachlicher Hintergrund:** MASTER_PROMPT §31/§36.
- **Scope:** Kamera-Panel im Ereignisdetail/Alarm-Popup-Kontext (nutzt `video.*`), Fehlanzeige „Video derzeit nicht verfügbar", kein Blockieren der Ereignisbearbeitung.
- **Nicht im Scope:** Vendor-spezifische Player-SDKs (blockiert bis Doku).
- **Abhängigkeiten:** E16-02, E07-08.
- **Acceptance Criteria:** Kamera-Ausfall blockiert die Ereignisbearbeitung nicht; a11y-konforme Alternativdarstellung.
- **Tests:** Playwright mit Mock: Kamera an/aus.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `integrations.view` · **Audit Events:** —

### E16-13 · Blocker-Doku: keine Vendor-Anbindung ohne offizielle Coda/HxGN-dC3-Doku
**Epic:** 16 · **Phase:** 5 · **Area:** documentation · **Branch:** docs/<nr>-coda-pending-info
- **Ziel:** Referenzierbarer Blocker gegen erfundene Endpunkte/Auth/Objektmodelle.
- **Fachlicher Hintergrund:** MASTER_PROMPT §31/§36; ADR-0006: „implemented only from official project/vendor documentation."
- **Scope:** `docs/` Blocker mit „Do NOT invent"-Liste (URLs, Auth, Event-Payloads, Ack-Methoden, Kamera-IDs, Display-Agent-Kommandos, SDK-Klassen, Lizenz-Annahmen); Verweis aus `.ai/CURRENT_STATE.md`.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** —
- **Acceptance Criteria:** Blocker vollständig; Prod-Config trägt „requires Coda API/SDK docs"-Marker.
- **Tests:** Doc-Review.
- **Security-Auswirkung:** verhindert Fehlannahmen. · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

---

# EPIC 17 · Siedle

**Milestone:** `17 Siedle` · **Phase:** 5+ · **Ziel des Epics:** Siedle-
Türstationen als technische Endpunkte; Klingeln → Popup + Kamera; „Öffnen" →
transaktionaler DTMF-Türöffner über die Telefonie-Integration, exactly-once,
ohne Klartext-Code im Audit. Quellen: MASTER_PROMPT §30, `.ai/INTEGRATIONS_SIEDLE.md`,
ADR-0004.

### E17-01 · Siedle-Endpoint-Profil (door_station, DTMF-Profil-Ref, Kamera-Mapping)
**Epic:** 17 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-siedle-endpoint-profile
- **Ziel:** Türstation als `technical_endpoint` vom Typ `door_station` mit allen Siedle-Konfigurationsfeldern.
- **Fachlicher Hintergrund:** `.ai/INTEGRATIONS_SIEDLE.md` „Technical endpoint model".
- **Scope:** Endpoint-Felder (Anzeigename, Standort, Calling/Route-Match, Kamera-Mapping-Ref, DTMF-Profil-Ref, Popup-Text, Timeout, Priorität, enabled); Admin-API-Erweiterung.
- **Nicht im Scope:** DTMF-Profil-Speicher (E17-02).
- **Abhängigkeiten:** E15-01, E15-10.
- **Acceptance Criteria:** Profil vollständig; DTMF-Profil nur als Referenz-ID (kein Code im Endpoint).
- **Tests:** API-CRUD.
- **Security-Auswirkung:** Kein DTMF-Code im Endpoint-Objekt.
- **HA-Auswirkung:** — · **Permissions:** `technical_endpoints.manage` `door.configure` · **Audit Events:** `TECHNICAL_ENDPOINT_UPDATED`.

### E17-02 · DB-Schema: door_action_profiles (verschlüsselter DTMF-Secret, Referenz per ID)
**Epic:** 17 · **Phase:** 5 · **Area:** db, security · **Branch:** feature/<nr>-schema-door-profiles
- **Ziel:** Migration für Tür-Aktionsprofile; DTMF-Code verschlüsselt, nur per ID referenzierbar.
- **Fachlicher Hintergrund:** MASTER_PROMPT §30; `.ai/SECURITY.md`: „DTMF door codes are secrets … audit the action profile ID, not the code."
- **Scope:** `door_action_profiles` (id, name, dtmf_ciphertext, post_dtmf_delay_ms, auto_hangup bool, created_by); Verschlüsselung über Secret-Store (E01-03) / KMS-Envelope.
- **Nicht im Scope:** Öffnen-Flow (E17-05).
- **Abhängigkeiten:** E01-03, E02-01.
- **Acceptance Criteria:** Migration up/down/up; `dtmf_ciphertext` ohne Schlüssel unbrauchbar; keine API gibt den Klartext je zurück.
- **Tests:** Migration; „Klartext nirgends abrufbar"-Test.
- **Security-Auswirkung:** Kern des Secret-Schutzes.
- **HA-Auswirkung:** Schlüssel auf beiden Knoten verfügbar (Secret-Store).
- **Permissions:** `door.configure` · **Audit Events:** `DOOR_PROFILE_CREATED/UPDATED` (ohne Code).

### E17-03 · DOORBELL_RINGING-Trigger (CUCM/SIP-Ringing → Endpoint-Match → Signal)
**Epic:** 17 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-siedle-doorbell-trigger
- **Ziel:** Ein eingehender Ring von einer Siedle-Nummer/Route erzeugt das normalisierte Signal `DOORBELL_RINGING`.
- **Fachlicher Hintergrund:** `.ai/INTEGRATIONS_SIEDLE.md` „Ring flow" (1–3).
- **Scope:** Technischer-Endpoint-Matcher für Ringing-Events, `DOORBELL_RINGING`-Signal in die Inbox, Regelanknüpfung.
- **Nicht im Scope:** Popup (E17-04); Öffnen (E17-05).
- **Abhängigkeiten:** E11-03, E15-04, E15-09.
- **Acceptance Criteria:** Ring von konfigurierter Quelle → genau ein `DOORBELL_RINGING`; unbekannte Quelle → unmapped-Queue.
- **Tests:** Integration mit `telephony_mock`: Ring → Signal; Duplikat → ein Signal.
- **Security-Auswirkung:** — · **HA-Auswirkung:** Inbox-Dedupe. · **Permissions:** — · **Audit Events:** `TRIGGER_EXECUTED`.

### E17-04 · Klingel-Popup + Kamera-Side-Effect (entkoppelt)
**Epic:** 17 · **Phase:** 5 · **Area:** backend, frontend · **Branch:** feature/<nr>-siedle-ring-popup-camera
- **Ziel:** Bei `DOORBELL_RINGING` erscheint unten rechts ein zeitlich begrenztes „Klingeln: <Bezeichnung>"-Popup mit Aktionen; die zugeordnete Kamera wird unabhängig angefordert.
- **Fachlicher Hintergrund:** `.ai/INTEGRATIONS_SIEDLE.md` „Ring flow" (4–6); Coda-Ausfall darf den Tür-Flow nicht blockieren.
- **Scope:** Trigger-Actions `show_client_popup` (E15-14) + `open_camera` (E15-07); Popup-Aktionen mind. `Öffnen` und `Schließen/Ablehnen`.
- **Nicht im Scope:** Öffnen-Transaktion (E17-05).
- **Abhängigkeiten:** E17-03, E15-14, E16-08.
- **Acceptance Criteria:** Popup nur am gebundenen Arbeitsplatz; Coda down → Popup erscheint trotzdem; Timeout entfernt das Popup.
- **Tests:** Integration + Playwright: Ring → Popup; Coda-Mock-Fehler → Popup trotzdem.
- **Security-Auswirkung:** Popup ohne Secrets.
- **HA-Auswirkung:** Entkopplung Video/Tür. · **Permissions:** `door.view` · **Audit Events:** `CLIENT_POPUP_DELIVERED`.

### E17-05 · Tür-Öffnen: transaktionaler, idempotenter Flow
**Epic:** 17 · **Phase:** 5 · **Area:** backend · **Branch:** feature/<nr>-siedle-door-open-flow
- **Ziel:** „Öffnen" führt idempotent aus: `door.open` prüfen → ggf. Call annehmen → CONNECTED/Media abwarten → DTMF-Profil senden → Nachlaufzeit → auto Hangup → auditiertes Ergebnis.
- **Fachlicher Hintergrund:** MASTER_PROMPT §30.2; `.ai/INTEGRATIONS_SIEDLE.md` „Door-open flow" (1–8).
- **Scope:** Orchestrierung über Outbox-Actions (E15-08) mit Ausführungsschlüssel; Zustandsmaschine des Öffnungsvorgangs; Timeout-/Fehlerbehandlung.
- **Nicht im Scope:** UI-Button (E17-04 liefert ihn).
- **Abhängigkeiten:** E15-08, E17-02, E12-05/E13-06.
- **Acceptance Criteria:** DTMF wird **genau einmal** gesendet; erneuter „Öffnen"-Klick mit gleicher Command-Id → keine zweite Öffnung; nach Nachlaufzeit automatischer Hangup; jeder Ausgang auditiert.
- **Tests:** §35 „Siedle/Cayuga" (Schritte 5–8, 10) + §30-Flow; Duplicate-Command → keine zweite Öffnung.
- **Security-Auswirkung:** `door.open` Pflicht; Klartext-Code nur transient im Speicher, nie persistiert/geloggt.
- **HA-Auswirkung:** exactly-once über Outbox + Ausführungsschlüssel + Idempotenz-Command.
- **Permissions:** `door.open` (`door.answer` falls Annahme nötig) · **Audit Events:** `DOOR_OPEN_REQUESTED` `DOOR_OPEN_RESULT` (Pflicht-Audit, **ohne** DTMF-Code).

### E17-06 · Audit ohne Klartext-DTMF (nur Profil-ID)
**Epic:** 17 · **Phase:** 5 · **Area:** backend, security · **Branch:** feature/<nr>-siedle-audit-no-secret
- **Ziel:** Kein Audit-/Event-/Log-Pfad enthält den DTMF-Klartext; nur die Profil-ID.
- **Fachlicher Hintergrund:** MASTER_PROMPT §30.2; `.ai/SECURITY.md`.
- **Scope:** Redaction-Layer für Tür-Actions, Contract-Test über alle Senken (Audit, Domain-Event, Outbox-Result, strukturierte Logs).
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E17-05, E04-02.
- **Acceptance Criteria:** Automatisierter Test durchsucht alle Senken nach dem Testcode und findet ihn nie; Audit enthält `door_action_profile_id`.
- **Tests:** Integration: „Code taucht nirgends auf".
- **Security-Auswirkung:** Kern der Secret-Nichtprotokollierung.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** `DOOR_OPEN_RESULT` (Profil-ID).

### E17-07 · Fehlerzustände + Permissions-Seed + Siedle/Coda-E2E (§35)
**Epic:** 17 · **Phase:** 5 · **Area:** backend, test · **Branch:** feature/<nr>-siedle-failures-e2e
- **Ziel:** Alle Siedle-Fehlerzustände sind behandelt, die `door.*`-Permissions geseedet, und der §35-Siedle/Cayuga-E2E-Test läuft grün.
- **Fachlicher Hintergrund:** `.ai/INTEGRATIONS_SIEDLE.md` „Failure states"; MASTER_PROMPT §35 „Siedle/Cayuga" (1–10).
- **Scope:** Behandlung: Anrufer legt auf, keine Media, keine DTMF-Capability, Coda down, Duplicate-Command, Auth denied, Telefonie-Failover; Daten-Migration `door.view/answer/open/configure` + `technical_endpoints.*`; E2E-Suite.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E17-05, E17-06, E02-14.
- **Acceptance Criteria:** Jeder Fehlerzustand → klares UI-Ergebnis, kein stiller Retry ohne gleiche Idempotency-Key; §35-E2E (10 Schritte) grün, inkl. „Duplicate Provider Event erzeugt keine zweite Öffnung" und „Audit ohne Klartext-DTMF".
- **Tests:** §35-Siedle-E2E; Fehlerzustands-Matrix.
- **Security-Auswirkung:** Least-Privilege-Defaults; robuste Fehlerbehandlung.
- **HA-Auswirkung:** verifiziert exactly-once bei Failover.
- **Permissions:** `door.view/answer/open/configure` `technical_endpoints.view/manage` · **Audit Events:** verifiziert.

---

# EPIC 18 · DWD Weather

**Milestone:** `18 DWD Weather` · **Phase:** 7 · **Ziel des Epics:** Erste echte
Live-Integrationsreferenz: DWD-Warnungen, Radar/Niederschlag, lokale Messwerte
für Mittelfranken, mit Wetterlage-Seite und „Wetterereignis erzeugen". Quellen:
MASTER_PROMPT §10/§13.12.

### E18-01 · `integrations/dwd`-Scaffold + Manifest + Config (Mittelfranken)
**Epic:** 18 · **Phase:** 7 · **Area:** integration · **Branch:** feature/<nr>-dwd-scaffold
- **Ziel:** Integrations-Grundgerüst mit Config für Zielgebiet Mittelfranken und Beispielorte.
- **Fachlicher Hintergrund:** MASTER_PROMPT §10: Zielgebiet Mittelfranken; Orte Nürnberg/Fürth/Erlangen/Schwabach/Ansbach/Neustadt a.d. Aisch.
- **Scope:** `integrations/dwd/` (manifest, config_schema, adapter-Stub), Warnregionen/Orte konfigurierbar, Capability-Modell (warnings/radar/observations/health).
- **Nicht im Scope:** Adapter-Implementierung (E18-02..04).
- **Abhängigkeiten:** Epic 01 (SDK).
- **Acceptance Criteria:** Manifest validiert; Region/Orte aus Config; Discovery im Core.
- **Tests:** Manifest-Schema.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `integrations.view/configure` · **Audit Events:** —

### E18-02 · DWD-Warnungen-Adapter (offizielle DWD-Open-Data-API)
**Epic:** 18 · **Phase:** 7 · **Area:** integration · **Branch:** feature/<nr>-dwd-warnings
- **Ziel:** Wetterwarnungen für die konfigurierten Warnregionen abrufen und normalisieren.
- **Fachlicher Hintergrund:** MASTER_PROMPT §10; DWD stellt dokumentierte Open-Data-Schnittstellen bereit (echte API, keine Erfindung).
- **Scope:** Client gegen die dokumentierte DWD-Warnungs-Schnittstelle, Normalisierung (Region, Typ, Stufe, Gültigkeit, Text), Fehlerbehandlung.
- **Nicht im Scope:** Radar (E18-03); Ereigniserzeugung (E18-08).
- **Abhängigkeiten:** E18-01, E18-05.
- **Acceptance Criteria:** Warnungen erscheinen normalisiert; API-Ausfall → letzter bekannter Stand + Health `degraded`, kein Absturz.
- **Tests:** Integration gegen aufgezeichnete DWD-Responses (Fixtures); Degradations-Fall.
- **Security-Auswirkung:** Nur ausgehende HTTPS zu DWD; keine Creds nötig.
- **HA-Auswirkung:** Abruf als Singleton (E04-08) empfohlen.
- **Permissions:** — · **Audit Events:** —

### E18-03 · DWD-Radar/Niederschlag-Adapter + Zeitleiste
**Epic:** 18 · **Phase:** 7 · **Area:** integration · **Branch:** feature/<nr>-dwd-radar
- **Ziel:** Radar-/Niederschlagsdaten inkl. Zeitleiste für das Zielgebiet.
- **Fachlicher Hintergrund:** MASTER_PROMPT §10/§13.12: „DWD Radar", „Radarzeitleiste".
- **Scope:** Client für die dokumentierten Radar-Produkte, Frame-Serie mit Zeitstempeln, Zuschnitt aufs Zielgebiet, Cache.
- **Nicht im Scope:** UI-Rendering (E18-09).
- **Abhängigkeiten:** E18-01, E18-06.
- **Acceptance Criteria:** Frame-Serie mit korrekten UTC-Zeitstempeln (ADR-0017); Cache begrenzt; Ausfall → letzte Frames + `degraded`.
- **Tests:** Integration mit Fixtures.
- **Security-Auswirkung:** — · **HA-Auswirkung:** Cache je Knoten. · **Permissions:** — · **Audit Events:** —

### E18-04 · Lokale-Messwerte-Adapter
**Epic:** 18 · **Phase:** 7 · **Area:** integration · **Branch:** feature/<nr>-dwd-observations
- **Ziel:** Aktuelle Messwerte (Temperatur, Wind, Niederschlag) für die Beispielorte.
- **Fachlicher Hintergrund:** MASTER_PROMPT §10: „lokale Messwerte".
- **Scope:** Client für DWD-Stationsmesswerte, Zuordnung Station↔Ort, Normalisierung, Aktualisierungsintervall.
- **Nicht im Scope:** Bewertungslogik (Operator im UI).
- **Abhängigkeiten:** E18-01, E18-05.
- **Acceptance Criteria:** Werte je Ort aktuell; fehlende Station → klar „keine Daten", kein Fehler.
- **Tests:** Integration mit Fixtures.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E18-05 · DB-Schema: weather_alerts, weather_observations
**Epic:** 18 · **Phase:** 7 · **Area:** db · **Branch:** feature/<nr>-schema-weather
- **Ziel:** Migration für persistierte Warnungen und Messwerte.
- **Fachlicher Hintergrund:** MASTER_PROMPT §14.
- **Scope:** `weather_alerts` (id, region, type, level, valid_from, valid_to, headline, description, source_ref, received_at), `weather_observations` (id, place, metric, value, unit, observed_at, station_ref).
- **Nicht im Scope:** — .
- **Abhängigkeiten:** —
- **Acceptance Criteria:** Migration up/down/up; Zeiten als `timestamptz`.
- **Tests:** Migration.
- **Security-Auswirkung:** — · **HA-Auswirkung:** expand-only. · **Permissions:** — · **Audit Events:** —

### E18-06 · Weather-Cache, Health-Status, Refresh-Scheduler
**Epic:** 18 · **Phase:** 7 · **Area:** backend · **Branch:** feature/<nr>-weather-cache-scheduler
- **Ziel:** Zentraler Refresh (Singleton) füllt Cache/DB; Health spiegelt Aktualität.
- **Fachlicher Hintergrund:** MASTER_PROMPT §10: „Aktualisierung, Health Status, Cache".
- **Scope:** Scheduler (via Leader-Election E04-08), Cache-TTL, Health (`ok/stale/degraded/down`), letzte erfolgreiche Aktualisierung je Datenart.
- **Nicht im Scope:** Adapter (E18-02..04).
- **Abhängigkeiten:** E04-08, E18-05.
- **Acceptance Criteria:** Nur ein Knoten refresht; Health wird `stale` nach überschrittener TTL; Recovery automatisch.
- **Tests:** Integration: TTL überschritten → `stale`; Leader-Failover → anderer Knoten refresht.
- **Security-Auswirkung:** — · **HA-Auswirkung:** Singleton-Refresh. · **Permissions:** — · **Audit Events:** —

### E18-07 · Weather-API fürs Frontend
**Epic:** 18 · **Phase:** 7 · **Area:** backend, api · **Branch:** feature/<nr>-weather-api
- **Ziel:** Endpoints für aktuelle Warnungen, Messwerte, Radar-Frames, Warnregionen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.12.
- **Scope:** `GET /weather/alerts`, `/weather/observations`, `/weather/radar`, `/weather/regions`; `weather.view` Pflicht.
- **Nicht im Scope:** Ereigniserzeugung (E18-08).
- **Abhängigkeiten:** E18-05, E18-06.
- **Acceptance Criteria:** `weather.view` erforderlich; Health-Status im Response-Header/Body; UTC-Zeiten.
- **Tests:** API: Rechte, Health-Feld, Formen.
- **Security-Auswirkung:** — · **HA-Auswirkung:** Read-only. · **Permissions:** `weather.view` · **Audit Events:** —

### E18-08 · WEATHER_EVENT_CREATED: Ereignis aus Wetterwarnung
**Epic:** 18 · **Phase:** 7 · **Area:** backend, api · **Branch:** feature/<nr>-weather-create-event
- **Ziel:** Aus einer Wetterwarnung entsteht auf Knopfdruck ein BBZ-Ereignis mit betrieblicher Bewertung.
- **Fachlicher Hintergrund:** MASTER_PROMPT §10/§13.12: „Erzeugung eines BBZ-Ereignisses aus einer Wetterwarnung".
- **Scope:** `POST /weather/alerts/{id}/create-event` (Priorität wählbar, Bewertungstext), `weather.create_event`, `WEATHER_EVENT_CREATED` + `EVENT_CREATED`, Verknüpfung Ereignis↔Warnung.
- **Nicht im Scope:** Auto-Erzeugung ohne Operator (bewusst nicht).
- **Abhängigkeiten:** E18-07, E03-06.
- **Acceptance Criteria:** `weather.create_event` Pflicht; idempotent (gleiche Command-Id → ein Ereignis); Ereignis referenziert die Warnung.
- **Tests:** API: Erzeugung, Idempotenz, Rechte.
- **Security-Auswirkung:** `weather.create_event`.
- **HA-Auswirkung:** Idempotent. · **Permissions:** `weather.view` `weather.create_event`
- **Audit Events:** `WEATHER_EVENT_CREATED` `EVENT_CREATED`.

### E18-09 · Wetterlage-UI-Seite (Radar-Zeitleiste, Warnungen, Werte, Bewertung, Ereignis erzeugen)
**Epic:** 18 · **Phase:** 7 · **Area:** frontend, a11y · **Branch:** feature/<nr>-ui-weather-page
- **Ziel:** Die Wetterlage-Seite gemäß §13.12.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.12: Mittelfranken, DWD Radar, Warnungen, Wetterwerte, betriebliche Bewertung, Wetterereignis erzeugen.
- **Scope:** Radar-Zeitleiste (Play/Scrub, tastaturbedienbar), Warnungsliste, Messwert-Kacheln je Ort, Bewertungsfeld, „Wetterereignis erzeugen"-Dialog (E18-08); Health-Anzeige bei veralteten Daten.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E18-07, E18-08, E07-13 (Topbar-Warnung greift auch hier).
- **Acceptance Criteria:** Radar-Zeitleiste ohne Maus bedienbar; veraltete Daten klar markiert; Ereigniserzeugung mit Bestätigung; a11y grün.
- **Tests:** Playwright: Radar scrubben (Tastatur), Warnung → Ereignis erzeugen.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `weather.view` `weather.create_event` · **Audit Events:** — (Server).

### E18-10 · DWD-Integrationstests (Fixtures) + Degraded-Verhalten
**Epic:** 18 · **Phase:** 7 · **Area:** integration, test · **Branch:** feature/<nr>-dwd-tests
- **Ziel:** Deterministische Tests gegen aufgezeichnete DWD-Antworten inkl. Ausfall-/Degraded-Pfade.
- **Fachlicher Hintergrund:** `.ai/TESTING.md` (integration adapters); MASTER_PROMPT §10 (Health).
- **Scope:** Fixture-Set, Tests für Parsing/Normalisierung/Cache/Health, Ausfall → `degraded`/`stale`, Recovery.
- **Nicht im Scope:** Live-DWD-Tests in CI (nur nightly optional).
- **Abhängigkeiten:** E18-02..06.
- **Acceptance Criteria:** Alle Adapterpfade + Degradation getestet; keine Netzabhängigkeit im PR-CI.
- **Tests:** ebendiese.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

---

# EPIC 19 · Weytec Monitor Routing

**Milestone:** `19 Weytec Monitor Routing` · **Phase:** 8 · **Ziel des Epics:**
Monitor-/KVM-Routing als eigene Integration: Domänenmodell (Inputs/Outputs/
3×2-Layout, BBZ-OS fix unten links), Routing-API, Layoutprofile, `monitor_mock`,
Weytec-Interface-Vorbereitung (keine erfundene API). Quellen: MASTER_PROMPT §9.

### E19-01 · DB-Schema: monitor_inputs, monitor_outputs, monitor_routes, monitor_profiles
**Epic:** 19 · **Phase:** 8 · **Area:** db · **Branch:** feature/<nr>-schema-monitor
- **Ziel:** Migration für das Monitor-Routing-Modell.
- **Fachlicher Hintergrund:** MASTER_PROMPT §9/§14.
- **Scope:** `monitor_inputs` (id, key, label — BBZ-OS, BKU1–4, CODA1/2), `monitor_outputs` (id, key, label — 6 Arbeitsplatzmonitore + Mittelmonitor/Großbild, position im 3×2), `monitor_routes` (output_id, input_id, set_by, set_at, profile_id?), `monitor_profiles` (id, name, scope user/workplace, layout jsonb).
- **Nicht im Scope:** Provider (E19-06/07).
- **Abhängigkeiten:** E02-01.
- **Acceptance Criteria:** Migration up/down/up; Positionen des 3×2-Layouts abbildbar; ein aktives Route je Output.
- **Tests:** Migration; Constraint „ein Input je Output".
- **Security-Auswirkung:** — · **HA-Auswirkung:** expand-only. · **Permissions:** — · **Audit Events:** —

### E19-02 · Monitor-Domänenmodell + Standard-Layout
**Epic:** 19 · **Phase:** 8 · **Area:** backend · **Branch:** feature/<nr>-monitor-domain
- **Ziel:** Domänenmodell mit Inputs/Outputs, 3×2-Arbeitsplatzlayout und einem definierten Standard-Layout.
- **Fachlicher Hintergrund:** MASTER_PROMPT §9: Layout 3×2, Standard-Layout, gespeicherte Layoutprofile.
- **Scope:** Domänenobjekte, Standard-Layout als Seed, Validierung erlaubter Input→Output-Zuordnungen.
- **Nicht im Scope:** Routing-Ausführung am Provider (E19-04).
- **Abhängigkeiten:** E19-01.
- **Acceptance Criteria:** Standard-Layout wiederherstellbar; ungültige Zuordnung → Domänenfehler.
- **Tests:** Unit: Standard-Layout, Validierung.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E19-03 · Feste Regel: unten links immer BBZ-OS (serverseitig erzwungen)
**Epic:** 19 · **Phase:** 8 · **Area:** backend · **Branch:** feature/<nr>-monitor-fixed-rule
- **Ziel:** Der Output „unten links" ist unveränderlich auf Input `BBZ-OS` gebunden — der Server lehnt abweichende Routen ab.
- **Fachlicher Hintergrund:** MASTER_PROMPT §9: „Feste Regel: Monitor unten links bleibt immer BBZ-OS."
- **Scope:** Invariante im Routing-Service, klare Fehlermeldung, kein UI-Bypass.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E19-02.
- **Acceptance Criteria:** Route-Versuch, der den Unten-links-Output umbelegt → abgelehnt (auch via API direkt); Standard-Reset behält die Regel.
- **Tests:** API: Umbelegung abgelehnt; Reset respektiert Regel.
- **Security-Auswirkung:** Server-Enforcement (nicht nur UI).
- **HA-Auswirkung:** — · **Permissions:** `monitor.route` · **Audit Events:** —

### E19-04 · Routing-API + MONITOR_ROUTE_CHANGED
**Epic:** 19 · **Phase:** 8 · **Area:** backend, api · **Branch:** feature/<nr>-monitor-routing-api
- **Ziel:** Routen setzen, auf Standard zurücksetzen — als auditierte, idempotente Commands, umgesetzt am aktiven Provider.
- **Fachlicher Hintergrund:** MASTER_PROMPT §9/§17 (Monitorrouting ist kritische Aktion → Audit).
- **Scope:** `PUT /monitor/routes` (Batch), `POST /monitor/routes/reset-standard`, Umsetzung über Provider (E19-06/07), `MONITOR_ROUTE_CHANGED` + Audit.
- **Nicht im Scope:** UI (E19-08).
- **Abhängigkeiten:** E19-02, E19-03, E19-06.
- **Acceptance Criteria:** `monitor.route` bzw. `monitor.reset_standard` Pflicht; doppelter Command → keine zweite Provider-Aktion; jede Änderung auditiert.
- **Tests:** API gegen `monitor_mock`: Route setzen, Reset, Idempotenz, Rechte, Audit.
- **Security-Auswirkung:** kritische Aktion → Audit.
- **HA-Auswirkung:** Idempotent; Provider-Aktion über Outbox falls extern.
- **Permissions:** `monitor.view/route/reset_standard`
- **Audit Events:** `MONITOR_ROUTE_CHANGED` (Pflicht-Audit).

### E19-05 · Layoutprofile: speichern/laden, user- & arbeitsplatzbezogen
**Epic:** 19 · **Phase:** 8 · **Area:** backend, api · **Branch:** feature/<nr>-monitor-profiles
- **Ziel:** Benutzer-/arbeitsplatzbezogene Layoutprofile speichern und anwenden.
- **Fachlicher Hintergrund:** MASTER_PROMPT §9: „gespeicherte Layoutprofile, Nutzer-/Arbeitsplatzbezogene Layouts".
- **Scope:** CRUD `/monitor/profiles`, Anwenden eines Profils (→ Routing-API), Scope (user/workplace), `monitor.manage_profiles`.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E19-04.
- **Acceptance Criteria:** Profil anwenden respektiert die Unten-links-Regel; user-Profil nur für den User sichtbar; workplace-Profil für den Arbeitsplatz.
- **Tests:** API: CRUD, Anwenden, Scope-Sichtbarkeit.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `monitor.manage_profiles` · **Audit Events:** `MONITOR_PROFILE_APPLIED`.

### E19-06 · `monitor_mock`-Provider (vollständig)
**Epic:** 19 · **Phase:** 8 · **Area:** integration, test · **Branch:** feature/<nr>-monitor-mock-full
- **Ziel:** Der Mock setzt Routen deterministisch um und meldet Zustände zurück.
- **Fachlicher Hintergrund:** MASTER_PROMPT §9: „Provider 1: monitor_mock".
- **Scope:** Provider-Interface (route/get_state/health), simulierte Fehler (Output nicht erreichbar), deterministische Antworten.
- **Nicht im Scope:** Weytec (E19-07).
- **Abhängigkeiten:** E19-02.
- **Acceptance Criteria:** Alle Interface-Methoden; Fehlersimulation; genutzt in E19-10.
- **Tests:** Provider-Konformität.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E19-07 · `monitor_weytec`-Scaffold + Capability-Interface + Blocker-Doku
**Epic:** 19 · **Phase:** 8 · **Area:** integration, documentation · **Branch:** feature/<nr>-monitor-weytec-scaffold
- **Ziel:** Integrations-Scaffold + normalisiertes Interface für Weytec, ohne erfundene API.
- **Fachlicher Hintergrund:** MASTER_PROMPT §9: „Weytec-API nicht erfinden. Nur Interface vorbereiten, bis Dokumentation vorliegt."
- **Scope:** `integrations/monitor_weytec/` (manifest, config_schema, adapter-Stub mit `NotImplementedError`), `docs/` Blocker mit „Pending: Weytec API documentation" (schon in `.ai/CURRENT_STATE.md` „Open external dependencies").
- **Nicht im Scope:** Echte Anbindung.
- **Abhängigkeiten:** E19-06 (gemeinsames Interface).
- **Acceptance Criteria:** Manifest validiert; Adapter ehrlich als Stub gelabelt; Blocker referenziert.
- **Tests:** Manifest-Schema.
- **Security-Auswirkung:** verhindert Fehlannahmen. · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E19-08 · Monitor-Routing-Dialog-UI (Drag & Drop + Tastatur/Select-Alternative)
**Epic:** 19 · **Phase:** 8 · **Area:** frontend, a11y · **Branch:** feature/<nr>-ui-monitor-dialog
- **Ziel:** Der Monitor-Layout-Button öffnet einen Dialog mit Drag & Drop UND vollständiger tastatur-/select-basierter Alternative; Standard-Layout-Button.
- **Fachlicher Hintergrund:** MASTER_PROMPT §9/§26.14: „Bedienung darf nicht ausschließlich auf Drag & Drop beruhen."
- **Scope:** 3×2-Rasterdarstellung + Großbild, Zuordnung per Drag oder per Select/Tastatur, Standard-Layout-Button, Profil speichern/laden, Unten-links-Feld gesperrt dargestellt.
- **Nicht im Scope:** Backend (E19-04/05).
- **Abhängigkeiten:** E19-04, E19-05, E07-03.
- **Acceptance Criteria:** Komplette Bedienung ohne Maus möglich; Unten-links nicht änderbar (UI + Server); a11y grün.
- **Tests:** Playwright: Route per Tastatur ändern; Standard-Reset; BBZ-OS-Feld gesperrt.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `monitor.view/route/reset_standard/manage_profiles` · **Audit Events:** — (Server).

### E19-09 · Monitor-Permissions-Seed
**Epic:** 19 · **Phase:** 8 · **Area:** db · **Branch:** feature/<nr>-monitor-permissions-seed
- **Ziel:** `monitor.view/route/reset_standard/manage_profiles` im Katalog und Rollen zugeordnet.
- **Fachlicher Hintergrund:** `docs/domain/permission-catalog.md` (Monitor-Zeile).
- **Scope:** Daten-Migration + Default-Mapping (z. B. Disponent: route; Sichtleiter: alles).
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E02-14, E19-01.
- **Acceptance Criteria:** Vier Keys vorhanden; „Nur Lesen" ≤ `monitor.view`.
- **Tests:** Migration up/down; Mapping-Assertion.
- **Security-Auswirkung:** Least-Privilege. · **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E19-10 · Monitor-Routing-E2E
**Epic:** 19 · **Phase:** 8 · **Area:** test · **Branch:** feature/<nr>-e2e-monitor-routing
- **Ziel:** Routing-Änderung, Standard-Reset, BBZ-OS-Invariante und Profil-Save/Load laufen automatisiert grün.
- **Fachlicher Hintergrund:** MASTER_PROMPT §9; `.ai/TESTING.md`.
- **Scope:** Playwright über Compose + `monitor_mock`: Route ändern → am Mock reflektiert + Audit; Standard-Reset; Umbelegung unten links abgelehnt; Profil speichern/anwenden.
- **Nicht im Scope:** Weytec.
- **Abhängigkeiten:** E19-04, E19-05, E19-08.
- **Acceptance Criteria:** Alle vier Szenarien grün inkl. Audit.
- **Tests:** ebendiese E2E.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** div. · **Audit Events:** verifiziert.

---

# EPIC 20 · Archive / Postprocessing

**Milestone:** `20 Archive / Postprocessing` · **Phase:** 1+ · **Ziel des Epics:**
Archivierte Ereignisse vollständig einsehbar halten, Nachbearbeitung/Notizen,
sichere Reaktivierung, Export, dokumentierte Aufbewahrung — ohne Hard-Delete.
Quellen: MASTER_PROMPT §13.6/§13.11/§17/§26.7.

### E20-01 · Archiv-Detailmodell (event_archive / erweitertes Detail)
**Epic:** 20 · **Phase:** 1 · **Area:** db, backend · **Branch:** feature/<nr>-archive-detail-model
- **Ziel:** Ein Ereignis behält im Archiv seine vollständige Historie; das Detailmodell bündelt Status, Notizen, Workflow-Ergebnisse, Calls, Audit-Referenzen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.6: „vollständig detailliert einsehbar".
- **Scope:** Entscheidung „event_archive-Tabelle vs. Sicht auf events + Historie" (dokumentiert), Detail-Aggregatorabfrage, keine Datenreduktion beim Archivieren.
- **Nicht im Scope:** UI (E07-11).
- **Abhängigkeiten:** E03-01, E03-16.
- **Acceptance Criteria:** Archiviertes Ereignis liefert dieselbe Detailtiefe wie ein aktives; nichts wird beim Archivieren gelöscht.
- **Tests:** Integration: Detailtiefe aktiv vs. archiviert identisch.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `events.view` · **Audit Events:** —

### E20-02 · Archiv-Listen-API (chronologisch inkl. archiviert, Filter)
**Epic:** 20 · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-archive-list-api
- **Ziel:** `GET /events` (chronologisch inkl. archiviert) mit Filtern für die Archiv-Ansicht.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.6.
- **Scope:** Erweiterung von E03-12 um Archiv-Filter (Datum, Priorität, BBZ, Verantwortlicher), stabile Pagination.
- **Nicht im Scope:** Export (E20-06).
- **Abhängigkeiten:** E03-12.
- **Acceptance Criteria:** archivierte Ereignisse hier sichtbar, aber nicht in `queue=active`; scope-gefiltert.
- **Tests:** API: Filter, Abgrenzung zur Work-Queue.
- **Security-Auswirkung:** Scope. · **HA-Auswirkung:** Read-only. · **Permissions:** `events.view` · **Audit Events:** —

### E20-03 · Archiv-Detail-API (volle Historie)
**Epic:** 20 · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-archive-detail-api
- **Ziel:** `GET /events/{id}` liefert für archivierte Ereignisse die komplette Historie (Status, Notizen, Workflow, Calls, Audit-Referenzen).
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.6.
- **Scope:** Detail-Endpoint um Archiv-Aggregation erweitern (E20-01), Verweise auf Audit-Einträge (Query via E04-04).
- **Nicht im Scope:** UI.
- **Abhängigkeiten:** E20-01.
- **Acceptance Criteria:** Vollständige, deterministisch geordnete Historie; `events.view` + Scope.
- **Tests:** API: Vollständigkeit/Ordnung.
- **Security-Auswirkung:** Scope. · **HA-Auswirkung:** Read-only. · **Permissions:** `events.view` · **Audit Events:** —

### E20-04 · Nachbearbeitungsnotizen (events.postprocess), versioniert
**Epic:** 20 · **Phase:** 1 · **Area:** backend, api · **Branch:** feature/<nr>-postprocess-notes
- **Ziel:** An archivierten Ereignissen sind Nachbearbeitungsnotizen möglich; Änderungen sind nachvollziehbar.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.6: „Nachbearbeitungsnotizen möglich".
- **Scope:** `POST /events/{id}/notes` (kind `postprocess`), Versionierung/Historie der Notiz, `events.postprocess`.
- **Nicht im Scope:** Arbeitsnotizen (E03-16).
- **Abhängigkeiten:** E03-16.
- **Acceptance Criteria:** Notiz nur mit `events.postprocess`; jede Änderung erzeugt `EVENT_NOTE_ADDED`/`EVENT_NOTE_UPDATED` + Audit; alte Fassungen bleiben erhalten.
- **Tests:** API: Notiz anlegen/ändern, Historie, Rechte.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** `events.postprocess` · **Audit Events:** `EVENT_NOTE_ADDED` `EVENT_NOTE_UPDATED`.

### E20-05 · Reaktivierungs-Flow finalisieren (Confirm-Token, zurück in die Queue)
**Epic:** 20 · **Phase:** 1 · **Area:** backend · **Branch:** feature/<nr>-reactivation-finalize
- **Ziel:** Reaktivierung ist serverseitig zweistufig abgesichert und bringt das Ereignis sauber zurück in die Arbeitswarteschlange.
- **Fachlicher Hintergrund:** MASTER_PROMPT §13.6/§26.8; ergänzt E03-11.
- **Scope:** Confirm-Token/Doppelbestätigung serverseitig, Pflicht-Grund, Wiedereintritt in `queue=active`, `EVENT_REACTIVATED`-Audit mit Grund; Rate-Limit gegen versehentliche Serien.
- **Nicht im Scope:** UI (E07-12).
- **Abhängigkeiten:** E03-11.
- **Acceptance Criteria:** Kein Pfad reaktiviert ohne Confirm + Grund; reaktiviertes Ereignis erscheint wieder in der Work-Queue; Pflicht-Audit.
- **Tests:** API: ohne Confirm/Grund → abgelehnt; mit → zurück in Queue + Audit.
- **Security-Auswirkung:** `events.reactivate`; Doppelabsicherung.
- **HA-Auswirkung:** Idempotent. · **Permissions:** `events.reactivate` · **Audit Events:** `EVENT_REACTIVATED` (Pflicht-Audit mit Grund).

### E20-06 · Export: Ereignis + Audit + Workflow-Bündel (JSON/PDF)
**Epic:** 20 · **Phase:** 1+ · **Area:** backend, api · **Branch:** feature/<nr>-event-export-bundle
- **Ziel:** `events.export` erzeugt ein vollständiges, konsistentes Bündel (JSON immer, PDF optional) eines Ereignisses.
- **Fachlicher Hintergrund:** MASTER_PROMPT §12 `events.export`; §17 Nachvollziehbarkeit.
- **Scope:** Aggregation Ereignis + Statushistorie + Notizen + Workflow-Ergebnisse + zugehörige Calls + Audit-Einträge; deterministische Ordnung; PDF-Renderer (serverseitig) optional hinter Feature-Flag.
- **Nicht im Scope:** Bulk-Export.
- **Abhängigkeiten:** E03-16, E20-03, E04-04.
- **Acceptance Criteria:** `events.export` Pflicht; JSON-Bündel vollständig + reproduzierbar; Export selbst auditiert (`EVENT_EXPORTED`).
- **Tests:** API: Vollständigkeit, Determinismus, Rechte, Audit.
- **Security-Auswirkung:** Bündel enthält sensible Daten → strenge Rechte/Scope; kein DTMF-Klartext (E17-06).
- **HA-Auswirkung:** Read-only. · **Permissions:** `events.export` `system.audit.view` · **Audit Events:** `EVENT_EXPORTED`.

### E20-07 · Aufbewahrungsrichtlinie (kein Hard-Delete) + Doku
**Epic:** 20 · **Phase:** 1+ · **Area:** backend, documentation · **Branch:** feature/<nr>-retention-policy
- **Ziel:** Eine konfigurierbare Aufbewahrungsrichtlinie, die archivierte Ereignisse und Audit niemals hart löscht.
- **Fachlicher Hintergrund:** MASTER_PROMPT §26.7: „Keine archivierten Ereignisse hart löschen"; §17 Audit nie hart löschen.
- **Scope:** Policy-Konfiguration (Aufbewahrungsfristen für ableitbare/nicht-essenzielle Daten wie Radar-Frames — NICHT für Ereignisse/Audit), Doku in `docs/`, expliziter Guard „kein DELETE auf events/audit_events".
- **Nicht im Scope:** WORM-Storage (Epic 23).
- **Abhängigkeiten:** E04-10.
- **Acceptance Criteria:** Kein Codepfad löscht Ereignisse/Audit; Doku beschreibt, was überhaupt wie lange aufbewahrt/bereinigt wird.
- **Tests:** Contract-Test „kein DELETE auf events/audit_events/domain_events".
- **Security-Auswirkung:** Revisionssicherheit.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E20-08 · Archiv/Postprocessing-E2E
**Epic:** 20 · **Phase:** 1+ · **Area:** test · **Branch:** feature/<nr>-e2e-archive
- **Ziel:** Archivieren → Detail ansehen → Nachbearbeitungsnotiz → Export → Reaktivierung mit Bestätigung laufen automatisiert grün.
- **Fachlicher Hintergrund:** MASTER_PROMPT §24 (Schritte 8–10) + §13.6.
- **Scope:** Playwright über Compose; Assertions inkl. Audit + „kein Hard-Delete".
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E20-02..06, E07-11, E07-12.
- **Acceptance Criteria:** Alle Schritte grün; Reaktivierung nur nach Bestätigung; Export vollständig.
- **Tests:** ebendiese E2E.
- **Security-Auswirkung:** — · **HA-Auswirkung:** — · **Permissions:** div. · **Audit Events:** verifiziert.

---

# EPIC 21 · Enterprise Authentication

**Milestone:** `21 Enterprise Authentication` · **Phase:** 9 · **Ziel des Epics:**
Entra ID / OIDC, LDAP/AD, MFA-Policy, WebAuthn und erweiterte RBAC-Bedingungen —
lokale Accounts bleiben immer möglich. Quellen: MASTER_PROMPT §11, `.ai/SECURITY.md`.

### E21-01 · Entra ID / OIDC-Provider (PKCE, State, Nonce, Token-Validierung)
**Epic:** 21 · **Phase:** 9 · **Area:** backend, security · **Branch:** feature/<nr>-oidc-provider
- **Ziel:** `entra_oidc` als voll funktionsfähiger Auth-Provider mit Authorization-Code-Flow + PKCE.
- **Fachlicher Hintergrund:** MASTER_PROMPT §11/§22; `.ai/SECURITY.md` „PKCE for OIDC".
- **Scope:** OIDC-Discovery, PKCE, `state`/`nonce`, ID-Token-Signaturprüfung (JWKS-Rotation), Claim→User-Mapping, Redirect-Endpoints, Fehler-/Abbruchpfade.
- **Nicht im Scope:** Gruppen-Mapping (E21-02); MFA-Policy (E21-05).
- **Abhängigkeiten:** E02-04, E02-05.
- **Acceptance Criteria:** Login gegen Test-IdP erfolgreich; manipuliertes/abgelaufenes Token → abgelehnt; `state`/`nonce`-Mismatch → abgelehnt; lokale Logins weiterhin möglich.
- **Tests:** Integration gegen Mock-IdP; Negativfälle.
- **Security-Auswirkung:** Standardkonformer OIDC-Flow; keine impliziten Grants.
- **HA-Auswirkung:** `state`/PKCE-Verifier in gemeinsamem Store (etcd/DB), damit Redirect nach Failover funktioniert.
- **Permissions:** — · **Audit Events:** `LOGIN_SUCCEEDED` (provider=entra_oidc) `LOGIN_FAILED`.

### E21-02 · OIDC-Gruppen-/Rollen-Mapping + JIT-Provisioning-Policy
**Epic:** 21 · **Phase:** 9 · **Area:** backend · **Branch:** feature/<nr>-oidc-group-mapping
- **Ziel:** IdP-Gruppen/Claims werden auf BBZ-Rollen/Gruppen abgebildet; neue User werden nach Policy just-in-time angelegt.
- **Fachlicher Hintergrund:** MASTER_PROMPT §11/§12.
- **Scope:** Mapping-Konfiguration (Claim/Gruppe → BBZ-Rolle/Gruppe), JIT-Provisioning (an/aus, Default-Rolle), Deprovisioning-Verhalten bei entfallener Gruppe.
- **Nicht im Scope:** Directory-Sync (E21-04).
- **Abhängigkeiten:** E21-01, E02-02.
- **Acceptance Criteria:** Gruppenwechsel im IdP wirkt beim nächsten Login; JIT-User erhält nur die gemappten Rechte; Mapping-Änderung auditiert.
- **Tests:** Integration: verschiedene Claim-Sets → erwartete Rollen.
- **Security-Auswirkung:** Verhindert Rechteausweitung über falsches Mapping.
- **HA-Auswirkung:** DB-basiert. · **Permissions:** `roles.manage` · **Audit Events:** `AUTH_MAPPING_CHANGED` `USER_ROLE_ASSIGNED`.

### E21-03 · LDAP/AD-Provider (Bind, Suche, Gruppen-Mapping, Pooling)
**Epic:** 21 · **Phase:** 9 · **Area:** backend, security · **Branch:** feature/<nr>-ldap-provider
- **Ziel:** `ldap_ad` als Auth-Provider mit Bind-Authentifizierung und Gruppenauflösung.
- **Fachlicher Hintergrund:** MASTER_PROMPT §11.
- **Scope:** LDAP-Client (LDAPS/StartTLS erzwungen), Service-Account-Bind + User-Bind, Gruppen-Suche, Connection-Pool, Timeouts/Retry.
- **Nicht im Scope:** Sync (E21-04).
- **Abhängigkeiten:** E02-04, E02-05.
- **Acceptance Criteria:** Login gegen Test-LDAP erfolgreich; nur verschlüsselte Verbindungen; Service-Account-Creds als Secret.
- **Tests:** Integration gegen containerisiertes Test-LDAP; TLS-Zwang.
- **Security-Auswirkung:** Keine Klartext-LDAP-Verbindung; Service-Account Least Privilege.
- **HA-Auswirkung:** Pool je Knoten; LDAP-Ausfall → lokale Logins weiter möglich.
- **Permissions:** — · **Audit Events:** `LOGIN_SUCCEEDED` (provider=ldap_ad) `LOGIN_FAILED`.

### E21-04 · Directory-Sync-Job (LDAP/Entra), geplant + auditiert
**Epic:** 21 · **Phase:** 9 · **Area:** backend · **Branch:** feature/<nr>-directory-sync
- **Ziel:** Ein geplanter Singleton-Job synchronisiert Benutzer/Gruppen aus dem Verzeichnis.
- **Fachlicher Hintergrund:** MASTER_PROMPT §11 „advanced RBAC"; Betrieb.
- **Scope:** Sync über Leader-Election (E04-08), Diff-Erkennung, Deaktivierung entfallener Accounts (kein Hard-Delete), Reporting, Trockenlauf-Modus.
- **Nicht im Scope:** SCIM/Echtzeit-Provisioning.
- **Abhängigkeiten:** E21-02, E21-03, E04-08.
- **Acceptance Criteria:** Sync deaktiviert entfallene User (soft), legt neue an, aktualisiert Gruppen; jeder Lauf auditiert; Trockenlauf ändert nichts.
- **Tests:** Integration: Diff-Szenarien.
- **Security-Auswirkung:** verlässliches Offboarding; kein Datenverlust (soft).
- **HA-Auswirkung:** Singleton-Job. · **Permissions:** `users.manage` · **Audit Events:** `DIRECTORY_SYNC_COMPLETED` `USER_DEACTIVATED`.

### E21-05 · MFA-Policy-Engine (rollen-/scopebasierte MFA-Pflicht, Step-up)
**Epic:** 21 · **Phase:** 9 · **Area:** backend, security · **Branch:** feature/<nr>-mfa-policy
- **Ziel:** Konfigurierbare Regel „welche Rolle/welcher Scope erfordert MFA", plus Step-up-Auth für kritische Aktionen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §11 „MFA / 2FA"; §22.
- **Scope:** Policy-Modell (Rolle/Scope → MFA required), Enforcement im Login + optional bei definierten Aktionen (Step-up), Grace-Period-Konfiguration.
- **Nicht im Scope:** TOTP-Mechanik (E02-13); WebAuthn (E21-06).
- **Abhängigkeiten:** E02-13, E02-08.
- **Acceptance Criteria:** User in MFA-pflichtiger Rolle ohne zweiten Faktor → Zugriff verweigert; Step-up greift bei markierten Aktionen; Policy-Änderung auditiert.
- **Tests:** Integration: MFA-Pflicht je Rolle; Step-up bei kritischer Aktion.
- **Security-Auswirkung:** erzwingt starke Auth für privilegierte Rollen.
- **HA-Auswirkung:** Policy in DB. · **Permissions:** `permissions.manage` · **Audit Events:** `MFA_POLICY_CHANGED` `MFA_STEPUP_REQUIRED`.

### E21-06 · WebAuthn/FIDO2 für lokale Accounts
**Epic:** 21 · **Phase:** 9 · **Area:** backend, security · **Branch:** feature/<nr>-webauthn
- **Ziel:** Lokale User können einen FIDO2-Authenticator registrieren und als Faktor nutzen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §11: „WebAuthn vorbereiten".
- **Scope:** Registrierung/Assertion (WebAuthn L2), Credential-Speicher, Recovery, Einbindung in die MFA-Policy.
- **Nicht im Scope:** passwortloser Erstfaktor als Default.
- **Abhängigkeiten:** E02-05, E21-05.
- **Acceptance Criteria:** Registrierung + Login mit Authenticator; Recovery-Pfad; Credentials je User isoliert.
- **Tests:** Integration mit virtuellem Authenticator (CDP).
- **Security-Auswirkung:** phishing-resistenter Faktor.
- **HA-Auswirkung:** Credentials in DB. · **Permissions:** — · **Audit Events:** `WEBAUTHN_REGISTERED` `WEBAUTHN_REMOVED`.

### E21-07 · Erweiterte RBAC: Bedingungen, zeitgebundene Grants, Delegation
**Epic:** 21 · **Phase:** 9 · **Area:** backend · **Branch:** feature/<nr>-advanced-rbac
- **Ziel:** Permissions können optionale Bedingungen (Rule DSL), Gültigkeitszeiträume und Delegation tragen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §12 „optionale Bedingungen"; §11 „advanced RBAC".
- **Scope:** `role_permissions.condition_json` produktiv auswerten (E02-07 nutzte Feature-Flag), `valid_from`/`valid_to` an Grants, temporäre Delegation eines Rechts mit Ablauf + Audit.
- **Nicht im Scope:** Genehmigungs-Workflows für Delegationen.
- **Abhängigkeiten:** E02-07, E05-01.
- **Acceptance Criteria:** abgelaufener Grant wirkt nicht mehr; Bedingung nicht erfüllt → deny; Delegation zeitlich begrenzt + auditiert; Entzug sofort wirksam.
- **Tests:** Unit/Integration: Zeitfenster, Bedingungen, Delegation/Entzug.
- **Security-Auswirkung:** feiner steuerbare, nachvollziehbare Rechte.
- **HA-Auswirkung:** DB-basiert; Serverzeit. · **Permissions:** `permissions.manage` `roles.manage` · **Audit Events:** `PERMISSION_DELEGATED` `PERMISSION_DELEGATION_REVOKED`.

### E21-08 · Account-Linking (lokal + extern) & Auth-Provider-Admin-UI
**Epic:** 21 · **Phase:** 9 · **Area:** backend, frontend · **Branch:** feature/<nr>-account-linking-admin-ui
- **Ziel:** Ein User kann mehrere `auth_identities` haben (lokal + Entra); Admins konfigurieren Provider/Mapping in der UI.
- **Fachlicher Hintergrund:** MASTER_PROMPT §11: „Lokale Benutzer müssen weiterhin möglich bleiben."
- **Scope:** Verknüpfen/Trennen von Identitäten (mit Re-Auth), Admin-UI für Provider-Konfiguration + Gruppen-Mapping + MFA-Policy.
- **Nicht im Scope:** Self-Service-Provider-Registrierung.
- **Abhängigkeiten:** E21-01, E21-02, E21-05.
- **Acceptance Criteria:** Verknüpfen erfordert Bestätigung beider Faktoren; Trennen der letzten Identität eines aktiven Admins verhindert; UI-Änderungen auditiert.
- **Tests:** Integration + Playwright: Link/Unlink; „letzte Identität"-Schutz.
- **Security-Auswirkung:** verhindert Aussperren; kontrolliertes Identitäts-Management.
- **HA-Auswirkung:** — · **Permissions:** `users.manage` `roles.manage` `permissions.manage` · **Audit Events:** `IDENTITY_LINKED` `IDENTITY_UNLINKED` `AUTH_PROVIDER_CONFIGURED`.

---

# EPIC 22 · Monitoring / Observability

**Milestone:** `22 Monitoring / Observability` · **Phase:** fortlaufend · **Ziel des
Epics:** Durchgängige Beobachtbarkeit: OpenTelemetry-Traces, Prometheus-Metriken,
strukturierte Logs, Integration-Health-Aggregation, Alerting, Dashboards.
Quellen: MASTER_PROMPT §23, ADR-0008.

### E22-01 · OpenTelemetry-Verdrahtung (Traces, correlation_id ↔ trace_id)
**Epic:** 22 · **Phase:** fortlaufend · **Area:** backend, infra · **Branch:** feature/<nr>-otel-traces
- **Ziel:** Aus dem No-Op-OTel-Seam wird echtes Tracing; `correlation_id` und `trace_id` verknüpft.
- **Fachlicher Hintergrund:** MASTER_PROMPT §6 „OpenTelemetry vorbereiten"; ADR-0008.
- **Scope:** OTel-SDK-Init, Auto-Instrumentierung (FastAPI, SQLAlchemy, httpx), OTLP-Exporter (default aus), Span-Attribute, Verknüpfung zu `correlation_id` (E04-09).
- **Nicht im Scope:** Collector-Deployment (E22-07).
- **Abhängigkeiten:** E04-09.
- **Acceptance Criteria:** ein Request erzeugt einen zusammenhängenden Trace API→DB→Outbox; `trace_id` im Log; Exporter abschaltbar ohne Codeänderung.
- **Tests:** Integration: Trace-Struktur; Log enthält `trace_id`.
- **Security-Auswirkung:** keine sensiblen Daten in Span-Attributen (Redaction).
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E22-02 · Prometheus-Metriken (voller §23-Satz)
**Epic:** 22 · **Phase:** fortlaufend · **Area:** backend · **Branch:** feature/<nr>-prometheus-metrics
- **Ziel:** `/metrics` liefert API-Latency, DB-State, Replication-Lag, aktiver Server, verbundene Clients, WS-Verbindungen, pending Offline-Commands, Call-Line-Status, Integration-Health.
- **Fachlicher Hintergrund:** MASTER_PROMPT §23.
- **Scope:** Metrik-Registry, Histogramme/Gauges/Counters, sparsame Labels, Endpoint zugriffsbeschränkt; erweitert E06-13.
- **Nicht im Scope:** Dashboards (E22-07).
- **Abhängigkeiten:** E06-13.
- **Acceptance Criteria:** alle §23-Metriken vorhanden + dokumentiert; Endpoint nicht öffentlich; niedrige Kardinalität.
- **Tests:** Integration: Metriken unter Last/Failover plausibel.
- **Security-Auswirkung:** Endpoint geschützt.
- **HA-Auswirkung:** Frühwarnung. · **Permissions:** `system.cluster.view` · **Audit Events:** —

### E22-03 · Strukturierte-Log-Pipeline (JSON, Level, Shipping, keine Secrets)
**Epic:** 22 · **Phase:** fortlaufend · **Area:** backend, infra · **Branch:** feature/<nr>-log-pipeline
- **Ziel:** Einheitliche JSON-Logs mit Korrelations-/Trace-Feldern, konfigurierbarem Level, optionalem Shipping.
- **Fachlicher Hintergrund:** MASTER_PROMPT §6/§22.
- **Scope:** structlog finalisieren (ts, level, event, correlation_id, trace_id, node_id, user_id), Redaction-Filter (Passwörter, Tokens, DTMF), Shipping-Adapter, Sampling für laute Pfade.
- **Nicht im Scope:** Log-Backend-Betrieb.
- **Abhängigkeiten:** E22-01.
- **Acceptance Criteria:** kein Log-Eintrag enthält Secrets (Redaction-Test); Level pro Modul steuerbar; Felder konsistent.
- **Tests:** Unit: Redaction; Integration: Feldkonsistenz.
- **Security-Auswirkung:** verhindert Secret-Leak über Logs.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E22-04 · `/health/details`-Anreicherung (Dependency-Matrix, Build-Info)
**Epic:** 22 · **Phase:** fortlaufend · **Area:** backend · **Branch:** feature/<nr>-health-details-enrich
- **Ziel:** `/health/details` zeigt je Abhängigkeit einen Status + Build-/Versionsinfo.
- **Fachlicher Hintergrund:** MASTER_PROMPT §23.
- **Scope:** Dependency-Checks aggregieren, Build-Metadaten (git-SHA, Version, Build-Zeit), Antwortzeit je Check.
- **Nicht im Scope:** `/cluster/status` (E06-04).
- **Abhängigkeiten:** E06-04.
- **Acceptance Criteria:** jede Kernabhängigkeit mit Status; Build-Info korrekt; kein Secret im Body.
- **Tests:** Integration: Abhängigkeit ausfallen lassen → Status spiegelt es.
- **Security-Auswirkung:** `system.cluster.view`; keine internen Details.
- **HA-Auswirkung:** Diagnose. · **Permissions:** `system.cluster.view` · **Audit Events:** —

### E22-05 · Integration-Health-Aggregation-API + Modell
**Epic:** 22 · **Phase:** fortlaufend · **Area:** backend, api · **Branch:** feature/<nr>-integration-health-api
- **Ziel:** Einheitliche Sicht auf alle Integrationen (Telefonie, CUCM, Coda, DWD, Monitor, BKU-Agents) mit Status/Kennzahlen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §23; §8.14; `.ai/INTEGRATIONS_CODA_VIDEO.md`.
- **Scope:** `integration_health`-Modell (§14), `GET /integrations/health` aggregiert Status + letzte-Aktivität + Fehlerzähler; einheitliches Schema.
- **Nicht im Scope:** Deep-Diagnostics je Integration.
- **Abhängigkeiten:** E12-15, E16-10.
- **Acceptance Criteria:** alle aktiven Integrationen erscheinen; Status konsistent (`ok/degraded/down/disabled`); `integrations.diagnostics` Pflicht.
- **Tests:** Integration: Störung spiegelt sich.
- **Security-Auswirkung:** keine Secrets. · **HA-Auswirkung:** — · **Permissions:** `integrations.view` `integrations.diagnostics` · **Audit Events:** —

### E22-06 · Alerting-Regeln-Baseline
**Epic:** 22 · **Phase:** fortlaufend · **Area:** infra · **Branch:** feature/<nr>-alerting-rules
- **Ziel:** Vordefinierte Alerts: Cluster degraded, Replication-Lag hoch, Quorumverlust, Integration down, Outbox-Backlog, viele pending Offline-Commands.
- **Fachlicher Hintergrund:** MASTER_PROMPT §23.
- **Scope:** Prometheus-Alert-Rules (YAML), Schwellen dokumentiert, Alert→Runbook-Verweis, `promtool`-Tests.
- **Nicht im Scope:** Alertmanager-Routing (Betrieb).
- **Abhängigkeiten:** E22-02.
- **Acceptance Criteria:** jede Regel hat Schwelle + Runbook-Link; Regeln valid (promtool); simulierte Werte lösen aus.
- **Tests:** `promtool test rules`.
- **Security-Auswirkung:** — · **HA-Auswirkung:** operative Früherkennung. · **Permissions:** — · **Audit Events:** —

### E22-07 · Collector-Deployment + Dashboards + SLO-Doku
**Epic:** 22 · **Phase:** fortlaufend · **Area:** infra, documentation · **Branch:** feature/<nr>-telemetry-deploy-dashboards
- **Ziel:** Optionaler OTel-Collector + Grafana-Dashboards (Cluster/Telefonie/Trigger) + „was heißt healthy"-Doku.
- **Fachlicher Hintergrund:** MASTER_PROMPT §20 „optional telemetry collector"; §23.
- **Scope:** Collector als Deploy-Profil (opt-in, nicht auf Quorum), Grafana-Dashboard-JSON im Repo, SLO/Runbook-Doku je Kernkomponente.
- **Nicht im Scope:** Betrieb der Monitoring-Infrastruktur.
- **Abhängigkeiten:** E22-01, E22-02, E22-06.
- **Acceptance Criteria:** Collector-Profil startbar in Compose; Dashboards laden gegen die Metriken; Doku beschreibt Ziel-SLOs.
- **Tests:** Compose-Smoke; Dashboard-JSON-Lint.
- **Security-Auswirkung:** Collector-Endpoint geschützt.
- **HA-Auswirkung:** Collector kein SPOF für Fachbetrieb.
- **Permissions:** — · **Audit Events:** —

---

# EPIC 23 · Security Hardening

**Milestone:** `23 Security Hardening` · **Phase:** fortlaufend · **Ziel des Epics:**
Die Sicherheits-Baseline aus MASTER_PROMPT §22 / `.ai/SECURITY.md` durchgängig
umsetzen und die weichen CI-Gates scharf schalten. Quellen: MASTER_PROMPT §22,
`.ai/SECURITY.md`, ADR-0014, ADR-0015.

### E23-01 · Secret-Store-Anbindung (aus ADR-0019) produktiv verdrahten
**Epic:** 23 · **Phase:** fortlaufend · **Area:** infra, security · **Branch:** feature/<nr>-secret-store-integration
- **Ziel:** Runtime-Secrets kommen aus dem in ADR-0019 gewählten Store; `.env`/Compose-Secrets nur noch für Dev.
- **Fachlicher Hintergrund:** ADR-0015; E01-03 (ADR-0019).
- **Scope:** Provider-Abstraktion für Secret-Zugriff, Anbindung des gewählten Stores, Rotation-Hooks, Fallback-Verhalten, Doku.
- **Nicht im Scope:** Store-Betrieb/HA (Deploy).
- **Abhängigkeiten:** E01-03.
- **Acceptance Criteria:** kein produktives Secret im Klartext nötig; Rotation ohne Deploy; Startup schlägt fehl, wenn Pflicht-Secret fehlt.
- **Tests:** Integration gegen Test-Instanz; Rotation.
- **Security-Auswirkung:** zentrale, rotierbare Secret-Verwaltung.
- **HA-Auswirkung:** Store auf beiden Knoten erreichbar (ADR adressiert). · **Permissions:** — · **Audit Events:** `SECRET_ROTATED` (ohne Wert).

### E23-02 · TLS überall + interne mTLS zwischen Diensten
**Epic:** 23 · **Phase:** fortlaufend · **Area:** infra, security · **Branch:** feature/<nr>-tls-mtls
- **Ziel:** Alle Verbindungen sind TLS; dienstintern mTLS wo sinnvoll.
- **Fachlicher Hintergrund:** MASTER_PROMPT §22; `.ai/SECURITY.md`; ADR-0018.
- **Scope:** interne PKI/Zertifikatsausgabe, mTLS API↔`cucm-cti-gateway`, Agent-mTLS (E09-08 vervollständigen), Rotation.
- **Nicht im Scope:** externe CA-Beschaffung.
- **Abhängigkeiten:** E06-12, E09-08, E12-16.
- **Acceptance Criteria:** kein Klartext-Dienst-zu-Dienst-Pfad in Prod; ungültiges Zert → Verbindung verweigert; Rotation ohne Downtime.
- **Tests:** Integration: mTLS erzwungen; ungültiges Zert abgelehnt.
- **Security-Auswirkung:** kein internes MITM/Sniffing.
- **HA-Auswirkung:** Rotation rolling. · **Permissions:** — · **Audit Events:** —

### E23-03 · Security-Header + CSP (Web + Electron, strikt)
**Epic:** 23 · **Phase:** fortlaufend · **Area:** frontend, infra, security · **Branch:** feature/<nr>-csp-headers
- **Ziel:** Strikte CSP und Security-Header für Web-UI und Electron-Renderer.
- **Fachlicher Hintergrund:** MASTER_PROMPT §22: „Security Headers, CSP".
- **Scope:** CSP (default-src 'self', kein inline-script, nonce/hashes), HSTS, X-Content-Type-Options, Referrer-Policy, Permissions-Policy; Electron-CSP + `webSecurity` an; Report-Endpoint.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E06-12, E08-01.
- **Acceptance Criteria:** CSP ohne `unsafe-inline`/`unsafe-eval`; automatischer Header-Test; keine CSP-Violations im Normalbetrieb.
- **Tests:** Playwright: Header-Assertions; Violation-Report leer.
- **Security-Auswirkung:** XSS-/Injection-Härtung.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E23-04 · Rate-Limiting (Login, API, Integrations-Webhooks) + Lockout
**Epic:** 23 · **Phase:** fortlaufend · **Area:** backend, security · **Branch:** feature/<nr>-rate-limiting
- **Ziel:** Missbrauchsschutz durch Rate-Limits an sensiblen Endpunkten.
- **Fachlicher Hintergrund:** MASTER_PROMPT §22.
- **Scope:** Limiter (Login, TOTP-Verify, Passwort-Reset, API-Buckets, eingehende Integrations-Webhooks), konfigurierbare Schwellen, `429` + `Retry-After`, verteilter Zähler (Redis/DB/etcd).
- **Nicht im Scope:** WAF/DDoS (Netzwerk).
- **Abhängigkeiten:** E02-05.
- **Acceptance Criteria:** Login-Brute-Force gedrosselt; Limits knotenübergreifend; legitime Nutzung nicht behindert.
- **Tests:** Integration: Schwellen; verteilter Zähler über zwei Knoten.
- **Security-Auswirkung:** Brute-Force-/Missbrauchsschutz.
- **HA-Auswirkung:** verteilter Zählerspeicher. · **Permissions:** — · **Audit Events:** `RATE_LIMIT_TRIGGERED` (Auth-Pfade).

### E23-05 · CSRF-Review + SameSite + Token-Bindung
**Epic:** 23 · **Phase:** fortlaufend · **Area:** backend, security · **Branch:** feature/<nr>-csrf-review
- **Ziel:** Durchgängiger CSRF-Schutz für Cookie-Flows; Prüfbericht.
- **Fachlicher Hintergrund:** MASTER_PROMPT §22.
- **Scope:** Review aller state-changing Endpoints, SameSite-Politik dokumentiert, Double-Submit-Token wo nötig, Origin/Referer-Prüfung, Bearer-Pfad (Agents) dokumentiert ausgenommen.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E02-05.
- **Acceptance Criteria:** kein Cookie-basierter Write ohne CSRF-Schutz (Contract-Test); Bericht in `docs/`.
- **Tests:** API: CSRF-Negativfälle je Write-Kategorie.
- **Security-Auswirkung:** CSRF-Härtung.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E23-06 · Input-Validation-Audit + Payload-Größenlimits
**Epic:** 23 · **Phase:** fortlaufend · **Area:** backend, security · **Branch:** feature/<nr>-input-validation-audit
- **Ziel:** Alle Write-Endpoints haben strikte Schemas und Größenlimits; Audit belegt Abdeckung.
- **Fachlicher Hintergrund:** MASTER_PROMPT §22.
- **Scope:** Pydantic-Modelle je Write-Body (`extra=forbid`), Max-Body-Size global + je Endpoint, Reject unbekannter Felder, Upload-Limits.
- **Nicht im Scope:** fachliche Validierung.
- **Abhängigkeiten:** E03-*, E02-*.
- **Acceptance Criteria:** Contract-Test: jeder `/api/v1`-Write hat `extra=forbid`-Modell; übergroßer Body → `413`; Bericht in `docs/`.
- **Tests:** API: Overlarge/Unknown-Field-Fälle.
- **Security-Auswirkung:** reduziert Injection-/Overpost-Fläche.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E23-07 · Dependency-/Container-Scanning-Gates scharf schalten
**Epic:** 23 · **Phase:** fortlaufend · **Area:** infra, security · **Branch:** feature/<nr>-scanning-gates-enforce
- **Ziel:** CRITICAL/HIGH-Findings aus `pip-audit` und Trivy blockieren PRs.
- **Fachlicher Hintergrund:** MASTER_PROMPT §22; ADR-0014.
- **Scope:** `security.yml` fail on CRITICAL/HIGH; kuratiertes Ausnahmeverfahren mit Ablaufdatum; npm-audit für `apps/web` scharf (nach #14).
- **Nicht im Scope:** CVE-Behebung (laufend via Dependabot).
- **Abhängigkeiten:** E01-06.
- **Acceptance Criteria:** neuer CRITICAL/HIGH-Fund bricht CI; Ausnahmen nur mit Begründung + Ablauf; wöchentlicher Scan aktiv.
- **Tests:** CI: eingeführte verwundbare Dependency bricht den Build.
- **Security-Auswirkung:** kontinuierliche Schwachstellenkontrolle.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E23-08 · Non-Root-Container-Audit (alle Images)
**Epic:** 23 · **Phase:** fortlaufend · **Area:** infra, security · **Branch:** feature/<nr>-nonroot-audit
- **Ziel:** Jedes selbstgebaute Image läuft als Nicht-Root; CI erzwingt es.
- **Fachlicher Hintergrund:** MASTER_PROMPT §22; `.ai/SECURITY.md`.
- **Scope:** `bbz-api` (non-root), `bbz-web`, `cucm-cti-gateway`, Worker; Dockerfile-Härtung (USER, `--read-only`, dropped caps), CI-Assertion (Trivy/Dockle/eigener Check).
- **Nicht im Scope:** Fremd-Images — nur konfigurieren.
- **Abhängigkeiten:** E12-01.
- **Acceptance Criteria:** CI schlägt fehl, wenn ein selbstgebautes Image als root läuft; Härtungsoptionen dokumentiert.
- **Tests:** CI-Image-Check.
- **Security-Auswirkung:** geringere Container-Ausbruchsfläche.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E23-09 · Audit-Log-Integrität: Hash-Chain / WORM-Option umsetzen
**Epic:** 23 · **Phase:** fortlaufend · **Area:** db, security · **Branch:** feature/<nr>-audit-hash-chain
- **Ziel:** Optionale kryptografische Verkettung der Audit-/Domain-Event-Zeilen + Verifikationsjob; WORM-Ablage dokumentiert.
- **Fachlicher Hintergrund:** `.ai/CURRENT_STATE.md` offener Punkt; MASTER_PROMPT §17; erweitert E04-10.
- **Scope:** `prev_hash`/`row_hash`-Spalten, in-TX-Berechnung, periodischer Verifikationsjob, Chain-Export für externe Archivierung.
- **Nicht im Scope:** WORM-Hardware.
- **Abhängigkeiten:** E04-10.
- **Acceptance Criteria:** manipulierte/entfernte Zeile wird erkannt und alarmiert; Overhead gemessen + akzeptabel.
- **Tests:** Integration: Chain-Bruch erkannt; Performance-Benchmark.
- **Security-Auswirkung:** revisionssichere, manipulationserkennende Audit-Kette.
- **HA-Auswirkung:** Chain folgt der Replikation. · **Permissions:** `system.audit.view` · **Audit Events:** `AUDIT_INTEGRITY_ALERT`.

### E23-10 · Threat-Model + Pentest-Checkliste + DPIA-Input (BKU-Session-Monitoring)
**Epic:** 23 · **Phase:** fortlaufend · **Area:** documentation, security · **Branch:** docs/<nr>-threat-model-dpia
- **Ziel:** Gepflegtes Bedrohungsmodell, Pentest-Checkliste, datenschutzrechtliche Zuarbeit für BKU-Session-Monitoring + Remote-Logout/Restart.
- **Fachlicher Hintergrund:** `.ai/CURRENT_STATE.md` offener Punkt „DPIA for BKU session monitoring"; MASTER_PROMPT §28.3.
- **Scope:** STRIDE je Vertrauensgrenze (Client/Agent/Server/Integrationen), Pentest-Checkliste, DPIA-Zuarbeit (Daten, Zweck, Aufbewahrung, Betroffenenrechte).
- **Nicht im Scope:** rechtliche Bewertung (Kunde/DSB).
- **Abhängigkeiten:** Epics 09, 10.
- **Acceptance Criteria:** Threat-Model deckt alle Vertrauensgrenzen ab; DPIA-Input listet alle personenbeziehbaren Datenflüsse (Login, Präsenz, Calls, BKU-Session).
- **Tests:** Doc-Review.
- **Security-Auswirkung:** strukturierte Risikoübersicht.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —
- **Status (2026-09-02):** *partial.* `docs/security/{threat-model,pentest-checklist,dpia-input}.md`
  cover every trust boundary + data flow that exists today. The BKU-agent
  boundary (#5) and the BKU-session data flows are stubbed pending Epic 09/10;
  the model is completed there. Retention values in the DPIA input must be set
  before go-live.

### E23-11 · Security-Review Agent-Kommandofläche + Tür-/DTMF-Secret-Handling
**Epic:** 23 · **Phase:** fortlaufend · **Area:** security, test · **Branch:** feature/<nr>-security-review-agents-door
- **Ziel:** Gezielter Sicherheits-Review + Härtungstests der Agent-Kommandos und des Tür-/DTMF-Pfads.
- **Fachlicher Hintergrund:** `.ai/SECURITY.md` „Agent / remote control security", „Door control security".
- **Scope:** Review + Fuzzing der Agent-Kommando-Deserialisierung, Replay-/Expiry-/Generation-Bypass-Versuche, Prüfung dass DTMF-Klartext in keiner Senke landet (erweitert E17-06), „kein Browser→Agent-Direktvertrauen".
- **Nicht im Scope:** externer Pentest.
- **Abhängigkeiten:** E10-12, E10-13, E17-06.
- **Acceptance Criteria:** kein gefundener Bypass; Fuzzing ohne Crash/Umgehung; Secret-Nichtprotokollierung erneut bestätigt.
- **Tests:** Fuzz-/Negativ-Suite als CI-Job.
- **Security-Auswirkung:** Härtung der höchstprivilegierten Pfade.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E23-12 · SBOM- + cosign-Verifikation beim Deploy erzwingen
**Epic:** 23 · **Phase:** fortlaufend · **Area:** infra, security · **Branch:** feature/<nr>-deploy-signature-enforce
- **Ziel:** Deployments akzeptieren nur signierte Images mit gültiger SBOM und immutable Digest.
- **Fachlicher Hintergrund:** MASTER_PROMPT §19; ADR-0014.
- **Scope:** Deploy-Skripte verifizieren `cosign verify` (OIDC-Identität + Policy) vor Start; nur Digest-Referenzen; SBOM-Vorhandensein geprüft.
- **Nicht im Scope:** Admission-Controller.
- **Abhängigkeiten:** E01-04, E24-01.
- **Acceptance Criteria:** Deploy eines unsignierten/`latest`-Images → abgebrochen; nur Digest-Pins erlaubt.
- **Tests:** Deploy-Dry-Run: signiert ok, unsigniert abgelehnt.
- **Security-Auswirkung:** Supply-Chain-Durchsetzung am Deploy.
- **HA-Auswirkung:** — · **Permissions:** `system.cluster.manage` · **Audit Events:** `DEPLOY_IMAGE_VERIFIED`.

---

# EPIC 24 · Production Deployment

**Milestone:** `24 Production Deployment` · **Phase:** fortlaufend/Abschluss ·
**Ziel des Epics:** Reproduzierbares, sicheres Produktiv-Deployment der 2+1-
Topologie mit Release-Pipeline, Rolling Updates, Backup/DR, Staging und Go-Live-
Checkliste. Quellen: MASTER_PROMPT §19/§20/§21, ADR-0014, `docs/runbooks/*`.

### E24-01 · release.yml vervollständigen (SemVer+SHA, SBOM, cosign, GHCR, Digests)
**Epic:** 24 · **Phase:** fortlaufend · **Area:** infra · **Branch:** feature/<nr>-release-pipeline-complete
- **Ziel:** Die in E01-04 begonnene Release-Pipeline ist vollständig und deckt alle prod-Images ab (inkl. `cucm-cti-gateway`).
- **Fachlicher Hintergrund:** MASTER_PROMPT §19; ADR-0014.
- **Scope:** alle prod-Images bauen/taggen/signieren/pushen, SBOM je Image, Release-Notes, Digest-Manifest als Artefakt, Contract-Test der Images (starten + `/health/ready`).
- **Nicht im Scope:** Deployment (E24-04).
- **Abhängigkeiten:** E01-04, E12-01.
- **Acceptance Criteria:** ein Tag erzeugt je Image SemVer+SHA-Tag, SBOM, Signatur; Digest-Manifest referenzierbar; kein `latest`.
- **Tests:** Release-Dry-Run auf Pre-Release-Tag; Image-Start-Contract.
- **Security-Auswirkung:** vollständige Provenienz.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E24-02 · Produktions-Deployment-Manifeste (2× BBZ-Server + Quorum)
**Epic:** 24 · **Phase:** fortlaufend · **Area:** infra · **Branch:** feature/<nr>-prod-deploy-manifests
- **Ziel:** Vollständige, dokumentierte Deployment-Definitionen der Produktivtopologie.
- **Fachlicher Hintergrund:** MASTER_PROMPT §20; ADR-0001/0018.
- **Scope:** `deploy/prod/` je Rolle (srv01/srv02/quorum), Ressourcenlimits, Restart-Policies, Volume-/Backup-Pfade, Netzwerk-/Firewall-Hinweise, Digest-Pins.
- **Nicht im Scope:** IaC für die VMs (Kunde/Betrieb).
- **Abhängigkeiten:** E06-01, E06-08, E24-01.
- **Acceptance Criteria:** Manifeste starten die 2+1-Topologie in einer Testumgebung; nur Digest-Referenzen; Quorum ohne Fachdienste.
- **Tests:** Integrationsumgebung: Stack hoch, `/cluster/status` gesund.
- **Security-Auswirkung:** definierte Netz-/Rechte-Grenzen.
- **HA-Auswirkung:** produktive HA-Topologie. · **Permissions:** — · **Audit Events:** —

### E24-03 · Umgebungs-/Secret-Provisionierung (staging/prod)
**Epic:** 24 · **Phase:** fortlaufend · **Area:** infra, security · **Branch:** feature/<nr>-env-secret-provisioning
- **Ziel:** Klar getrennte Konfig-/Secret-Sätze je Umgebung, aus dem Secret-Store (E23-01).
- **Fachlicher Hintergrund:** ADR-0015; MASTER_PROMPT §22.
- **Scope:** Umgebungs-Matrix, Provisionierungs-Runbook, Validierung „alle Pflicht-Secrets vorhanden" beim Deploy.
- **Nicht im Scope:** Store-Betrieb.
- **Abhängigkeiten:** E23-01.
- **Acceptance Criteria:** fehlendes Pflicht-Secret → Deploy bricht mit klarer Meldung ab; keine Umgebung teilt Secrets.
- **Tests:** Deploy-Dry-Run mit fehlendem Secret → Abbruch.
- **Security-Auswirkung:** Umgebungs-Isolation.
- **HA-Auswirkung:** — · **Permissions:** — · **Audit Events:** —

### E24-04 · Rolling-Update-Automation + Pre-Flight-Checks
**Epic:** 24 · **Phase:** fortlaufend · **Area:** infra · **Branch:** feature/<nr>-rolling-update-automation
- **Ziel:** Ein Kommando/Pipeline führt das Rolling Update produktiv durch — mit Vorprüfungen.
- **Fachlicher Hintergrund:** MASTER_PROMPT §21; erweitert E06-09.
- **Scope:** Automation um E06-09 (Pre-Flight: Cluster grün, Migration N-1-kompatibel, freier Speicher, Backup frisch), Health-Gates, automatischer Abbruch + Rollback-Hinweis.
- **Nicht im Scope:** — .
- **Abhängigkeiten:** E06-09, E06-10, E24-01.
- **Acceptance Criteria:** Update in Staging ohne Clientausfall; Abbruch bei rotem Pre-Flight; jeder Lauf auditiert.
- **Tests:** Staging: Update mit laufenden Stream-Clients; erzwungener Pre-Flight-Fehler.
- **Security-Auswirkung:** nur verifizierte Images (E23-12).
- **HA-Auswirkung:** Wartung ohne Downtime. · **Permissions:** `system.cluster.manage` · **Audit Events:** `ROLLING_UPDATE_STARTED/COMPLETED/ABORTED`.

### E24-05 · Backup-/Restore-Automation + getesteter Restore
**Epic:** 24 · **Phase:** fortlaufend · **Area:** infra · **Branch:** feature/<nr>-backup-restore-automation
- **Ziel:** Produktive, überwachte Backups (PostgreSQL + etcd) mit regelmäßig automatisiert getestetem Restore.
- **Fachlicher Hintergrund:** MASTER_PROMPT §20/§24; erweitert E06-14.
- **Scope:** Zeitpläne, verschlüsselte Offsite-Kopie (Ziel), Restore-Automation, wöchentlicher automatischer Restore-Test mit Integritätsprüfung, Alert bei Backup-Fehler.
- **Nicht im Scope:** DR-Standort-Aufbau (E24-06).
- **Abhängigkeiten:** E06-14, E22-06.
- **Acceptance Criteria:** Backup-Fehler alarmiert; automatischer Restore-Test grün; RPO/RTO dokumentiert und eingehalten.
- **Tests:** wöchentlicher Restore-Test-Job.
- **Security-Auswirkung:** Backups verschlüsselt, Zugriff beschränkt.
- **HA-Auswirkung:** Wiederherstellbarkeit. · **Permissions:** `system.cluster.manage` · **Audit Events:** `BACKUP_COMPLETED` `RESTORE_TEST_COMPLETED`.

### E24-06 · Disaster-Recovery-Runbook (beide Server / Witness verloren)
**Epic:** 24 · **Phase:** fortlaufend · **Area:** documentation, infra · **Branch:** docs/<nr>-dr-runbook
- **Ziel:** Getestete Wiederanlaufprozeduren für Totalverlust-Szenarien.
- **Fachlicher Hintergrund:** MASTER_PROMPT §5/§24; `docs/runbooks/`.
- **Scope:** Runbooks: beide App-Server verloren (Restore, etcd-Neuaufbau, Patroni-Reinit), Witness verloren, Split-Brain-Auflösung; jede Prozedur mindestens einmal in Staging durchgespielt.
- **Nicht im Scope:** Georedundanz-Architektur.
- **Abhängigkeiten:** E24-05, E06-11.
- **Acceptance Criteria:** jede DR-Prozedur Schritt-für-Schritt dokumentiert und in Staging verifiziert; RTO dokumentiert.
- **Tests:** Staging-Durchlauf je Szenario (protokolliert).
- **Security-Auswirkung:** — · **HA-Auswirkung:** definierte Wiederanlauffähigkeit. · **Permissions:** — · **Audit Events:** —
- **Status (2026-09-02):** `docs/runbooks/disaster-recovery.md` — die Szenario-Leiter
  (§ A–E) mit Schritt-für-Schritt-Prozeduren, Post-Recovery-Verifikation (inkl.
  `single_primary`, `event_seq`-Nichtregression, Hash-Chain `verified:true`) und
  RTO-Zieltabelle. **Der Staging-Durchlauf je Szenario steht noch aus** — beim
  ersten DR-Drill die gemessenen RTOs in die Tabelle eintragen.

### E24-07 · Staging-Umgebung + Smoke-Suite
**Epic:** 24 · **Phase:** fortlaufend · **Area:** infra, test · **Branch:** feature/<nr>-staging-env
- **Ziel:** Dauerhafte Staging-Umgebung entsprechend der Produktivtopologie, mit automatisierter Smoke-Suite nach jedem Deploy.
- **Fachlicher Hintergrund:** MASTER_PROMPT §19 (e2e smoke tests).
- **Scope:** Staging-Deploy (2+1), Seed-Daten, Post-Deploy-Smoke (Health, Login, Ereignis-Lebenszyklus, Telefonie-Mock, Trigger, Failover-Kurztest).
- **Nicht im Scope:** Lasttest.
- **Abhängigkeiten:** E24-02, E07-16, E11-16, E15-15.
- **Acceptance Criteria:** jeder Staging-Deploy löst die Smoke-Suite aus; roter Smoke blockiert die Prod-Freigabe.
- **Tests:** Smoke-Suite selbst.
- **Security-Auswirkung:** Staging mit eigenen Secrets/Daten (keine Prod-Daten).
- **HA-Auswirkung:** Staging spiegelt HA. · **Permissions:** — · **Audit Events:** —

### E24-08 · Go-Live-Checkliste + Akzeptanztestplan + Betriebshandbuch
**Epic:** 24 · **Phase:** Abschluss · **Area:** documentation · **Branch:** docs/<nr>-golive-checklist
- **Ziel:** Vollständige Go-Live-Checkliste, Akzeptanztestplan (Mockup-Parity + Pflicht-E2E + HA) und konsolidiertes Betriebshandbuch.
- **Fachlicher Hintergrund:** MASTER_PROMPT §24/§27; `.ai/DEFINITION_OF_DONE.md`.
- **Scope:** Checkliste (Sicherheit, Backup, Monitoring, Runbooks, Schulung, §8.18/Coda/Weytec-Blocker-Status), Akzeptanztestplan (alle E2E-Suiten + Parity-Checkliste + HA-Szenarien), Betriebshandbuch (Runbooks konsolidiert).
- **Nicht im Scope:** die eigentliche Abnahme (Kunde).
- **Abhängigkeiten:** praktisch alle Epics.
- **Acceptance Criteria:** Checkliste referenziert je Punkt ein Artefakt/Test; kein offener Blocker ohne dokumentierten Status; Betriebshandbuch vollständig.
- **Tests:** Doc-Review; Cross-Check gegen `.ai/DEFINITION_OF_DONE.md`.
- **Security-Auswirkung:** stellt sicher, dass Sicherheits-/Datenschutzpunkte vor Go-Live erledigt sind.
- **HA-Auswirkung:** HA-Abnahme Teil des Plans. · **Permissions:** — · **Audit Events:** —

---

## 4. Zusammenfassung / Zählung

| Epic | Issues | Phase |
|---|---|---|
| 01 Repository Foundation | 7 | 0 |
| 02 Identity / RBAC | 14 | 1 |
| 03 Event Core | 16 | 1 |
| 04 Audit / Domain Events | 11 | 1 |
| 05 EPK Workflow Engine | 13 | 1 |
| 06 HA Cluster | 14 | 2 |
| 07 Web UI / PrimeVue | 19 | 3 |
| 08 BBZ Desktop Client | 7 | 4 |
| 09 BBZ Client Agent | 10 | 4 |
| 10 BKU Agent | 16 | 4 |
| 11 Telephony Core | 16 | 5 |
| 12 Cisco CUCM | 20 | 5 |
| 13 SIP Provider | 8 | 5 |
| 14 Contacts / Call Priorities | 10 | 6 |
| 15 Technical Trigger Engine | 15 | 5–6 |
| 16 Coda Video / HxGN dC3 Video | 13 | 5+ |
| 17 Siedle | 7 | 5+ |
| 18 DWD Weather | 10 | 7 |
| 19 Weytec Monitor Routing | 10 | 8 |
| 20 Archive / Postprocessing | 8 | 1+ |
| 21 Enterprise Authentication | 8 | 9 |
| 22 Monitoring / Observability | 7 | fortlaufend |
| 23 Security Hardening | 12 | fortlaufend |
| 24 Production Deployment | 8 | fortlaufend |
| **Summe** | **279** | |

## 5. Neue ADRs, die diese Roadmap erzeugt

| ADR | Titel | ausgelöst in |
|---|---|---|
| ADR-0009 | Agent-Sprache (Go) — Proposed → Accepted | E09-01 |
| ADR-0019 | Runtime-Secret-Store (Vault vs. SOPS-age) | E01-03 |
| ADR-0020 | Audit-Unveränderlichkeitsmechanismus | E04-10 |
| ADR-0021 | PostgreSQL-Replikationsmodus (sync/async) | E06-02 |
| ADR-0022 | Electron: Web-Build laden vs. bündeln | E08-07 |
| ADR-0023 | SIP/CTI-Gateway (Asterisk vs. FreeSWITCH) | E13-02 |

## 6. Katalog-Ergänzung (Permissions)

- `agents.manage` — Verwaltung der BBZ-Client-Agents (analog `bku.agent.manage`), E09-08.
- Alle übrigen Permission-Keys stammen aus `docs/domain/permission-catalog.md`.

## 7. Nach Freigabe — Umsetzungsschritte (kein Feature-Code)

1. `.ai/ROADMAP.md` per PR nach `main` mergen (dieses Dokument).
2. 24 GitHub-Milestones anlegen (`01 …` – `24 …`).
3. Labels anlegen (`epic:*`, `phase:*`, `area:*`).
4. Issues aus diesem Dokument erzeugen (Titel `<Epic-Kurz> · <Issue-Titel>`,
   Body = Template, Milestone + Labels gesetzt), Roadmap-IDs durch echte
   `#`-Nummern ersetzen, `Depends on #…` eintragen.
5. Optional je Epic ein Tracking-Issue mit Task-Liste.
6. `.ai/CURRENT_STATE.md` „Next target" auf „Epic 02 nach ADR-Akzeptanz (E01-01)"
   aktualisieren.
