# EPK-Style Workflow / Handlungsanweisungs-Engine

## Goal

Handlungsanweisungen are not hardcoded checklists. Administrators can create and version graphical process templates using EPK-style events/functions and logical connectors.

The operator receives a clear step-by-step execution view derived from the graph.

## Node Types

### Event
Represents a state/condition. Examples:
- BMA-Anruf eingegangen
- Lage bestätigt
- Feuerwehr eingetroffen

### Function / Task
Typed task kinds:
- manual user task
- confirmation task
- documentation task
- integration action
- notification action
- timer/wait
- event creation/update

### Logical Connectors
- AND split / AND join
- XOR split / XOR join
- OR split / OR join

## Connector semantics

AND: all branches activate / all required branches must complete before join.

XOR: exactly one valid branch is selected. Selection may be automatic from safe rules or explicit operator decision.

OR: one or more valid branches can activate; join waits for the set of branches activated for this execution instance.

## Safe Conditions

Never use arbitrary Python/JavaScript `eval`.

Use a restricted expression model/DSL over whitelisted context fields.

Examples conceptually:
- severity equals critical
- station belongs to configured group
- answer `smoke_visible` equals true

## Versioning

Template lifecycle:
- DRAFT
- VALIDATED
- PUBLISHED
- DEPRECATED

A running event/workflow instance is pinned to an immutable published template version. Publishing v4 must not silently change instances running on v3. Explicit migration, if added later, must be a separate audited operation.

## Publish validation

At minimum validate:
- exactly defined start behavior
- reachable end path(s)
- no orphan nodes
- valid event/function/connectors
- correct split/join cardinality
- XOR branch selection can be resolved
- OR branch activation is trackable
- required properties present
- integration actions reference existing capabilities/config
- no unsafe recursive loop without a bounded/explicit re-entry rule

## Operator behavior

The operator sees:
- current active step(s)
- completed steps
- waiting branches
- required decisions
- progress/status
- timestamps
- audit entries

Event responsibility remains on the WHOLE event, not per workflow task.

## Suggested persistence

- workflow_templates
- workflow_template_versions
- workflow_nodes
- workflow_edges
- workflow_instances
- workflow_tokens
- workflow_task_results
- workflow_decisions

Store graph definition as versioned structured JSON plus normalized indexes where useful.
