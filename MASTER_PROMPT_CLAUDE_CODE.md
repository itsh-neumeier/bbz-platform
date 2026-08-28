# MASTER PROMPT – BBZ / 3-S-Zentrale Management Platform

## 0. Auftrag an Claude Code / Multi-AI Agent

Du arbeitest an einer hochverfügbaren, modularen Leitstellenplattform für eine Bahnhofsbetriebszentrale (BBZ) / 3-S-Zentrale der DB InfraGO AG Personenbahnhöfe.

Dieses Projekt ist **kein einfaches Web-Dashboard**. Es ist eine modular erweiterbare Betriebsplattform mit:

- Ereignismanagement
- Anruf-/Telefoniedokumentation
- geführten Handlungsanweisungen
- Ereignisverantwortung / Übergaben
- Kontakt- und Prioritätsmanagement
- Wetterlage / DWD-Integration
- Monitor-/KVM-Routing
- Audit / Nachbearbeitung / Archiv
- hochverfügbarem 2-Server-Betrieb plus Quorum/Witness
- eigenständigem Chromium-basiertem Arbeitsplatzclient mit Client-Agent
- später Entra ID / LDAP / MFA sowie lokale Benutzer
- frei definierbarer Rollen- und Berechtigungsmatrix
- integrationsfähiger Architektur nach dem Prinzip von Home Assistant

Alle Änderungen müssen nachvollziehbar, testbar, rollback-fähig und über GitHub versioniert sein.

---

# 1. Verbindliche AI-Arbeitsweise

Vor JEDEM Task:

1. Lies:
   - `AGENTS.md`
   - `CLAUDE.md` (wenn du Claude Code bist)
   - `.ai/WORKSPACE.md`
   - `.ai/ARCHITECTURE.md`
   - `.ai/RULES.md`
   - `.ai/CURRENT_STATE.md`
   - `.ai/TASK_PROTOCOL.md`
   - `.ai/FEATURES.md`
   - `.ai/SECURITY.md`
   - `.ai/TESTING.md`
   - `.ai/DEFINITION_OF_DONE.md`
   - relevante ADRs unter `.ai/DECISIONS/`

2. Prüfe, ob der Task eine Architekturentscheidung verändert.
   - Wenn ja: erst ADR erstellen/ändern.
   - Keine stillen Architekturänderungen.

3. Arbeite ausschließlich über:
   `GitHub Issue -> Feature/Fix Branch -> Commits -> Tests -> Pull Request -> Review -> Merge`

4. Niemals direkt auf `main` committen.

5. Niemals bestehende Funktionslogik einfach entfernen, nur weil eine neue Implementierung bequemer wäre.

6. Nach jedem Task:
   - Tests aktualisieren
   - Doku aktualisieren
   - `.ai/CURRENT_STATE.md` aktualisieren
   - offene technische Schulden dokumentieren
   - PR-Zusammenfassung erstellen

---

# 2. Zielarchitektur

## 2.1 Server

Es gibt genau zwei produktive BBZ-Server:

- `BBZ-SRV01`
- `BBZ-SRV02`

Beide sind für Clients **ACTIVE** und können gleichzeitig Requests verarbeiten.

Zusätzlich:

- `BBZ-QUORUM01`

Der Quorum-Knoten speichert keine primären BBZ-Fachdaten, sondern dient als drittes Voting-Mitglied für Cluster-/Failover-Entscheidungen.

### Wichtige Architekturregel

**Active/Active gilt für die Applikationsschicht.**

Die relationale Datenbank darf NICHT als unkontrolliertes 2-Node-Multi-Master-System umgesetzt werden.

Empfohlen:

- PostgreSQL
- Patroni
- etcd oder Consul als Distributed Configuration Store
- 3 Voting Members:
  - BBZ-SRV01
  - BBZ-SRV02
  - BBZ-QUORUM01
- PostgreSQL Primary + synchroner/streamender Standby
- automatischer DB-Failover durch Patroni
- beide API-/Application-Server bleiben aktiv

Damit vermeiden wir Split Brain und behalten konsistente Ereignisverantwortung.

---

# 3. Daten- und Synchronisationsmodell

Das System arbeitet eventorientiert.

Jede fachliche Zustandsänderung wird als atomarer Command verarbeitet und erzeugt einen oder mehrere Audit-/Domain-Events.

Beispiele:

- EVENT_CREATED
- EVENT_ACCEPTED
- EVENT_ACKNOWLEDGED
- EVENT_OPENED
- EVENT_ASSIGNED
- EVENT_TAKEN_OVER
- EVENT_ARCHIVED
- EVENT_REACTIVATED
- ACTION_STEP_COMPLETED
- CALL_RINGING
- CALL_ANSWERED
- CALL_ENDED
- CALL_DOCUMENTED
- CONTACT_CREATED
- CONTACT_PRIORITY_CHANGED
- MONITOR_ROUTE_CHANGED
- WEATHER_EVENT_CREATED

Jedes Event erhält mindestens:

- `event_seq` – global monoton steigende Sequenz
- `event_uuid`
- `aggregate_type`
- `aggregate_id`
- `event_type`
- `occurred_at_utc`
- `occurred_at_local`
- `node_id`
- `user_id`
- `client_id`
- `command_id`
- `correlation_id`
- `payload`
- `schema_version`

### Keine Synchronisation nur über Uhrzeit

Für Catch-up und Reconnect wird primär `event_seq` bzw. DB/WAL-Position verwendet.

Timestamps dienen zur Anzeige und Auditierung, nicht als alleiniger Replikationscursor.

---

# 4. Verhalten bei Serverausfall

Der Client-Agent kennt mindestens beide Server:

- SRV01
- SRV02

Er überwacht:

- `/health/live`
- `/health/ready`
- `/cluster/status`

Wenn der aktuell verwendete Server nicht erreichbar ist:

1. Verbindung sofort auf den anderen verfügbaren Server umstellen.
2. Letzten bekannten `event_seq` mitsenden.
3. Verpasste Events nachladen.
4. UI-Zustand weiterführen.
5. Offene UI-Arbeit soweit möglich erhalten.

Wenn ein Server zurückkehrt:

- PostgreSQL-Replikation holt fehlende WAL-Daten nach.
- App-Knoten wird erst `ready`, wenn Datenstand/Clusterstatus gültig ist.
- Keine manuelle Datenkopie im Anwendungs-Code.

---

# 5. Verhalten wenn BEIDE Server nicht erreichbar sind

Der Chromium-Client darf nicht sofort unbrauchbar werden.

Der lokale Client-Agent hält einen verschlüsselten lokalen Cache.

Offline/Degraded Mode:

Erlaubt:
- bereits geladene Ereignisse lesen
- aktive Gesprächsdokumentation lokal fortführen
- Freitextnotizen lokal erfassen
- lokale Pending-Commands erzeugen
- technischen Status anzeigen

