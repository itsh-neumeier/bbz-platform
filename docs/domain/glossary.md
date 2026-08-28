# Glossary

| Term | Meaning |
|------|---------|
| BBZ | Bahnhofsbetriebszentrale — station operations control centre |
| 3-S-Zentrale | Service, Sicherheit, Sauberkeit centre (DB InfraGO Personenbahnhöfe) |
| BBZ-SRV01 / SRV02 | The two active application servers |
| BBZ-QUORUM01 | Witness / third voting member; no BBZ domain data |
| BKU | Corporate workstation paired 1:1 with a BBZ workplace |
| BKU Agent | Local service on the BKU workstation; typed allowlist only (ADR-0003) |
| BBZ Client Agent | Local service on the BBZ workplace PC; discovery/failover/cache |
| Ereignis | Event — the central operational work item; ownership is on the whole event |
| Ereignisspeicher | Shared event work queue on the workplace page |
| Ereignisverantwortung | Event ownership; transfer/takeover is audited |
| EPK | Ereignisgesteuerte Prozesskette — graph model for Handlungsanweisungen (ADR-0005) |
| Handlungsanweisung | Guided operating procedure, executed step-by-step from an EPK graph |
| BMA | Brandmeldeanlage — fire alarm system; can dial a technical number (§32) |
| Überfallmeldeknopf | Panic/duress button; a first-class alarm trigger via Coda (ADR-0006) |
| Siedle | Door-station system; door open via telephony + DTMF profile (ADR-0004) |
| Coda Video | HxGN dC3 Video; canonical `coda_video`; video + alarm source (ex "Cayuga") |
| Weytec | Monitor / KVM routing vendor (§9); API not yet documented |
| CUCM | Cisco Unified Communications Manager |
| JTAPI / CTI Manager | Cisco real-time call-control interface (ADR-0002) |
| AXL / RisPort70 / UDS / CDR | CUCM SOAP/REST interfaces for config / health / directory / call records |
| CONTROL_LEADER | The single node allowed to issue mutating CTI commands per CUCM cluster |
| LeiDis (ARAMIS) | DB operational web application launched on the BKU via the app catalog |
| DWD | Deutscher Wetterdienst — weather integration source (§10) |
| technical_endpoint | A machine signal source (door, BMA, panic button), not a phonebook contact |
| trigger rule | Versioned, typed condition→action mapping over normalized signals (ADR-0004) |
| provider event inbox | Dedupe store for inbound external events (exactly-once under active/active) |
| outbox | Durable, idempotent dispatch of external side effects |
| event_seq | Global monotonic sequence assigned by the PostgreSQL primary; the ordering cursor |
