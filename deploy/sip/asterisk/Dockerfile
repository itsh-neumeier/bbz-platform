# BBZ SIP lab PBX — Asterisk 20 LTS for the `telephony_sip` integration tests
# (roadmap E13-08, ADR-0023) and the E13-09 trunk-config sync (ADR-0034).
#
# NOT a production image and never deployed: ARI is reachable with a well-known
# throwaway credential, `allowed_origins=*`, and the dialplan only drives `Local`
# channels into the Stasis app. A real BBZ site points `telephony_sip` at THEIR
# Asterisk from the admin UI (ADR-0033) and runs sync-trunk-config.sh on their
# own box.
#
# ubuntu:24.04, not debian: Debian dropped the asterisk package after bullseye;
# Ubuntu noble carries Asterisk 20 LTS (full ARI + Stasis) in the default image.
#
# Build context is deploy/sip/ (so the sync script is reachable); the Dockerfile
# is asterisk/Dockerfile.
FROM ubuntu:24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends asterisk curl ca-certificates; \
    apt-get purge -y --auto-remove; \
    rm -rf /var/lib/apt/lists/*; \
    # the package creates the `asterisk` user/group; make sure its runtime dirs
    # are writable by it (the container runs as that user, not root). The MoH
    # tree (E13-12) is where sync-trunk-config.sh drops uploaded hold music.
    install -d -o asterisk -g asterisk \
        /var/run/asterisk /var/lib/asterisk /var/log/asterisk /var/spool/asterisk \
        /var/lib/asterisk/moh/bbz

# Overlay just the files the lab overrides; the packaged defaults (asterisk.conf
# with the correct paths, etc.) stay in place.
COPY --chown=asterisk:asterisk asterisk/etc/ /etc/asterisk/
COPY sync-trunk-config.sh asterisk/entrypoint.sh /usr/local/bin/
RUN chmod 0755 /usr/local/bin/sync-trunk-config.sh /usr/local/bin/entrypoint.sh

USER asterisk
EXPOSE 8088 5060/udp
# -f  foreground (PID 1)   -p  no realtime prio (non-root)   -T  timestamp logs
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