Eingeschränkt:
- Ereignisverantwortung ändern
- Archivierung/Reaktivierung
- Rollen-/Benutzeränderungen
- globale Konfliktoperationen

Offline erzeugte Schreibvorgänge erhalten:
- `command_id`
- `client_timestamp`
- `offline=true`
- lokale Sequenz

Nach Reconnect:
- idempotent synchronisieren
- Konfliktprüfung serverseitig
- UI zeigt klar `UNSYNCED`, `SYNCING`, `SYNCED` oder `CONFLICT`

---

# 6. Technologiestack

## Backend / Core

Empfehlung:

- Python 3.12+
- FastAPI
- Pydantic
- SQLAlchemy 2.x async
- Alembic
- PostgreSQL
- WebSocket/SSE Event Stream
- strukturierte JSON-Logs
- OpenTelemetry vorbereiten
- pytest

Begründung:
- Home-Assistant-ähnliches Integrationsmodell
- Python eignet sich sehr gut für Adapter/Integrationen
- schnelle Erweiterbarkeit
- sauber testbar

## Frontend

- Vue 3
- TypeScript
- PrimeVue
- Pinia
- Vue Router
- i18n vorbereiten
- WCAG-orientierte Bedienbarkeit

Das vorhandene funktionale BBZ-Mockup ist als verbindliche UX-/Feature-Referenz zu behandeln.

## Desktop Client

Chromium-basierter Kiosk-Client:

- Electron
- Vue/PrimeVue Web UI wird eingebettet
- Autostart/Kiosk-Modus
- Update-Mechanismus
- Client-ID / Arbeitsplatz-ID
- Verbindung zum lokalen Client-Agent

## Client-Agent

Empfehlung:
- Go oder Rust als separater lokaler Dienst
- Windows Service bzw. systemnaher Daemon

Aufgaben:
- Server Discovery
- Health Checks
- Failover
- lokaler Cache
- Offline Outbox
- Client-Zertifikat
- Hardware-/OS-Informationen
- Kiosk-Prozessüberwachung
- lokale Integrationsbrücke falls später erforderlich

---

# 7. Home-Assistant-Prinzip / Integrationsarchitektur

Der BBZ-Core darf nicht für jede neue Schnittstelle geändert werden müssen.

Struktur:

```text
server/
  core/
  api/
  domain/
  workflows/
  auth/
  audit/
  integrations/

integrations/
  dwd/
  telephony_mock/
  telephony_sip/
  telephony_cisco/
  monitor_mock/
  monitor_weytec/
```

Jede Integration bekommt z. B.:

```text
integration_name/
  manifest.json
  config_schema.json
  __init__.py
  adapter.py
  services.py
  events.py
  models.py
  diagnostics.py
  tests/
```

`manifest.json` enthält mindestens:

- id
- name
- version
- domain
- dependencies
- minimum_core_version
- capabilities
- config_schema_version

Integrationen müssen über definierte Interfaces mit dem Core kommunizieren.

Keine direkten Cross-Imports in Core-Domainlogik.

---

# 8. Telephony / Cisco Unified Communications Manager (CUCM)

## 8.1 Architekturentscheidung

Für eine konzerngeeignete Cisco-UC-Umgebung ist Cisco Unified Communications Manager (CUCM/UCM)
die primäre Cisco-Telefonieplattform.

Die BBZ-Plattform darf Cisco-Telefonie NICHT direkt aus dem Browser oder aus Vue-Komponenten ansprechen.

Die Cisco-Integration wird als eigener Provider und als separater Gateway-Dienst umgesetzt.

Primärer Cisco-Provider:

- `telephony_cucm_jtapi`

Weitere Provider bleiben unabhängig:

- `telephony_mock`
- `telephony_sip`

Damit ist die BBZ nicht an Cisco gebunden.

## 8.2 Verwendete CUCM-Schnittstellen

### JTAPI / CTI Manager – primär für Echtzeit und Call Control

JTAPI ist die primäre CUCM-Schnittstelle für:

- eingehende Anrufereignisse
- ausgehende Anrufe
- Annehmen
- Auflegen
- Hold / Resume
- Transfer / Redirect
- Konferenzfunktionen soweit freigegeben
- DTMF soweit vom kontrollierten Gerät unterstützt
- Monitoring von Lines / Addresses / Terminals
- Screen-Pop / Caller Context
- CTI Route Points
- CTI Ports
- aktive Call-State-Überwachung

Cisco JTAPI wird in einem separaten Java-Dienst gekapselt:

`cucm-cti-gateway`

Empfehlung:
- Java 8 / kompatibles OpenJDK gemäß CUCM/JTAPI-Kompatibilität
- Maven/Gradle
- Cisco `jtapi.jar` als externe, versionsgebundene Abhängigkeit
- keine Cisco-Binary in einem öffentlichen GitHub-Repository einchecken
- Bereitstellung über autorisierten internen Artifact Store oder Deployment Secret/Volume

Der verwendete JTAPI-Client muss zur produktiven CUCM-Version kompatibel sein.
Die CUCM-Version ist während Onboarding automatisch/administrativ zu erfassen und als
Integrationseigenschaft zu speichern.

### AXL – Provisionierung und Konfigurationsinventar

AXL ist NUR für administrative/configurative Aufgaben vorgesehen, zum Beispiel:

- Geräte/Lines/Route Points inventarisieren
- CTI Route Points lesen/erstellen, wenn das Betriebskonzept dies erlaubt
- Directory Numbers lesen
- Device Associations lesen
- kontrollierte BBZ-Geräte referenzieren
- Konfigurationsvalidierung
- optionale automatisierte Provisionierung nach expliziter Freigabe

AXL darf nicht für Live-Call-State-Polling benutzt werden.

Implementierung:
- SOAP/HTTPS
- versionsgebundenes WSDL
- separater technischer Account mit `Standard AXL API Access`
- Rate Limiting
- Caching
- keine umfangreichen Abfragen in kurzen Intervallen

### RisPort70 – technische Echtzeit-/Registrierungsdiagnose

RisPort70 wird für technische Statusinformationen verwendet:

- Cisco Phone registriert / nicht registriert
- CTI Device Status
- CTI Application Status
- IP-Adresse
- Device Model
- Registration Node

Verwendung:
- Health/Diagnostics
- Leitungs-/Gerätestatus
- Integration Health
- Fehlerdiagnose

Nicht als Call-Control-Schnittstelle verwenden.

Polling muss begrenzt sein.
StateInfo/inkrementelle Abfragen verwenden, wo möglich.

### UDS – optionale Benutzer-/Verzeichnisintegration

UDS ist optional für:

- Directory Search
- Benutzer
- zugehörige Geräte
- Extensions
- Speed Dials
- persönliche CUCM-Einstellungen

