# BBZ SIP lab PBX — Asterisk 20 LTS for the `telephony_sip` integration tests
# (roadmap E13-08, ADR-0023).
#
# NOT a production image and never deployed: ARI is reachable with a well-known
# throwaway credential, `allowed_origins=*`, and the dialplan only drives `Local`
# channels into the Stasis app. A real BBZ site points `telephony_sip` at THEIR
# Asterisk from the admin UI (ADR-0033).
#
# ubuntu:24.04, not debian: Debian dropped the asterisk package after bullseye;
# Ubuntu noble carries Asterisk 20 LTS (full ARI + Stasis) in the default image.
FROM ubuntu:24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends asterisk; \
    apt-get purge -y --auto-remove; \
    rm -rf /var/lib/apt/lists/*; \
    # the package creates the `asterisk` user/group; make sure its runtime dirs
    # are writable by it (the container runs as that user, not root)
    install -d -o asterisk -g asterisk \
        /var/run/asterisk /var/lib/asterisk /var/log/asterisk /var/spool/asterisk

# Overlay just the files the lab overrides; the packaged defaults (asterisk.conf
# with the correct paths, etc.) stay in place.
COPY --chown=asterisk:asterisk etc/ /etc/asterisk/

USER asterisk
EXPOSE 8088 5060/udp
# -f  foreground (PID 1)          -T  timestamp log lines
# -p  do NOT request realtime priority — we are not root and would only warn
CMD ["asterisk", "-f", "-p", "-T", "-vvv"]
