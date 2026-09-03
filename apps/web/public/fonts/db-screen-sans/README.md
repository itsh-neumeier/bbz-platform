# DB Screen Sans

The Deutsche Bahn corporate screen typeface (DB Type 2.5 · "DB Screen Sans" /
"DB Screen Head", WEB `.woff2`). Used as the primary UI font (ADR-0029).

**Licensing.** DB Type is licensed to Deutsche Bahn / DB InfraGO per the *DB Type
Lizenzvereinbarung* and **must not be committed to this public repository or
redistributed.** The `*.woff2` files are `.gitignore`d.

**Setup on a build/deploy host.** Place these files here:

```
DBScreenSans-Regular.woff2      (400)
DBScreenSans-Medium.woff2       (500)
DBScreenSans-SemiBold.woff2     (600)
DBScreenSans-Bold.woff2         (700)
DBScreenSans-DigitalRegular.woff2   (tabular figures — clocks, IDs)
DBScreenHead-Regular.woff2      (headings)
DBScreenHead-Black.woff2        (headings, emphasis)
```

`src/theme/fonts.css` declares the `@font-face` rules against `/fonts/db-screen-sans/…`.
If the files are absent the `@font-face` simply fails to load and the app falls
back through `--bbz-font-sans` → `--db-font-family-sans` (helvetica / arial /
sans-serif) — the layout is unaffected.