Das BBZ-eigene Telefonbuch bleibt ein eigenes Domainobjekt.
UDS-Daten können zur Kontaktanreicherung oder Synchronisation dienen.

### CDRonDemand – optionale Nachprüfung

CDR/CMR dürfen als sekundäre Quelle für:

- Nachbearbeitung
- technische Reconciliation
- Rufhistorienprüfung
- Call-Metadaten

verwendet werden.

CDR ist NICHT die Quelle für Live-Call-Control.

## 8.3 CUCM CTI Gateway

Neue Service-Komponente:

```text
services/
  cucm-cti-gateway/
    src/
    tests/
    Dockerfile
    README.md
    api/
    jtapi/
    state/
    health/
```

Das Gateway übersetzt Cisco-spezifische JTAPI-Objekte in ein BBZ-internes,
herstellerneutrales Telephony Event Model.

Beispiel:

Cisco/JTAPI:
`CallCtlConnOfferedEv`

wird intern zu:

`CALL_OFFERED`

Das restliche BBZ-System darf keine Cisco-JTAPI-Klassen kennen.

## 8.4 Normalisiertes Telephony Event Model

Mindestens:

- CALL_OFFERED
- CALL_RINGING
- CALL_ANSWERED
- CALL_CONNECTED
- CALL_HELD
- CALL_RESUMED
- CALL_TRANSFER_INITIATED
- CALL_TRANSFERRED
- CALL_CONFERENCED
- CALL_DISCONNECTED
- CALL_FAILED
- LINE_IN_SERVICE
- LINE_OUT_OF_SERVICE
- DEVICE_REGISTERED
- DEVICE_UNREGISTERED
- CTI_PROVIDER_IN_SERVICE
- CTI_PROVIDER_OUT_OF_SERVICE

Jedes Telefonieereignis enthält mindestens:

- `telephony_event_id`
- `provider`
- `provider_cluster_id`
- `source_call_id`
- `source_leg_id` wenn verfügbar
- `line_id`
- `device_id`
- `calling_number`
- `called_number`
- `redirecting_number` wenn vorhanden
- `display_name`
- `occurred_at`
- `received_at`
- `gateway_node`
- `raw_event_type`
- `correlation_id`
- `metadata`

## 8.5 Call-ID / Deduplizierung

Für Cisco sollen nach Möglichkeit die von JTAPI bereitgestellten CiscoCallID-Werte verwendet werden:

- CallManagerID
- GlobalCallID

Daraus wird eine stabile `source_call_id` gebildet.

Keine Identifikation eines Anrufes nur anhand:
- Telefonnummer
- Startzeit
- lokaler UI-ID

Die BBZ-eigene Call-ID bleibt zusätzlich unabhängig von Cisco.

## 8.6 CUCM Redundanz innerhalb der BBZ-Redundanz

Cisco JTAPI/CTI Manager unterstützt selbst redundante CTI-Manager-Verbindungen.

Zusätzlich laufen auf:

- BBZ-SRV01
- BBZ-SRV02

je ein `cucm-cti-gateway`.

Beide Container dürfen eine CUCM-Verbindung aufrechterhalten, damit ein Failover schnell erfolgen kann.

Es gibt jedoch pro CUCM-Cluster genau EINEN logischen:

`CONTROL_LEADER`

Leader Election:
- über etcd/Consul Lease
- kurze TTL
- automatische Erneuerung
- kein statischer Primary

Nur der CONTROL_LEADER darf steuernde Commands an CUCM ausführen:

- answer
- dial
- hangup
- hold
- transfer
- conference

Der Standby:
- hält Provider-/Call-State soweit möglich warm
- überwacht Health
- führt keine steuernden Commands aus
- publiziert keine doppelten fachlichen Call-State-Transitions

Nach Leaderwechsel:
1. neuen Lease erhalten
2. JTAPI Provider State prüfen
3. aktuelle Calls/Lines reconciliieren
4. `TELEPHONY_RECONCILED` Audit erzeugen
5. erst dann Steuercommands freigeben

Dadurch bleibt die BBZ-App Active/Active, ohne doppelte Cisco-Steuerbefehle zu erzeugen.

## 8.7 CTI Manager Redundanz

Konfiguration einer CUCM-Integration enthält mehrere CTI Manager Nodes:

```yaml
cti_managers:
  - cucm-sub01.example
  - cucm-sub02.example
```

Das Gateway muss den von Cisco unterstützten CTI/JTAPI-Failover verwenden.

Der Ausfall eines einzelnen CUCM Subscriber/CTI Managers darf die BBZ-Telefonie nicht
dauerhaft unterbrechen.

Status muss im BBZ-System sichtbar sein:

- primary CTI connection
- backup CTI connection
- provider state
- last reconnect
- reconnect count

## 8.8 Betriebsmodell der BBZ-Rufnummern

Die Integration muss zwei Betriebsmodi unterstützen.

### Mode A – Existing Device Control

BBZ steuert/überwacht bereits vorhandene CUCM-Endgeräte:

- Cisco IP Phones
- freigegebene Softclients
- Directory Numbers / Shared Lines

Audio verbleibt auf dem Cisco-Endgerät.

Die BBZ-Weboberfläche ist CTI-Bedienoberfläche:
- Annehmen
- Wählen
- Halten
- Transfer
- Dokumentation
- Caller Context

Dies ist der bevorzugte erste Produktivmodus.

### Mode B – CTI Route Point / Application Routing

Optional:
- zentrale BBZ-Rufnummer auf CTI Route Point
- mehrere simultane Calls
- Anwendung kann Calls beobachten/routen
- Übergabe an Arbeitsplatz-Endgeräte

Dieser Modus wird nur implementiert, wenn das konkrete CUCM-Betriebskonzept dies vorsieht.

Keine Annahme treffen, dass die BBZ selbst Media/RTP terminieren muss.

## 8.9 Medien

JTAPI ist primär Call-Control und stellt nicht automatisch die Audioausgabe des Chromium-Clients bereit.

Baseline:
- Sprache läuft über Cisco-Endgerät / freigegebenes UC-Endgerät
- BBZ Client steuert den Call per CTI

Wenn später Sprache direkt über den BBZ-PC/Headset laufen soll, ist dafür eine eigene
Media-Architektur erforderlich.

Mögliche spätere Variante:
- CTI Port / SIP Media Gateway
- WebRTC Gateway
- RTP Service

Diese Funktion darf nicht implizit in die JTAPI-Integration hineingebaut werden.

## 8.10 CUCM Application Users / Least Privilege

Für Produktion getrennte technische Konten vorsehen:

### `bbz-cucm-cti`
Für JTAPI/CTI.

Mindestens:
- `Standard CTI Enabled`

Zusätzliche Rechte nur nach tatsächlichem Funktionsbedarf, z. B.:
- Control of configured devices
- Connected Transfer/Conference
- Rollover
- Secure Connection

