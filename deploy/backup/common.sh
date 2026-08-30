# shellcheck shell=sh
# Shared backup helpers (roadmap E06-14). Backups contain BBZ domain data AND
# the audit trail, so they are always encrypted and access-restricted.
set -eu

# --- config (override via env / the systemd unit) -----------------------
BACKUP_DIR="${BACKUP_DIR:-/var/backups/bbz}"
GPG_RECIPIENT="${GPG_RECIPIENT:?set to the backup GPG key id/fingerprint}"
KEEP_FULL="${KEEP_FULL:-7}"            # keep this many newest full backups
KEEP_DAYS="${KEEP_DAYS:-14}"          # and prune anything older than this

# --- helpers ------------------------------------------------------------
ts()   { date -u +%Y%m%dT%H%M%SZ; }
log()  { printf '[%s] %s\n' "$(ts)" "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# encrypt stdin -> $1 (0600). Asymmetric: the private key stays offline.
gpg_encrypt() {
	umask 077
	gpg --batch --yes --trust-model always --encrypt --recipient "$GPG_RECIPIENT" \
		--output "$1" -
}

# decrypt $1 -> stdout
gpg_decrypt() { gpg --batch --yes --decrypt "$1"; }

# keep the KEEP_FULL newest files matching $1/*$2, drop the rest and anything
# older than KEEP_DAYS
prune() {
	dir=$1; glob=$2
	find "$dir" -maxdepth 1 -name "*$glob" -mtime "+$KEEP_DAYS" -print -delete || true
	# shellcheck disable=SC2012
	ls -1t "$dir"/*"$glob" 2>/dev/null | tail -n "+$((KEEP_FULL + 1))" | while read -r f; do
		log "prune $f"; rm -f "$f"
	done
}

require_dir() { mkdir -p "$1"; chmod 700 "$1"; }
