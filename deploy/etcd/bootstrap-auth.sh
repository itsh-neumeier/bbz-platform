#!/usr/bin/env sh
# Enable etcd authentication and create prefix-scoped roles (ADR-0018).
# Run ONCE against a healthy cluster, from a host that has certs/ca.crt and
# certs/client-admin.{crt,key}.
#
#   ENDPOINTS=https://bbz-srv01:2379,https://bbz-srv02:2379 ./bootstrap-auth.sh
#
# Users are authenticated by client-certificate CN (--client-cert-auth on the
# members), so no passwords are set for the service users — only `root` gets a
# password as the auth-enable escape hatch.
set -eu

CERTS="${CERTS:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/certs}"
ENDPOINTS="${ENDPOINTS:-https://127.0.0.1:2379}"

etcd_() {
  etcdctl --endpoints="$ENDPOINTS" \
    --cacert="$CERTS/ca.crt" \
    --cert="$CERTS/client-admin.crt" \
    --key="$CERTS/client-admin.key" "$@"
}

# root is required before `auth enable`
if ! etcd_ user get root >/dev/null 2>&1; then
  echo "creating root user — set a strong password when prompted:"
  etcd_ user add root
fi
etcd_ user grant-role root root 2>/dev/null || true

# --- Patroni: read/write ONLY under /patroni/ ------------------------------
etcd_ role add patroni 2>/dev/null || true
etcd_ role grant-permission patroni readwrite --prefix=true /patroni/
etcd_ user add patroni --no-password 2>/dev/null || true
etcd_ user grant-role patroni patroni

# --- BBZ app: read/write ONLY under /bbz/ ---------------------------------
etcd_ role add bbz 2>/dev/null || true
etcd_ role grant-permission bbz readwrite --prefix=true /bbz/
etcd_ user add bbz-app --no-password 2>/dev/null || true
etcd_ user grant-role bbz-app bbz

# --- operator: read-only everywhere -------------------------------------
etcd_ role add observer 2>/dev/null || true
etcd_ role grant-permission observer read --prefix=true '' 2>/dev/null || true
etcd_ user add admin --no-password 2>/dev/null || true
etcd_ user grant-role admin observer

etcd_ auth enable
echo "auth enabled. patroni -> /patroni/, bbz-app -> /bbz/, admin -> read-only."
etcd_ role list