`Standard CTI Allow Control of All Devices` nur verwenden, wenn das genehmigte
Betriebs-/Skalierungskonzept dies erfordert.

Bevorzugt:
- nur BBZ-relevante Geräte / CTI Route Points / Lines kontrollieren
- Least Privilege

### `bbz-cucm-axl`
Nur:
- `Standard AXL API Access`

### `bbz-cucm-serviceability`
Nur notwendige Serviceability/RisPort-Rechte.

Keine gemeinsamen Superuser-Credentials für alle APIs.

## 8.11 Secure CTI

Secure CTI/TLS unterstützen.

Wenn der CUCM-Cluster dies vorsieht:
- `Standard CTI Secure Connection`
- Zertifikatsvalidierung
- interne PKI/Truststore
- keine TLS-Verify-Deaktivierung in Produktion

JTAPI-Truststore wird als Secret/Volume bereitgestellt.

## 8.12 Provider Interface

Das herstellerneutrale BBZ Telephony Provider Interface enthält mindestens:

- initialize()
- health()
- list_lines()
- get_line_state()
- subscribe_call_events()
- get_active_calls()
- dial()
- answer()
- hangup()
- hold()
- resume()
- transfer()
- conference()
- send_dtmf()
- resolve_caller()
- reconcile()

Optionale Capabilities werden im Manifest angegeben.

Beispiel:

```json
{
  "capabilities": {
    "answer": true,
    "hold": true,
    "transfer": true,
    "conference": true,
    "dtmf": true,
    "device_monitoring": true,
    "media_termination": false
  }
}
```

## 8.13 Integration Manifest

`integrations/telephony_cucm/manifest.json`

enthält u. a.:

```json
{
  "id": "telephony_cucm",
  "name": "Cisco Unified Communications Manager",
  "domain": "telephony",
  "adapter": "jtapi_gateway",
  "capabilities": [
    "call_control",
    "call_monitoring",
    "device_monitoring",
    "directory_optional"
  ]
}
```

## 8.14 Integration Health

UI/Admin muss anzeigen:

- CUCM Cluster erreichbar
- CUCM Version
- JTAPI Version
- CTI Provider State
- aktiver CTI Manager
- CONTROL_LEADER
- Standby Gateway
- AXL Status
- RisPort Status
- letzte erfolgreiche Reconciliation
- Anzahl aktiver Calls
- Fehler seit letztem Healthy State

## 8.15 Failure Scenarios

Tests erforderlich:

- CTI Manager 1 fällt aus
- CTI Manager 2 übernimmt
- CONTROL_LEADER BBZ-SRV01 fällt aus
- BBZ-SRV02 übernimmt Lease
- aktiver Call läuft während BBZ-Serverwechsel
- Netzwerkunterbrechung CUCM
- JTAPI Provider OutOfService -> InService
- doppelte Commands
- Retry eines `answer` command
- Reconnect mit bestehenden Calls
- CUCM Publisher nicht verfügbar, CTI Subscriber aber verfügbar
- AXL unavailable ohne Ausfall von Live-Telefonie

## 8.16 TAPI

TAPI ist NICHT die primäre BBZ-Cisco-Integration.

Gründe:
- Windows-/TSP-zentriert
- BBZ-Server laufen containerisiert
- JTAPI eignet sich besser für einen serverseitigen Java-Gateway
- Cisco hat 32-bit-TAPI in neueren CUCM-SU-Ständen als deprecated gekennzeichnet

TAPI kann später als separate Integration ergänzt werden, falls eine konkrete
Bestandsanwendung dies erfordert.

## 8.17 SIP Open Integration

Parallel bleibt eine herstellerneutrale SIP-Integration bestehen.

Sie darf NICHT von Cisco-JTAPI abhängen.

Ziel:
- einfache SIP-Trunks
- alternative PBX
- Lab/Test
- Migration/Fallback
- andere Hersteller

Empfehlung:
- Asterisk oder FreeSWITCH als optionaler SIP/CTI Gateway
- Core spricht immer das normalisierte Telephony Provider Interface

## 8.18 Keine erfundenen CUCM-Details

Vor der Produktivanbindung müssen vorliegen:

- genaue CUCM-Version / SU
- Cluster-Topologie
- CTI Manager Nodes
- BBZ-Geräte / DNs
- Rufnummernkonzept
- CSS/Partitions
- gewünschter Device-Control- oder Route-Point-Modus
- Security Mode
- Application User Rollenfreigabe
- Zertifikatskette

Danach wird die Integration gegen exakt diese Version validiert.


# 9. Monitor-/Weytec-Integration

Monitorrouting ist eigene Integration.

Aktuelle logische Inputs:

- BBZ-OS
- BKU1
- BKU2
- BKU3
- BKU4
- Cayuga 1
- Cayuga 2

Outputs:

- Arbeitsplatzmonitor 1
- Arbeitsplatzmonitor 2
- Arbeitsplatzmonitor 3
- Arbeitsplatzmonitor 4
- Arbeitsplatzmonitor 5
- Arbeitsplatzmonitor 6
- Mittelmonitor / Großbild

Layout Arbeitsplatz:
- 3 x 2

Feste Regel:
- Monitor unten links bleibt immer `BBZ-OS`

Andere Outputs frei belegbar.

Funktionen:
- Drag & Drop
- barrierefreie Select-/Keyboard-Alternative
- Standard-Layout
- gespeicherte Layoutprofile
- Nutzer-/Arbeitsplatzbezogene Layouts

Provider:

1. `monitor_mock`
2. `monitor_weytec`

Weytec-API nicht erfinden.
Nur Interface vorbereiten, bis Dokumentation vorliegt.

---

# 10. Wetter / DWD Integration

Erste echte Integrationsreferenz.

`integrations/dwd`

Funktionen:

- Wetterwarnungen
- Radar/Niederschlag
- lokale Messwerte
- Warnregionen
- Aktualisierung
- Health Status
- Cache

Zielgebiet zunächst:
- Mittelfranken

Beispielorte:
- Nürnberg
- Fürth
- Erlangen
- Schwabach
- Ansbach
- Neustadt a.d. Aisch

Das Frontend bietet:
- Wetterlage-Seite
- Radarzeitleiste
- Warnungen
- betriebliche Bewertung
- Erzeugung eines BBZ-Ereignisses aus einer Wetterwarnung

---

# 11. Authentifizierung

Auth muss providerbasiert sein.

Provider:

- local
- entra_oidc
- ldap_ad

Später:
- Entra ID / OIDC
- LDAP / Active Directory
- MFA / 2FA

Lokale Benutzer müssen weiterhin möglich bleiben.

Lokale Accounts:
- Argon2id
- optional TOTP
- WebAuthn vorbereiten
- Sperr-/Passwortpolicy
- Login Audit

---

# 12. Berechtigungsmodell

Kein fest verdrahtetes Rollenmodell.

