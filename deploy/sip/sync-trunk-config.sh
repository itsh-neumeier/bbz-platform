#!/bin/sh
# ============================================================================
# BBZ — SIP trunk + WebRTC + MoH config sync (E13-09 / E13-11 / E13-12,
# ADR-0034 / 0035).
#
# Fetches the BBZ-rendered PJSIP + dialplan + musiconhold fragments (and the
# music-on-hold WAVs) and drops them onto the Asterisk box, then reloads. Run it
# from cron / a systemd timer, or once by hand. An operator who prefers not to
# give the box API access can copy the text fragments out of /admin/telefonie
# (the WAVs then need a manual scp).
#
# The PJSIP fragment carries the trunk AND the per-operator WebRTC endpoint
# passwords in cleartext (PJSIP type=auth needs them) — it is written 0600 and
# never printed here. If any WebRTC operator endpoint is configured the fragment
# also emits `[transport-wss]`; that needs a TLS cert on the box at the paths in
# BBZ_SIP_WEBRTC_CERT_FILE / _PRIV_KEY_FILE (lab: self-signed in the image).
#
# Required env:
#   BBZ_API    base URL, e.g. https://bbz.example:8443   (no trailing slash)
#   BBZ_USER   a least-privilege account with `integrations.configure`
#   BBZ_PASS   its password
# Optional env:
#   ASTERISK_ETC   default /etc/asterisk
#   MOH_DIR        where the MoH WAV tree lands; default /var/lib/asterisk/moh/bbz
#                  (must match BBZ_MOH_ASTERISK_DIR on the api node)
#   CURL_OPTS      extra curl flags, e.g. "--cacert /etc/ssl/bbz-ca.pem"
#   NO_RELOAD      set to 1 to write the files but skip `asterisk -rx ... reload`
# ============================================================================
set -eu

: "${BBZ_API:?set BBZ_API (e.g. https://bbz.example:8443)}"
: "${BBZ_USER:?set BBZ_USER}"
: "${BBZ_PASS:?set BBZ_PASS}"

ETC="${ASTERISK_ETC:-/etc/asterisk}"
MOH_DIR="${MOH_DIR:-/var/lib/asterisk/moh/bbz}"
# shellcheck disable=SC2086
CURL="curl -fsS ${CURL_OPTS:-}"

jar="$(mktemp)"
cleanup() {
  rm -f "$jar" "$ETC"/pjsip_bbz_trunks.conf.tmp "$ETC"/extensions_bbz_trunks.conf.tmp \
    "$ETC"/musiconhold_bbz.conf.tmp
}
trap cleanup EXIT

# 1) log in -> the API sets the bbz_access / bbz_refresh / bbz_csrf cookies
$CURL -c "$jar" -H 'Content-Type: application/json' \
  --data "{\"username\":\"${BBZ_USER}\",\"password\":\"${BBZ_PASS}\"}" \
  "${BBZ_API}/api/v1/auth/login" >/dev/null

# 2) fetch each config fragment (GET needs no CSRF token)
base="${BBZ_API}/api/v1/admin/telephony/sip/asterisk-config"
$CURL -b "$jar" "${base}?part=pjsip"       -o "${ETC}/pjsip_bbz_trunks.conf.tmp"
$CURL -b "$jar" "${base}?part=extensions"  -o "${ETC}/extensions_bbz_trunks.conf.tmp"
$CURL -b "$jar" "${base}?part=musiconhold" -o "${ETC}/musiconhold_bbz.conf.tmp"

# 3) move into place atomically, tight perms on the ones holding passwords
install -m 600 "${ETC}/pjsip_bbz_trunks.conf.tmp"      "${ETC}/pjsip_bbz_trunks.conf"
install -m 600 "${ETC}/extensions_bbz_trunks.conf.tmp" "${ETC}/extensions_bbz_trunks.conf"
install -m 644 "${ETC}/musiconhold_bbz.conf.tmp"       "${ETC}/musiconhold_bbz.conf"

# 4) pull the MoH WAVs — one dir per file id, `<id>/moh.wav` (no jq on the box:
#    the manifest is `<uuid> <sha256>` lines)
moh="${BBZ_API}/api/v1/admin/telephony/moh"
$CURL -b "$jar" "${moh}/manifest" | while read -r id _sha; do
  [ -n "$id" ] || continue
  mkdir -p "${MOH_DIR}/${id}"
  $CURL -b "$jar" "${moh}/${id}/download" -o "${MOH_DIR}/${id}/moh.wav.tmp"
  mv "${MOH_DIR}/${id}/moh.wav.tmp" "${MOH_DIR}/${id}/moh.wav"
done

# 5) reload (best effort — a bad fragment shows up in the Asterisk log)
if [ "${NO_RELOAD:-0}" != "1" ]; then
  asterisk -rx 'pjsip reload'       >/dev/null 2>&1 || echo "bbz: 'pjsip reload' failed" >&2
  asterisk -rx 'dialplan reload'    >/dev/null 2>&1 || echo "bbz: 'dialplan reload' failed" >&2
  asterisk -rx 'moh reload'         >/dev/null 2>&1 || echo "bbz: 'moh reload' failed" >&2
fi

echo "bbz: SIP config synced -> ${ETC}/{pjsip,extensions}_bbz_trunks.conf, musiconhold_bbz.conf; MoH -> ${MOH_DIR}"
