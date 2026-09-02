#!/usr/bin/env sh
# Deploy pre-flight for ONE BBZ application node (E24-03).
#
# Run in deploy/node/ before `docker compose up`. Verifies the environment is
# fully provisioned and isolated — every required BBZ_* var is set to a real
# value, every secret file exists and is not a placeholder, the etcd client
# certs are present. Exits non-zero with a list of everything missing; the
# app's own fail-closed check (verify_required_secrets, E23-01) is the second
# line of defence at startup.
#
#   cd /opt/bbz/deploy/node && sh preflight.sh
#
# rolling-update.sh runs this on each node before it swaps the image.
set -eu

DIR="${1:-$(dirname "$0")}"
cd "$DIR"

problems=""
add() { problems="${problems}\n  - $1"; }

# --- .env --------------------------------------------------------------------
if [ ! -f .env ]; then
  add ".env is missing (copy .env.example and fill it in)"
else
  # shellcheck disable=SC1091
  . ./.env

  for var in BBZ_NODE_ID BBZ_ENVIRONMENT BBZ_PUBLIC_NAME BBZ_API_IMAGE \
             BBZ_WEB_IMAGE BBZ_DATABASE_URL BBZ_CLUSTER_DCS_ENDPOINTS; do
    eval "val=\${$var:-}"
    [ -n "$val" ] || add "$var is not set in .env"
    case "$val" in *CHANGE_ME*) add "$var still contains CHANGE_ME" ;; esac
  done

  case "${BBZ_ENVIRONMENT:-}" in
    staging|production) : ;;
    "") : ;;  # already reported above
    *) add "BBZ_ENVIRONMENT='${BBZ_ENVIRONMENT}' — expected 'staging' or 'production' on a node" ;;
  esac

  # the app DB password rides in the DSN
  case "${BBZ_DATABASE_URL:-}" in
    *://*:*@*) : ;;
    *://*@*)   add "BBZ_DATABASE_URL has no password" ;;
  esac

  # production must not run a `latest` image (E23-12 will enforce a signed digest)
  if [ "${BBZ_ENVIRONMENT:-}" = "production" ]; then
    case "${BBZ_API_IMAGE:-}" in *:latest|*/latest) add "BBZ_API_IMAGE is ':latest' — pin a digest in production" ;; esac
    case "${BBZ_WEB_IMAGE:-}" in *:latest|*/latest) add "BBZ_WEB_IMAGE is ':latest' — pin a digest in production" ;; esac
  fi
fi

# --- secret files (docker/compose secrets, mounted at /run/secrets) ---------
for name in bbz_jwt_secret bbz_totp_encryption_key \
            postgres_superuser_password postgres_replication_password; do
  f="secrets/$name"
  if [ ! -f "$f" ]; then
    add "secret file $f is missing"
  elif [ ! -s "$f" ]; then
    add "secret file $f is empty"
  elif grep -q "CHANGE_ME" "$f"; then
    add "secret file $f is still the placeholder (CHANGE_ME)"
  elif [ -f "$f.example" ] && cmp -s "$f" "$f.example"; then
    add "secret file $f is identical to $f.example"
  fi
done

# bbz_jwt_secret must be long enough to be an HS256 key (>= 32 bytes)
if [ -f secrets/bbz_jwt_secret ] && [ "$(wc -c < secrets/bbz_jwt_secret)" -lt 32 ]; then
  add "secrets/bbz_jwt_secret is shorter than 32 bytes"
fi

# --- etcd client certs (ADR-0018) ------------------------------------------
for c in ca.crt client-bbz-app.crt client-bbz-app.key; do
  [ -f "etcd/certs/$c" ] || add "etcd/certs/$c is missing (run deploy/etcd/gen-certs.sh)"
done

# --- verdict ---------------------------------------------------------------
if [ -n "$problems" ]; then
  printf 'pre-flight FAILED for this node:%b\n' "$problems" >&2
  printf '\nSee docs/deploy/environments.md for the full matrix.\n' >&2
  exit 1
fi
echo "pre-flight OK — environment '${BBZ_ENVIRONMENT}', node '${BBZ_NODE_ID}'"
