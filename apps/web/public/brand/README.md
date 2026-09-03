# DB brand assets

The **official Deutsche Bahn logo** (ADR-0029, issue #713 — *"Keine selbst
nachgebauten oder verfremdeten DB Logos … Nur vorhandene bzw. offiziell
freigegebene Assets"*).

**Licensing.** The DB logo is a registered trademark; the SVG is a licensed
asset and **must not be committed to this public repository.** It is
`.gitignore`d.

**Setup on a build/deploy host.** Place the official DB logo here:

```
apps/web/public/brand/db-logo.svg
```

Sources for the licensed file:

- `@db-ux/db-theme` — run the package's `postinstall` with the
  `ASSET_PASSWORD` / `ASSET_INIT_VECTOR` from the DB Marketingportal, then copy
  `node_modules/@db-ux/db-theme/build/images/light/db_logo.svg`.
- or the DB Marketingportal logo download.

If the file is absent, `SidebarLeft.vue` falls back to the "DB" wordmark on DB
red — never a reconstructed logo.