Es gibt:

- Benutzer
- Gruppen
- Rollen
- Permissions
- Scopes
- optionale Bedingungen

Rollen können jederzeit neu erstellt werden.

Beispielrollen:

- Sichtleiter
- Disponent
- Administrator
- Nachbearbeitung
- Nur Lesen

Beispiel-Permissions:

## Events

- events.view
- events.create
- events.accept
- events.acknowledge
- events.open
- events.edit
- events.assign
- events.takeover
- events.close
- events.archive
- events.reactivate
- events.postprocess
- events.export

## Measures / Workflows

- workflows.view
- workflows.execute
- workflows.override
- workflows.manage_templates

## Calls

- calls.view
- calls.answer
- calls.dial
- calls.hangup
- calls.hold
- calls.transfer
- calls.document
- calls.view_history

## Contacts

- contacts.view
- contacts.create
- contacts.edit
- contacts.delete
- contacts.assign_priority

## Monitor

- monitor.view
- monitor.route
- monitor.reset_standard
- monitor.manage_profiles

## Weather

- weather.view
- weather.create_event

## Users / Roles

- users.view
- users.manage
- roles.view
- roles.manage
- permissions.manage

## Integrations

- integrations.view
- integrations.configure
- integrations.enable_disable
- integrations.diagnostics

## System

- system.audit.view
- system.cluster.view
- system.cluster.manage
- system.settings.manage

### Scopes

Permissions müssen zusätzlich scoping unterstützen:

- global
- region
- bbz
- workplace
- own_events
- assigned_events

Beispiel:

`events.takeover` nur innerhalb eigener BBZ.

---

# 13. Feature-Set aus dem Mockup – verbindlich

## 13.1 Layout

- feste linke Sidebar
- Content Mitte
- dynamisch horizontal resizebare rechte Kommunikationssidebar
- persistierte Sidebarbreite
- Maus/Touch + Tastaturbedienung
- gemeinsame Topbar über Content + Kommunikation
- große Uhr mit Sekunden
- verfügbare Leitungen
- Monitor-Layout-Button

## 13.2 Sidebar

Enthält:

- DB Branding
- Arbeitsplatz aktiv
- Systeme betriebsbereit
- BBZ / 3-S-Zentrale
- Navigation
- eingeloggter Nutzer
- Gruppe/Rolle

## 13.3 Ereignisspeicher

Oben auf Arbeitsplatzseite.

Gemeinsame Arbeitswarteschlange.

Aktionen immer sichtbar:

- Annehmen
- Quittieren
- Bearbeiten
- Archivieren

Klick auf Ereignis:
- öffnet Meldung unten im Content

Prioritäten:
- kritisch
- hoch
- mittel
- niedrig

Kritisch und hoch:
- deutlich animiert
- `prefers-reduced-motion` respektieren

## 13.4 Ereignisverantwortung

Verantwortung gilt für das GESAMTE Ereignis.

Nicht pro Maßnahmenschritt.

Funktionen:

- Ereignis an Nutzer übertragen
- Nutzerstatus sichtbar
- verfügbar
- Pause
- offline

Wenn Verantwortlicher Pause/offline:
- berechtigte Nutzer können `Ereignis übernehmen`

Übernahmen müssen auditiert werden.

## 13.5 Maßnahmen

Nach Öffnen des Ereignisses unten anzeigen.

Nur bearbeitbar wenn:
- Ereignis angenommen
- quittiert
- Benutzer berechtigt

Schritte:
- nummeriert
- Status
- Zeitstempel
- Audit
- Fortschritt

## 13.6 Archiv

Archivierte Ereignisse:

- nicht mehr in Arbeitswarteschlange
- bleiben chronologisch in Ereignisse-Ansicht
- vollständig detailliert einsehbar
- Nachbearbeitungsnotizen möglich

Reaktivierung:
- niemals Ein-Klick
- explizites Warn-/Bestätigungspopup
- Berechtigung prüfen
- Audit-Event EVENT_REACTIVATED

## 13.7 Globale Prioritätswarnung

Auf allen Seiten AUSSER Arbeitsplatz:

Wenn ein:
- HOHES oder
- KRITISCHES

Ereignis noch NICHT angenommen wurde:

Topbar zeigt auffällige rote Warnung vor Uhrzeit.

Klick:
- wechselt auf Arbeitsplatz
- öffnet betreffendes Ereignis

## 13.8 Telefon

Rechte Sidebar dauerhaft verfügbar.

Tabs z. B.:

- Telefon
- Gespräch
- Telefonbuch
- Historie

Funktionen:

- Wählfeld
- mehrere wartende Anrufe
- bekannte Nummern
- unbekannte Nummern
- Annehmen
- Ablehnen
- Auflegen
- Gesprächsdauer
- Leitungsstatus

## 13.9 Telefonbuch

Kontakte:

- anlegen
- bearbeiten
- suchen
- Kurzwahl
- Priorität

Prioritäten:

### niedrig
Standardanruf
Darstellung: blau

### mittel
wichtiger Kontakt
Darstellung: orange

### hoch
betriebsrelevanter Kontakt
Darstellung: rot

Eingehende Anrufe werden anhand Rufnummer automatisch Kontakt und Priorität zugeordnet.

Anrufwarteschlange:
- niedrig blau
- mittel orange
- hoch rot
- animierter Hintergrund
- hoch stärkere Animation
- reduced-motion berücksichtigen
- Sortierung nach Priorität

## 13.10 Pflicht-Anrufdokumentation

Jeder angenommene Anruf muss kategorisiert werden.

Kategorien:

- Auskunftsersuchen
- Technische Störung
- Reinigungsmeldung Kunde
- EVU & EVI Mitteilung
- Anderes

Zusätzlich:
- optionaler Freitext

Dokumentation:
- während des Gesprächs inline möglich

Wenn beim Auflegen keine Kategorie gesetzt:
- Pflicht-Popup
- Abschluss erst nach Dokumentation

Dokumentation wird auditiert.

## 13.11 Kurzwahl

Kein permanentes Kurzwahlgitter.

Button:
- `Kurzwahl öffnen`

Danach Dialog/Overlay.

## 13.12 Wetterlage

Eigene Seite:

- Mittelfranken
- DWD Radar
- Warnungen
- Wetterwerte
- betriebliche Bewertung
- Wetterereignis erzeugen

---

# 14. Persistenzmodell – fachliche Kernobjekte

Mindestens:

- users
- auth_identities
- roles
- permissions
- role_permissions
- user_roles
- user_presence

- workplaces
- clients
- client_agents

- events
- event_assignments
- event_status_history
- event_notes
- event_archive

- workflow_templates
- workflow_instances
- workflow_steps
- workflow_step_results

- calls
- call_participants
- call_documentation
- lines

- contacts
- contact_numbers
- contact_priorities

