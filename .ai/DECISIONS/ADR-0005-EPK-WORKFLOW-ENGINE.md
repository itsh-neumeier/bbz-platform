# ADR-0005: Versioned EPK-Style Workflow Engine

## Status
Accepted

## Context
BBZ handlungsanweisungen need configurable step-by-step processes including conditional and parallel paths. Administrators must be able to define these without changing application code.

## Decision
Implement a server-side versioned graph workflow engine with EPK-style Event and Function nodes and AND/OR/XOR connectors. Published versions are immutable; each running instance is pinned to its template version.

Conditions use a safe restricted rule model, never arbitrary code evaluation.

## Consequences
- complex operational procedures are configurable
- process changes are version/audit safe
- workflows require graph validation and concurrency/token semantics
