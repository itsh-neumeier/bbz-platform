"""Vendored DWD reference data (region → warncell / POI-station mapping).

Not fetched at runtime — a DWD directory reshuffle can't silently break
resolution (ADR-0026). Refresh by a deliberate PR from
``cap_warncellids.csv`` / the DWD POI station list.
"""
