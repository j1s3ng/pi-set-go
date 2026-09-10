#!/usr/bin/env bash
# Bootstrap Raspberry Pi OS / Debian with network services.
set -Eeuo pipefail
trap 'printf "pi-set-go: failed at line %s (exit %s).\n" "$LINENO" "$?" >&2' ERR

usage() {
  cat <<'EOF'
Usage: sudo ./pi-set-go.sh [--yes] [--dry-run] [--radius-only | --dns-only]
                          [--dns-interface=NAME]

Update APT, fully upgrade installed packages, then install FreeRADIUS,
radsecproxy, and BIND9 with their command-line utilities.
Configure FreeRADIUS PEAP/MSCHAPv2 with dynamic VLAN reply support.

  -y, --yes    Accept APT prompts; preserve existing package config files.
  --dry-run    Print commands without changing the system (no sudo needed).
  --radius-only Configure installed FreeRADIUS without running APT.
  --dns-only   Configure installed BIND9 without APT or FreeRADIUS changes.
  --dns-interface=NAME Select an Ethernet interface instead of auto-detection.
  -h, --help   Show this help.
EOF
}

assume_yes=false
dry_run=false
radius_only=false
dns_only=false
dns_args=(--interface "")
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for arg in "$@"; do
  case "$arg" in
    -y|--yes) assume_yes=true ;;
    --dry-run) dry_run=true ;;
    --radius-only) radius_only=true ;;
    --dns-only) dns_only=true ;;
    --dns-interface=*) dns_args=(--interface "${arg#*=}") ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$arg" >&2; usage >&2; exit 2 ;;
  esac
done
if "$radius_only" && "$dns_only"; then
  printf 'Choose only one of --radius-only and --dns-only.\n' >&2
  exit 2
fi

if ! "$dry_run"; then
  if [[ "$(uname -s)" != Linux || ! -r /etc/os-release ]]; then
    printf 'Run this script on Raspberry Pi OS or Debian Linux.\n' >&2
    exit 1
  fi
  . /etc/os-release
  case "${ID:-}" in
    debian|raspbian) ;;
    *) printf 'Unsupported OS: %s. Expected Raspberry Pi OS or Debian.\n' "${ID:-unknown}" >&2; exit 1 ;;
  esac
  if (( EUID != 0 )); then
    printf 'Run with sudo, or use --dry-run to preview.\n' >&2
    exit 1
  fi
  command -v apt-get >/dev/null
fi

run() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  if ! "$dry_run"; then "$@"; fi
}

apt_options=(-o DPkg::Lock::Timeout=120)
if "$assume_yes"; then
  export DEBIAN_FRONTEND=noninteractive
  apt_options+=(-y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)
fi

if ! "$radius_only" && ! "$dns_only"; then
run apt-get "${apt_options[@]}" -o APT::Update::Error-Mode=any update
# dist-upgrade is apt-get's equivalent of apt full-upgrade.
run apt-get "${apt_options[@]}" dist-upgrade
run apt-get "${apt_options[@]}" install freeradius freeradius-utils radsecproxy bind9 bind9-utils dnsutils python3 iproute2
remote_args=(--dry-run)
if ! "$dry_run"; then remote_args=(); fi
if "$assume_yes"; then remote_args+=(--yes); fi
run bash "$script_dir/setup-remote.sh" ${remote_args[@]+"${remote_args[@]}"}
fi
if ! "$dns_only"; then
run python3 "$script_dir/scripts/configure-radius.py" "$script_dir/config/freeradius/users"
fi
if ! "$radius_only"; then
run python3 "$script_dir/scripts/configure-dns.py" "$script_dir/config/dns" "${dns_args[@]}"
fi

if "$dry_run"; then
  printf 'Preview complete; no changes made.\n'
else
  run dpkg-query -W '-f=${binary:Package}\t${Status}\t${Version}\n' freeradius radsecproxy bind9
  printf '\nSetup complete. Configure RADIUS clients, RadSec TLS/peers, and client DNS settings before use.\n'
  printf 'Package installers may start services with their packaged defaults.\n'
  if [[ -f /var/run/reboot-required ]]; then
    printf 'A reboot is required. Reboot when ready with: sudo reboot\n'
  else
    printf 'Consider rebooting after kernel or firmware updates.\n'
  fi
fi