- integrations
- integration_configs
- integration_health

- monitor_inputs
- monitor_outputs
- monitor_routes
- monitor_profiles

- weather_alerts
- weather_observations

- audit_events
- domain_events
- commands

---

# 15. API-Grundsätze

REST für Commands/Queries + WebSocket/SSE für Live Updates.

Alle schreibenden Requests:

- command_id / idempotency key
- authenticated user
- client_id
- workplace_id
- optimistic concurrency version

Beispiel:

`POST /api/events/{id}/accept`

Payload:

```json
{
  "command_id": "uuid",
  "expected_version": 7
}
```

Konflikt:
- HTTP 409
- neuer Serverstand zurückgeben

---

# 16. Echtzeit

Clients abonnieren Event Stream.

Beispiel:

`GET /api/events/stream?after_seq=3842`

oder WebSocket:

`/ws/events?after_seq=3842`

Nach Reconnect:
- Catch-up ab letztem bestätigten `event_seq`
- danach Live Stream

---

# 17. Audit

Audit ist unveränderlich.

Audit-Einträge niemals hart löschen.

Audit beinhaltet:

- wer
- wann
- wo
- Arbeitsplatz
- Client
- Aktion
- vorher
- nachher
- Grund falls erforderlich
- correlation_id

Kritische Aktionen:

- Übernahme
- Übergabe
- Archivierung
- Reaktivierung
- Rollenänderungen
- Integrationsänderungen
- Monitorrouting
- Anrufdokumentation

---

# 18. GitHub Workflow

Pflichtworkflow:

1. GitHub Issue
2. Branch
3. Umsetzung
4. lokale Tests
5. CI
6. Pull Request
7. Review
8. Merge

Branch Naming:

- `feature/<issue>-<short-name>`
- `fix/<issue>-<short-name>`
- `refactor/<issue>-<short-name>`
- `docs/<issue>-<short-name>`

Commit Style:

Conventional Commits:

- feat:
- fix:
- docs:
- refactor:
- test:
- chore:

Kein Force-Push auf main.

---

# 19. CI/CD

GitHub Actions.

Pipeline:

- lint backend
- type checks
- unit tests
- integration tests
- frontend lint
- frontend tests
- e2e smoke tests
- security scan
- container build
- SBOM
- image signieren
- push nach GHCR

Deployment:
- Releases/Tags
- kein ungeprüfter `latest` in Produktion
- versionierte Container Images

---

# 20. Docker / Deployment

Je BBZ Server:

- bbz-api
- bbz-web
- postgres
- patroni
- etcd/consul member
- reverse proxy
- optional telemetry collector

Quorum:

- etcd/consul third member
- optional cluster monitoring

Keine Fachlogik im Quorum.

---

# 21. Updates

Rolling Deployment:

1. Cluster gesund prüfen
2. DB Migration prüfen
3. SRV02 aktualisieren
4. Health prüfen
5. SRV01 aktualisieren
6. Cluster prüfen

DB-Migrationsstrategie:
- expand / migrate / contract
- mindestens eine Version rückwärtskompatibel während Rolling Update

---

# 22. Security

Mindestens:

- TLS
- mTLS für Client-Agent optional/vorbereiten
- Secrets niemals im Git
- Docker Secrets / Secret Store
- Argon2id lokal
- MFA vorbereiten
- OIDC State/PKCE
- CSRF Schutz soweit relevant
- Rate Limits
- Security Headers
- CSP
- Input Validation
- Audit Logging
- Dependency Scanning
- Container nicht als root, sofern möglich

---

# 23. Observability

Endpoints:

- `/health/live`
- `/health/ready`
- `/health/details`
- `/cluster/status`

Metriken:

- API latency
- DB state
- replication lag
- active server
- connected clients
- WebSocket connections
- pending offline commands
- call line status
- integration health

---

# 24. Testing

Erforderlich:

## Unit
- Domainregeln
- Permissions
- Event transitions
- Archivierung
- Reaktivierung
- Call documentation

## Integration
- DB
- API
- auth
- integration adapters

## HA
Simulation:

- SRV01 down
- SRV02 down
- DB primary loss
- network isolation
- witness unavailable
- server recovery
- client reconnect
- catch-up event stream

## E2E
Mindestens:

1. Ereignis erzeugen
2. annehmen
3. quittieren
4. bearbeiten
5. übertragen
6. übernehmen
7. Maßnahmen abschließen
8. archivieren
9. Archivdetails ansehen
10. reaktivieren per Bestätigung

Telefon:

1. incoming call
2. Priorität erkennen
3. annehmen
4. Kategorie setzen
5. Freitext
6. auflegen
7. Audit prüfen

---

# 25. Erste Implementierungsphasen

## Phase 0 – Repository Foundation

Erstellen:

- Monorepo
- AI Workspace
- README
- Docker dev environment
- CI baseline
- coding conventions
- ADR system

Noch keine komplexe Fachlogik.

## Phase 1 – Core Domain

- users
- roles
- permissions
- workplaces
- events
- event ownership
- audit
- event stream
- workflow engine

## Phase 2 – HA Foundation

- PostgreSQL + Patroni
- etcd/Consul quorum
- 2 application nodes
- health
- failover tests
- client catch-up model

## Phase 3 – Frontend Foundation

Mockup in echte Vue/PrimeVue-Struktur überführen.

Keine UX-Verschlechterung gegenüber Mockup.

## Phase 4 – Desktop Client + Agent

- Electron kiosk
- Agent service
- server discovery
- reconnect
- local cache
- outbox

## Phase 5 – Telefonie

- mock provider
- SIP provider
- Cisco CUCM JTAPI gateway + mock mode + AXL/RisPort health adapters

## Phase 6 – Contacts / Priorities

- CRUD
- incoming call matching
- priority visualization

## Phase 7 – DWD

- Live weather
- warnings
- radar
- event creation

## Phase 8 – Monitor Routing

- mock
- Weytec interface
- real integration nach Doku

## Phase 9 – Enterprise Auth

- Entra
- LDAP
- MFA
- advanced RBAC

---

# 26. Nicht verhandelbare Qualitätsregeln

1. Keine Änderung ohne Git-Historie.
2. Keine direkte Arbeit auf main.
3. Keine Integrationslogik im Core.
4. Keine UI-only Business Rules.
5. Keine Server-spezifischen Dateninseln.
6. Keine Replikation nur über Timestamps.
7. Keine archivierten Ereignisse hart löschen.
8. Keine Reaktivierung ohne explizite Bestätigung.
9. Keine Anrufbeendigung ohne Pflichtkategorisierung.
10. Keine erfundene CUCM-, Cisco- oder Weytec-API; nur dokumentierte Cisco-Interfaces verwenden.
11. Keine Berechtigungsprüfung ausschließlich im Frontend.
12. Jede kritische Aktion muss Audit erzeugen.
13. `prefers-reduced-motion` respektieren.
14. Bedienung darf nicht ausschließlich auf Drag & Drop beruhen.
15. Alle Commands idempotent gestalten.

