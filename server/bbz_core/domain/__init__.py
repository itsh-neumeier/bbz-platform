"""Core domain.

**Boundary rule (enforced by import-linter, see root pyproject.toml):**
``bbz_core.domain`` must not import ``bbz_core.api``, ``bbz_core.infra``,
``bbz_core.integrations_host`` or ``bbz_integration_sdk``. The domain is pure:
entities, value objects, domain services, domain events, and policy. It talks to
infrastructure only through interfaces it defines itself (dependency inversion).

No domain code exists yet — Phase 1 introduces identity, authorization, events,
event ownership, workflows and audit here.
"""
