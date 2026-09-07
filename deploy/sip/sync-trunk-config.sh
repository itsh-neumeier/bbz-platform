#!/bin/sh
# ============================================================================
# BBZ — SIP trunk config sync (roadmap E13-09, ADR-0034).
#
# Fetches the BBZ-rendered PJSIP + dialplan fragments and drops them into the
# Asterisk config dir, then reloads. Run it from cron / a systemd timer on the
# Asterisk box, or once by hand. An operator who prefers not to give the box
# API access can instead copy the same text out of /admin/telefonie.
#
# The fetched config CONTAINS the trunk auth passwords in cleartext (PJSIP
# type=auth needs them) — it is written 0600 and never printed here.
#
# Required env:
#   BBZ_API    base URL, e.g. https://bbz.example:8443   (no trailing slash)
#   BBZ_USER   a least-privilege account with `integrations.configure`
#   BBZ_PASS   its password
# Optional env:
#   ASTERISK_ETC   default /etc/asterisk
#   CURL_OPTS      extra curl flags, e.g. "--cacert /etc/ssl/bbz-ca.pem"
#   NO_RELOAD      set to 1 to write the files but skip `asterisk -rx ... reload`
# ============================================================================
set -eu

: "${BBZ_API:?set BBZ_API (e.g. https://bbz.example:8443)}"
: "${BBZ_USER:?set BBZ_USER}"
: "${BBZ_PASS:?set BBZ_PASS}"

ETC="${ASTERISK_ETC:-/etc/asterisk}"
# shellcheck disable=SC2086
CURL="curl -fsS ${CURL_OPTS:-}"

jar="$(mktemp)"
cleanup() { rm -f "$jar" "$ETC"/pjsip_bbz_trunks.conf.tmp "$ETC"/extensions_bbz_trunks.conf.tmp; }
trap cleanup EXIT

# 1) log in -> the API sets the bbz_access / bbz_refresh / bbz_csrf cookies
$CURL -c "$jar" -H 'Content-Type: application/json' \
  --data "{\"username\":\"${BBZ_USER}\",\"password\":\"${BBZ_PASS}\"}" \
  "${BBZ_API}/api/v1/auth/login" >/dev/null

# 2) fetch each fragment (GET needs no CSRF token)
base="${BBZ_API}/api/v1/admin/telephony/sip/asterisk-config"
$CURL -b "$jar" "${base}?part=pjsip"      -o "${ETC}/pjsip_bbz_trunks.conf.tmp"
$CURL -b "$jar" "${base}?part=extensions" -o "${ETC}/extensions_bbz_trunks.conf.tmp"

# 3) move into place atomically, tight perms (the file holds trunk passwords)
install -m 600 "${ETC}/pjsip_bbz_trunks.conf.tmp"      "${ETC}/pjsip_bbz_trunks.conf"
install -m 600 "${ETC}/extensions_bbz_trunks.conf.tmp" "${ETC}/extensions_bbz_trunks.conf"

# 4) reload (best effort — a bad fragment shows up in the Asterisk log)
if [ "${NO_RELOAD:-0}" != "1" ]; then
  asterisk -rx 'pjsip reload'    >/dev/null 2>&1 || echo "bbz: 'pjsip reload' failed" >&2
  asterisk -rx 'dialplan reload' >/dev/null 2>&1 || echo "bbz: 'dialplan reload' failed" >&2
fi

echo "bbz: SIP trunk config synced -> ${ETC}/{pjsip,extensions}_bbz_trunks.conf"
