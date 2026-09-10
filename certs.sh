#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == --install ]]; then
    (( EUID == 0 )) || { echo 'Run --install with sudo.' >&2; exit 1; }
    if [[ -f /etc/certs.sh ]] && cmp -s "$script_dir/certs.sh" /etc/certs.sh; then
        chmod 750 /etc/certs.sh
        echo '/etc/certs.sh is already up to date.'
        exit 0
    fi
    if [[ -e /etc/certs.sh || -L /etc/certs.sh ]]; then
        backup="$(mktemp -d /var/backups/pi-set-go-certs.XXXXXXXX)"
        cp -Pp /etc/certs.sh "$backup/certs.sh"
        echo "Previous certificate script backed up to $backup"
    fi
    install -m 750 "$script_dir/certs.sh" /etc/certs.sh
    echo 'Installed /etc/certs.sh. Certificate generation remains a separate interactive step.'
    exit 0
fi
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    cat <<'EOF'
Usage: sudo ./certs.sh --install
       sudo /etc/certs.sh [OUTPUT_DIRECTORY]

Create test CA/server certificates interactively, preserving existing files.
Installed default output: /etc/pi-set-go/certs
Repository default output: config/certs (ignored by Git)
Set ENCRYPTED=1 to encrypt the server private key as well as the CA key.
EOF
    exit 0
fi
(( $# <= 1 )) || { echo 'Specify one output directory.' >&2; exit 2; }
[[ "${1:-}" != -* ]] || { echo 'Unknown option; use --help.' >&2; exit 2; }
output="${1:-$script_dir/config/certs}"
if [[ "$script_dir" == /etc && $# == 0 ]]; then output=/etc/pi-set-go/certs; fi
mkdir -p "$output"
cd -- "$output"
ENCRYPTED=${ENCRYPTED:-0}
# create a CA key & cert and a server key and cert for testing.

# CA key
echo -e "\n\n\n============= Creating CA key ==========================\n"
[ -s cakey.pem ] || openssl genrsa -out cakey.pem -aes256 4096
# CA self-signed cert
echo -e "\n\n\n============= Creating CA self-signed cert ==========================\n"
[ -s cacert.pem ] || openssl req -new -x509 -key cakey.pem -out cacert.pem -days 3650 -sha256

# server key
echo -e "\n\n\n============= Creating server key ==========================\n"
if [ "$ENCRYPTED" = "1" ]; then
    [ -s key.pem ] || openssl genrsa -out key.pem -aes256  2048
else
    [ -s key.pem ] || openssl genrsa -out key.pem 2048
fi
echo -e "\n\n\n============= Creating server cert signing request ==========================\n"
# server cert signing request
[ -s cert.csr ] || openssl req -new -key key.pem -out cert.csr -sha256
# display the cert req
echo -e "\n\n\n============= Cert signing request contents ===============================\n"
openssl req -text -noout -verify -in cert.csr

# build enough disk structure that "openssl ca" can operate
mkdir -p demoCA/newcerts
touch demoCA/index.txt
[ -s demoCA/serial ] || echo 01 >demoCA/serial

# sign the request with the CA key
echo -e "\n\n\n============= Signing server signing request with CA key ==========================\n"
[ -s cert.pem ] || openssl ca -in cert.csr -out cert.pem -cert cacert.pem -keyfile cakey.pem -verbose -days 730 -md sha256

echo -e "\n\n\n============= OK. Displaying results ==========================\n"

echo -e "\n\n==== CA cert ====\n"
openssl x509 -in cacert.pem -text -noout

echo -e "\n\n==== server cert ====\n"
openssl x509 -in cert.pem -text -noout

# create a binary cert for mobile usage
echo -e "\n\n\n============= Convert pem (ASCII) to der (binary) format for ios =============\n"
[ -s cacert.der ] || openssl x509 -in cacert.pem -inform PEM -out cacert.der -outform DER

echo -e "\n\n\n============= Done ==========================\n"
echo "Place the key.pem and cert.pem on the server, and cacert.pem in the client's trusted CA store"
