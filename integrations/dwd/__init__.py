"""DWD Weather integration (roadmap Epic 18).

A protocol-conformant :class:`~bbz_integration_sdk.providers.WeatherProvider` for
Mittelfranken over DWD's public open-data services (**ADR-0026**):

* ``weather.warnings``     — CAP 1.2 DISTRICT feed (E18-02)
* ``weather.radar``        — GeoServer WMS RV product frame series (E18-03)
* ``weather.observations`` — POI current-weather CSV (E18-04)

Only outbound HTTPS to ``opendata.dwd.de`` / ``maps.dwd.de``; no credentials, no
PII; no new runtime dependency (stdlib ``urllib`` / ``zipfile`` / ``csv`` /
``ElementTree``). Every DWD-derived value carries the "Deutscher Wetterdienst"
attribution.
"""
