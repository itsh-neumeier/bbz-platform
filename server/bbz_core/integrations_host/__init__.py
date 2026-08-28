"""Integration host (Home-Assistant-style plugin model, MASTER_PROMPT §7).

This is the ONLY part of the core allowed to import ``bbz_integration_sdk``. It
discovers integration manifests, validates them against the SDK schema, and will
(Phase 1+) load adapters and route normalized events between integrations and the
domain. Concrete integrations live under the top-level ``integrations/`` tree and
are never imported by the core (import-linter enforces this).
"""
