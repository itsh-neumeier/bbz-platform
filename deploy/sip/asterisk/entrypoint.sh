#!/bin/sh
# BBZ SIP lab entrypoint (E13-09, ADR-0034). If BBZ_API is set, pull the
# generated trunk config once after Asterisk is up; then run Asterisk in the
# foreground as PID 1. Without BBZ_API this is just `asterisk -f` (the E13-08
# integration tests don't need a trunk).
set -eu

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
