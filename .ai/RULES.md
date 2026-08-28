# .ai/RULES.md

- Never commit directly to main.
- Never invent external API contracts.
- Never remove functional behavior without explicit requirement.
- Every state-changing API must be idempotent.
- Every critical state change must create audit data.
- Permissions are enforced server-side.
- Archived events are never hard-deleted.
- Reactivation requires explicit confirmation.
- Calls require documentation category.
- Integration code must stay outside core domain.
- Accessibility is a functional requirement.
