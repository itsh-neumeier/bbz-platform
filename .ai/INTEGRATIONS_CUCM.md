# Cisco CUCM Integration Baseline

## Selected enterprise approach

Primary real-time interface:
**Cisco JTAPI -> CTI Manager**

Supporting interfaces:
- AXL: provisioning/configuration
- RisPort70: registration/device/application status
- UDS: optional directory/user/device data
- CDRonDemand: optional after-call reconciliation

## BBZ topology

```text
                         Cisco CUCM Cluster
                 +-------------------------------+
                 | CTI Manager SUB01 / SUB02     |
                 | Publisher (AXL)               |
                 | RisPort / UDS                 |
                 +---------------+---------------+
                                 |
                       JTAPI / SOAP / REST
                                 |
              +------------------+------------------+
              |                                     |
      +-------v---------+                   +-------v---------+
      | BBZ-SRV01       |                   | BBZ-SRV02       |
      | cucm-cti-gw     |                   | cucm-cti-gw     |
      | CONTROL_LEADER  |<--- etcd lease -->| HOT STANDBY     |
      +-------+---------+                   +-------+---------+
              |                                     |
              +------------------+------------------+
                                 |
                          BBZ Telephony Core
                                 |
                         Electron/Kiosk Clients
```

## Critical implementation rule

The browser never connects directly to CUCM.

The client sends normalized BBZ telephony commands.
Only the integration gateway knows JTAPI.

## Source references

Cisco DevNet JTAPI:
https://developer.cisco.com/site/jtapi/discover/technical-overview/

Cisco JTAPI feature matrix:
https://developer.cisco.com/site/jtapi/supported-jtapi-feature-matrix/

Cisco CUCM JTAPI compatibility:
https://developer.cisco.com/site/jtapi/jtapi-ucm-compatibility-matrix/

Cisco AXL:
https://developer.cisco.com/docs/axl/axl-developer-guide/

Cisco RisPort:
https://developer.cisco.com/site/sxml/discover/overview/risport/

Cisco UDS:
https://developer.cisco.com/docs/user-data-services/

Cisco CUCM CTI configuration:
https://www.cisco.com/c/en/us/td/docs/voice_ip_comm/cucm/admin/15/systemConfig/cucm_b_system-configuration-guide-15/cucm_b_system-configuration-guide-14_chapter_011001.html

## Pending information from customer environment

Before production implementation collect:

- CUCM exact version and SU
- publisher/subscriber topology
- active CTI Manager nodes
- security mode
- Application User policy
- BBZ DNs
- devices controlled per workplace
- shared lines / hunt pilots
- CTI Route Point usage
- CSS and partitions
- codec/media expectations
- whether audio remains on Cisco endpoint
