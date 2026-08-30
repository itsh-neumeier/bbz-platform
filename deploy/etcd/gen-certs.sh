#!/usr/bin/env sh
# Generate the etcd mTLS material for the BBZ cluster (ADR-0018).
#
#   ./gen-certs.sh              # uses the default member/SAN table below
#   OUT=./certs ./gen-certs.sh
#
# Run ONCE on a trusted host, then distribute:
#   certs/ca.crt                       -> every member + every client host
#   certs/<member>-peer.{crt,key}      -> that member only
#   certs/<member>-server.{crt,key}    -> that member only
#   certs/client-patroni.{crt,key}     -> both DB nodes (Patroni)
#   certs/client-bbz-app.{crt,key}     -> both app nodes (bbz-api)
#   certs/client-admin.{crt,key}       -> operator workstation (etcdctl)
#
# The private keys never leave their target host. certs/ is gitignored.
set -eu

# stop MSYS/Git-Bash from rewriting the openssl -subj "/O=.../CN=..." argument
# into a Windows path (no effect on Linux)
export MSYS2_ARG_CONV_EXCL="*"
export MSYS_NO_PATHCONV=1

OUT="${OUT:-$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)/certs}"
DAYS="${DAYS:-1825}"

# member  = etcd --name ;  hosts = comma-separated DNS/IP SANs for peer+server
MEMBERS="${MEMBERS:-BBZ-SRV01=bbz-srv01,10.0.0.11 BBZ-SRV02=bbz-srv02,10.0.0.12 BBZ-QUORUM01=bbz-quorum01,10.0.0.13}"
CLIENTS="${CLIENTS:-client-patroni client-bbz-app client-admin}"

mkdir -p "$OUT"
cd "$OUT"
umask 077

_san() {
  # $1 = comma-separated hosts -> openssl subjectAltName string (+ localhost)
  i_dns=1; i_ip=1; out="DNS.0:localhost,IP.0:127.0.0.1"
  OLD_IFS=$IFS; IFS=,
  for h in $1; do
    case "$h" in
      *[!0-9.]*) out="$out,DNS.$i_dns:$h"; i_dns=$((i_dns + 1)) ;;
      *)         out="$out,IP.$i_ip:$h";  i_ip=$((i_ip + 1)) ;;
    esac
  done
  IFS=$OLD_IFS
  echo "$out"
}

_leaf() {
  # $1 = base name, $2 = CN, $3 = SAN string ("" for a client), $4 = EKU
  name=$1; cn=$2; san=$3; eku=$4
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$name.key"
  openssl req -new -key "$name.key" -subj "/O=BBZ/CN=$cn" -out "$name.csr"
  ext="extendedKeyUsage=$eku
keyUsage=critical,digitalSignature,keyEncipherment
basicConstraints=critical,CA:FALSE"
  [ -n "$san" ] && ext="$ext
subjectAltName=$san"
  printf '%s\n' "$ext" > "$name.ext"
  openssl x509 -req -in "$name.csr" -CA ca.crt -CAkey ca.key -CAcreateserial \
    -days "$DAYS" -sha256 -extfile "$name.ext" -out "$name.crt"
  rm -f "$name.csr" "$name.ext"
}

# --- CA ---------------------------------------------------------------------
if [ ! -f ca.crt ]; then
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 -out ca.key
  openssl req -x509 -new -key ca.key -sha256 -days "$DAYS" \
    -subj "/O=BBZ/CN=BBZ etcd Root CA" \
    -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -out ca.crt
  echo "CA -> $OUT/ca.crt"
fi

# --- per-member peer + server certs ---------------------------------------
for entry in $MEMBERS; do
  m=${entry%%=*}; hosts=${entry#*=}
  san=$(_san "$hosts")
  _leaf "$m-peer"   "$m" "$san" "serverAuth,clientAuth"
  _leaf "$m-server" "$m" "$san" "serverAuth,clientAuth"
  echo "member $m -> $m-peer.crt / $m-server.crt"
done

# --- client certs (CN is the etcd username, see bootstrap-auth.sh) --------
for c in $CLIENTS; do
  _leaf "$c" "${c#client-}" "" "clientAuth"
  echo "client -> $c.crt (CN=${c#client-})"
done

echo "done. keep $OUT out of version control."
