# AGENTS.md

Dieses Repository ist Multi-AI-fähig.

Jeder Coding-Agent MUSS vor Änderungen folgende Dateien lesen:

1. `.ai/WORKSPACE.md`
2. `.ai/ARCHITECTURE.md`
3. `.ai/RULES.md`
4. `.ai/CURRENT_STATE.md`
5. `.ai/TASK_PROTOCOL.md`
6. `.ai/FEATURES.md`
7. `.ai/SECURITY.md`
8. `.ai/TESTING.md`
9. `.ai/DEFINITION_OF_DONE.md`
10. `.ai/INTEGRATIONS_CUCM.md` bei Telefonie-/Cisco-Tasks
11. relevante ADRs unter `.ai/DECISIONS/`

Regeln:
- Keine direkten Commits auf main.
- Jeder Task braucht Issue/Branch/PR.
- Architekturänderungen nur per ADR.
- Keine erfundenen externen APIs.
- Bestehende Features nicht still entfernen.
- Nach jedem Task `.ai/CURRENT_STATE.md` aktualisieren.
- Business Rules gehören in Backend/Core, nicht nur ins Frontend.