---

# 27. Startauftrag an Claude Code

Beginne NICHT sofort mit der kompletten Implementierung.

Arbeite in dieser Reihenfolge:

1. Repository analysieren.
2. Falls leer: Foundation-Struktur anlegen.
3. `.ai/` Workspace erstellen/prüfen.
4. Architektur-ADRs erstellen.
5. GitHub Issues für Phase 0 und Phase 1 vorbereiten.
6. Monorepo-Grundstruktur anlegen.
7. Docker Development Environment erstellen.
8. Backend/Frontend Skeleton aufbauen.
9. Test- und CI-Grundlage anlegen.
10. Erst danach Feature-Implementierung starten.

Erstelle vor umfangreichen Änderungen einen kurzen Plan und dokumentiere:
- Scope
- Dateien
- Risiken
- Tests
- Rollback

Wenn Anforderungen unklar sind:
- nicht raten
- offene Frage dokumentieren
- minimalen Adapter/Stub implementieren

Das bestehende funktionale BBZ-Mockup ist Feature-Referenz und darf bei der produktiven Umsetzung in Bedienlogik und Funktionsumfang nicht stillschweigend reduziert werden.


---

# 28. BKU Arbeitsplatz-Agent

Neben dem `BBZ Client Agent` existiert ein eigenständiger `BKU Agent` auf dem korrespondierenden BKU-Arbeitsplatz.

Der BKU Agent ist per Enrollment fest an `workplace_id` und `agent_id` gebunden und verbindet sich redundant mit BBZ-SRV01/SRV02.

## 28.1 Aufgaben

- Health/Online-Status melden
- interaktive BKU-Session erkennen
- zentral definierte Webanwendungen im Chrome/Chromium-basierten Unternehmensbrowser starten
- Fenster fokussieren/öffnen, soweit unterstützt
- autorisiertes Abmelden der interaktiven Sitzung
- autorisierten Neustart des BKU-Clients
- Diagnoseinformationen liefern

Der normale Nutzer darf KEINE beliebigen URLs, Shell-Kommandos, PowerShell-Kommandos oder Executable-Pfade an den Agent senden.

## 28.2 Link-/Anwendungskatalog

Der BBZ-Server verwaltet zentral einen Katalog für Tagesbetriebsanwendungen, z. B.:

- LeiDis (ARAMIS)
- weitere freigegebene DB-Webanwendungen

Jeder Eintrag besitzt mindestens:

- app_id
- Name
- URL
- Icon
- Launch Mode
- Ziel `BKU` oder später weitere Targets
- Rollen/Scopes
- Standort/Arbeitsplatzscope optional
- enabled
- Version

Der BBZ Client zeigt diese Einträge als zentral gepflegte Buttons. Individuelle Browser-Lesezeichen sind nicht erforderlich.

## 28.3 Schichtwechsel

Der BBZ-Client zeigt den Sessionstatus des gebundenen BKU-Clients. Wenn die vorherige Sitzung noch aktiv ist, können entsprechend berechtigte Nutzer nach expliziter Bestätigung:

- BKU-Benutzer abmelden
- BKU-Client neu starten

Jede Aktion ist auditiert.

Neue Permissions:

- `bku.status.view`
- `bku.apps.launch`
- `bku.apps.close`
- `bku.session.logout`
- `bku.device.restart`
- `bku.catalog.manage`
- `bku.agent.manage`

---

# 29. Technische Kontakte / Technische Endpunkte

Technische Systeme dürfen NICHT als normale Kontakte im Telefonbuch modelliert werden.

Neue Domain: `technical_endpoints`.

Beispiele:

- Siedle Tür-/Klingelanlage
- Brandmeldeanlage
- zukünftige Alarmwähler

Ein technischer Endpoint kann über Calling Number, Called Number, CTI Route Point und Provider-Kontext erkannt werden.

Administratoren konfigurieren versionierte Triggerregeln.

Typed Actions:

- Event erzeugen
- Workflow zuordnen
- Client Popup
- Kameraaktion
- Call annehmen
- DTMF senden
- Call beenden
- Notification
- Integration Action

Keine frei programmierbaren Scripts im Admin-Editor.

Active/Active-Regel:
Alle Trigger und externen Side Effects müssen Inbox/Outbox/Idempotency verwenden, damit ein doppeltes Provider-Event niemals eine Tür zweimal öffnet oder ein BMA-Ereignis doppelt erzeugt.

---

# 30. Siedle Türkommunikation über Telefonie / DTMF

Die erste Siedle-Integration verwendet die bestehende Telefonieintegration.

Siedle Access kann Türöffnerfunktionen über konfigurierbare DTMF/MFV-Codes auslösen. Der konkrete Code ist Konfiguration/Secret und wird NICHT im Core hardcodiert.

Der `telephony_cucm` Provider muss – wenn der kontrollierte Call dies unterstützt – die normalisierte Capability `send_dtmf()` anbieten.

## 30.1 Klingelprozess

1. eingehender CUCM/JTAPI Call
2. technische Rufnummer wird einem Siedle Endpoint zugeordnet
3. Trigger `DOORBELL_RINGING`
4. zugeordnete Cayuga Kamera öffnen/anfordern
5. unten rechts im BBZ-Client zeitlich begrenztes Popup: `Klingeln: <Bezeichnung>`
6. Nutzer kann `Öffnen` auswählen

## 30.2 Öffnen

`Öffnen` führt transaktional/idempotent aus:

1. Permission `door.open` prüfen
2. Call annehmen, falls für DTMF noch erforderlich
3. CONNECTED/Media Ready abwarten
4. konfiguriertes DTMF-Profil senden
5. definierte kurze Nachlaufzeit
6. Call automatisch beenden
7. Audit erzeugen

Der Audit speichert NICHT den Klartext-DTMF-Code.

Neue Permissions:

- `door.view`
- `door.answer`
- `door.open`
- `door.configure`
- `technical_endpoints.view`
- `technical_endpoints.manage`

---

# 31. Cayuga Video Integration

Eigene Integration: `integration_cayuga`.

API-Dokumentation liegt noch nicht vor.

NICHT erfinden:

- URL-Pfade
- Auth-Verfahren
- Kameraobjektmodell
- Client-Steuerungsmethode

Nur normalisierte Capability-Schnittstellen vorbereiten, z. B.:

- health
- camera resolve/mapping
- camera open/request for workplace
- optional camera list/search

Siedle Endpoint -> Cayuga Camera Mapping ist Admin-Konfiguration.

Wenn Cayuga ausfällt, muss das Klingel-Popup trotzdem erscheinen. Video und Klingelprozess sind entkoppelte Actions.

---

# 32. BMA über technische Telefonnummer

