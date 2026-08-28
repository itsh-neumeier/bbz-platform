# services/cucm-cti-gateway/libs/

Cisco proprietary binaries (`jtapi.jar` and companions) are **NOT** stored in
this repository (ADR-0002 §12).

At build/deploy time, `jtapi.jar` — matching the productive CUCM version/SU — is
provided here from an authorized internal artifact store or mounted as a
secret/volume. `*.jar` in this directory is git-ignored.
