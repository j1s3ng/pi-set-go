#!/usr/bin/env bash
# Run on the Pi: zones.list + Ethernet IPv4 -> complete BIND DNS configuration.
set -Eeuo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
  cat <<'EOF'
Usage: sudo ./manage-dns.sh [--interface NAME]
       ./manage-dns.sh --dry-run [--interface NAME]

Read config/dns/zones.list, detect the Pi's Ethernet IPv4 address/subnet with ip,
and generate forward/reverse zones, a trusted recursion ACL, and BIND settings.
Use the reference's public forwarders (8.8.8.8 and 8.8.4.4). Back up, validate, and
restart BIND. No package upgrades or FreeRADIUS changes.
The ignored zones.list must exist. Every forward zone includes commented ise01-03 records.
The Pi's reverse PTR uses ns1 under the first domain in zones.list.

  --interface NAME  Choose an Ethernet interface (otherwise auto-detected).
  --dry-run         Detect the address and preview generated files; no writes.
  --check-zones     Validate the local zone list only (also works on your Mac).
  -h, --help        Show this help.

Run this on the Pi with BIND9, bind9-utils, iproute2, and Python 3 installed.
Edit zones.list to add/remove domains, then rerun. No manual zone files needed.
Generated zone records and BIND options are replaced on every run.
EOF
  exit 0
fi

exec python3 "$script_dir/scripts/configure-dns.py" "$script_dir/config/dns" "$@"
