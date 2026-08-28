# .ai/FEATURES.md

The current functional mockup is the product feature baseline.

Important features:
- event store/work queue
- accept/ack/open/archive
- full-event ownership
- user transfer/takeover
- archive details/postprocessing/reactivation confirmation
- animated high/critical alerts
- global topbar alert for unaccepted high/critical events
- phone panel
- keypad
- incoming call queue
- contact priority blue/orange/red
- call priority animation
- contact CRUD
- mandatory call categorization
- optional call free text
- phonebook
- quick dial dialog
- DWD weather page
- monitor routing dialog
- 6 workplace monitors + large display
- BBZ-OS fixed on lower-left monitor
- standard monitor layout
- resizable right sidebar
- accessibility

Additional required features:
- dedicated BKU Agent bound to each BBZ workplace
- remotely visible BKU health/session state
- controlled BKU logout and restart with permission + confirmation + audit
- centrally administered operational web-app/link catalog
- launch allowlisted apps such as LeiDis (ARAMIS) in Chrome on the paired BKU client
- technical contacts/endpoints separate from human phonebook
- telephone-number based technical trigger rules
- Siedle door-station workflow via telephony + DTMF
- Cayuga camera action on doorbell ring via dedicated integration
- bottom-right BBZ client doorbell popup
- BMA telephone trigger creates an event and attaches a configured workflow
- admin-configurable trigger rules
- graphical EPK-style workflow editor
- AND / OR / XOR connectors
- versioned workflow templates and immutable running template version
- Coda Video (HxGN dC3 Video) as canonical video integration
- Coda Video as inbound alarm source, not camera-only
- panic/duress/Überfallmeldeknopf alarms from Coda create BBZ events
- Coda alarm-source mapping to station/location/cameras/priority
- Coda alarm-to-versioned-EPK workflow mapping
- exactly-once alarm ingestion and replay-safe failover
- camera action failure must not block alarm/event creation