Eine Brandmeldeanlage kann über eine separate konfigurierte Telefonnummer/Route einen Alarmcall auslösen.

Die technische Endpoint-/Triggerkonfiguration definiert:

- Matching
- Ereignistyp
- Priorität (typisch kritisch, aber konfigurierbar)
- Standort/Anlage
- zu verwendende Handlungsanweisung / Workflow Template Version
- optionale Call Actions

Flow:

1. CALL_RINGING normalisiert
2. BMA Endpoint match
3. exakt ein BBZ-Ereignis erzeugen
4. Workflow Template Version anhängen
5. Prioritätswarnung auslösen
6. Ereignis in Ereignisspeicher bereitstellen
7. weitere Prozessschritte über Workflow Engine

---

# 33. EPK Handlungsanweisungs-Editor

Handlungsanweisungen müssen im Adminbereich grafisch administrierbar sein.

Modell:

- Ereignis-Knoten
- Funktions-/Aufgaben-Knoten
- AND Connector Split/Join
- OR Connector Split/Join
- XOR Connector Split/Join

Aufgaben können sein:

- manuelle Aufgabe
- Bestätigung
- Dokumentation
- Integration Action
- Notification
- Timer/Wait
- Event Update

## 33.1 Versionierung

Lifecycle:

- DRAFT
- VALIDATED
- PUBLISHED
- DEPRECATED

Ein laufendes Ereignis bleibt auf der beim Start verwendeten Workflow-Version. Neue Änderungen dürfen laufende Instanzen nicht still verändern.

## 33.2 Bedingungen

OR/XOR-Bedingungen verwenden eine sichere eingeschränkte Rule DSL. Kein Python/JavaScript eval.

## 33.3 Editor

- Drag & Drop
- zusätzlich vollständig bedienbare Nicht-Drag-/Tastaturalternative
- Eigenschaftenpanel
- Graphvalidierung
- Simulation/Testlauf
- Publish mit Version/Changelog

Der Bediener sieht im laufenden Ereignis eine klare Schritt-für-Schritt-Ausführung des Graphen.

Die Verantwortung bleibt am GESAMTEN Ereignis und wird NICHT auf einzelne Workflow-Schritte verteilt.

---

# 34. Zusätzliche Persistenzobjekte

- bku_agents
- bku_agent_enrollments
- bku_agent_commands
- application_catalog
- application_catalog_scopes
- technical_endpoints
- technical_endpoint_numbers
- trigger_rules
- trigger_rule_versions
- trigger_executions
- external_action_outbox
- integration_camera_mappings
- door_action_profiles
- client_popup_events
- workflow_template_versions
- workflow_graph_nodes
- workflow_graph_edges
- workflow_tokens
- workflow_decisions

---

# 35. Zusätzliche Pflicht-E2E-Tests

## BKU

1. Agent enrollt sich an Arbeitsplatz
2. BBZ Client sieht Onlinezustand
3. LeiDis/ARAMIS wird über Katalogbutton gestartet
4. nicht freigegebene URL wird abgelehnt
5. Schichtwechsel -> Abmelden mit Bestätigung
6. Neustart mit Bestätigung
7. Audit vorhanden
8. SRV01-Ausfall -> Agent arbeitet über SRV02 weiter

## Siedle/Cayuga

1. Siedle Call trifft ein
2. technische Rufnummer wird erkannt
3. Cayuga Kameraaktion wird ausgelöst
4. BBZ Klingelpopup erscheint
5. Nutzer klickt Öffnen
6. Call wird falls nötig angenommen
7. DTMF genau einmal gesendet
8. Call automatisch beendet
9. Audit ohne Klartext-DTMF-Secret
10. Duplicate Provider Event erzeugt keine zweite Öffnung

## BMA

1. BMA Call trifft ein
2. technischer Endpoint erkannt
3. genau ein kritisches Ereignis erzeugt
4. richtige Workflow-Version gebunden
5. Ereignis im Ereignisspeicher sichtbar

## EPK

- AND Pfad korrekt
- XOR Pfad korrekt
- OR Mehrfachpfad korrekt
- ungültiger Graph nicht publizierbar
- neue Template-Version verändert laufende Instanz nicht
---

# 36. Coda Video (HxGN dC3 Video) – Video- und Alarmquelle

Die bisher als Cayuga bezeichnete Videoplattform wird im Projekt kanonisch als `Coda Video (HxGN dC3 Video)` / Integration `coda_video` geführt.

Coda ist nicht nur Kamera-Integration, sondern kann technische Alarmereignisse an die BBZ-Plattform liefern.

Pflichtanwendungsfall:

- Überfallmeldeknopf / Panic / Duress Alarm wird in Coda ausgelöst
- Alarmquelle wird über externe Source-ID auf einen BBZ Technical Endpoint gemappt
- BBZ erzeugt exakt ein Ereignis
- konfigurierbare Priorität, standardmäßig für Überfallalarm `KRITISCH`
- veröffentlichte EPK-Handlungsanweisung wird gebunden
- zugeordnete Kamera(s) werden als unabhängige Side-Effect-Aktion geöffnet
- Operator erhält Popup + Ereignis im Ereignisspeicher
- gesamte Bearbeitung/Auditierung erfolgt im BBZ-Ereignis

Admin-Konfiguration muss pro Coda-Alarmquelle erlauben:

- Provider/Instanz
- External Source ID
- Bezeichnung
- Standort/Bahnhof
- Alarmtyp/Subtyp
- BBZ-Priorität
- Kamera-Mappings
- Popup-Profil
- EPK Workflow Template/Version
- Eskalationsprofil
- Aktiv/Deaktiviert

Active/Active-Pflicht:

- Provider Inbox
- Deduplication
- idempotente Rule Executions
- Outbox
- Replay-safe Reconnect

Ein mehrfach zugestellter Coda-Alarm darf niemals mehrere BBZ-Ereignisse erzeugen.

Die konkrete Herstellerintegration darf nur anhand offizieller Coda/HxGN-dC3-Dokumentation implementiert werden. Öffentlich bekannte Integrationsoptionen sind lediglich Architekturhinweise und kein Ersatz für die projektspezifische API/SDK-Dokumentation.

## 36.1 Pflicht-E2E-Test Überfallalarm

1. Coda Mock Provider erzeugt Panic Alarm
2. Provider Event wird persistiert
3. Technical Endpoint wird gemappt
4. exakt ein KRITISCHES BBZ-Ereignis entsteht
5. korrekte EPK-Version ist gebunden
6. Alarm-Popup erscheint
7. zugeordnete Kameraaktion wird angefordert
8. Kameraaktion darf fehlschlagen, Ereignis bleibt aktiv
9. Duplicate Provider Event erzeugt kein zweites Ereignis
10. SRV01-Ausfall/Replay über SRV02 erzeugt kein Duplikat

