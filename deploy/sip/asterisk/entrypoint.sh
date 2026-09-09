#!/bin/sh
# BBZ SIP lab entrypoint (E13-09, ADR-0034). If BBZ_API is set, pull the
# generated trunk config once after Asterisk is up; then run Asterisk in the
# foreground as PID 1. Without BBZ_API this is just `asterisk -f` (the E13-08
# integration tests don't need a trunk).
set -eu

# WebRTC media on Docker Desktop (E13-11 / ADR-0035): the browser runs on the
# Docker host and reaches our PUBLISHED RTP range at the host, never our
# container IP (the only ICE host candidate Asterisk offers by default). Rewrite
# that candidate to an address the browser both accepts and can reach:
#   BBZ_ICE_HOST_IP  the host's LAN IP (e.g. 192.168.1.20). REQUIRED for audio
#                    on Docker Desktop — Chrome silently drops a 127.0.0.1
#                    remote candidate when it has no loopback candidate of its
#                    own, so the loopback fallback only works in narrow cases.
# LAB ONLY (a real site's Asterisk has a routable address). Harmless if rtp.conf
# already carries the section.
if ! grep -q '^\[ice_host_candidates\]' /etc/asterisk/rtp.conf 2>/dev/null; then
  _myip="$(getent hosts "$(hostname)" 2>/dev/null | awk '{print $1; exit}' || true)"
  _adv="${BBZ_ICE_HOST_IP:-127.0.0.1}"
  if [ -n "${_myip:-}" ]; then
    printf '\n[ice_host_candidates]\n%s => %s\n' "$_myip" "$_adv" >> /etc/asterisk/rtp.conf
    echo "bbz: ICE host candidate ${_myip} => ${_adv}"
  fi
fi

if [ -n "${BBZ_API:-}" ]; then
  (
    # BBZ may still be booting alongside us — retry the pull a few times
    sleep "${BBZ_SYNC_DELAY:-8}"
    i=0
    until /usr/local/bin/sync-trunk-config.sh; do
      i=$((i + 1))
      [ "$i" -ge "${BBZ_SYNC_RETRIES:-6}" ] && {
        echo "bbz: initial trunk sync failed after $i tries (non-fatal)" >&2
        break
      }
      sleep 10
    done
  ) &
fi

exec asterisk -f -p -T -vvv
