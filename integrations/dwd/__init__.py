"""DWD Weather integration (roadmap Epic 18).

Scaffold (E18-01): manifest + config schema + a protocol-conformant
:class:`~bbz_integration_sdk.providers.WeatherProvider` stub for Mittelfranken.
The concrete DWD open-data clients are chosen by **ADR-0026** and wired per
capability: warnings E18-02, radar E18-03, observations E18-04. Until then the
``get_*`` methods raise ``DwdNotImplementedError``.

Only outbound HTTPS to DWD's public services; no credentials, no PII.
"""
