# .ai/ARCHITECTURE.md

## Logical Architecture

BBZ Workplace Client:
- Electron/Chromium Kiosk
- Vue 3 + PrimeVue
- BBZ Client Agent (local service)

BKU Workplace Client:
- corporate BKU workstation
- BKU Agent (local service)
- bound 1:1 to a BBZ workplace by enrollment
- centrally managed web-app/link catalog

Servers:
- BBZ-SRV01
- BBZ-SRV02

Witness:
- BBZ-QUORUM01

Data:
- PostgreSQL
- Patroni
- etcd/Consul quorum

Both application servers are active.
Database writes are not uncontrolled multi-master.

## Core Modules
- identity
- authorization
- events
- workflows
- calls
- contacts
- audit
- integrations
- monitor
- weather
- cluster

Additional Core/Platform Modules:
- technical_endpoints
- technical_triggers
- application_catalog
- workplace_agents
- workflow_graph
- client_actions

Agent rule:
BBZ Client and BKU Agent do not trust/control each other directly. Commands are authenticated, authorized and routed through the BBZ server/event layer.

## Coda Video / Physical Security

Canonical integration: `coda_video`.

It has two independent capability groups:
- video presentation/control
- inbound alarm/event ingestion

Core modules include `technical_alarm_ingress` and `provider_event_inbox`.

Coda panic/duress alarms are normalized before entering the trigger engine. Vendor payloads never become direct business-rule dependencies.

Marker: coda_video_alarm_ingress
