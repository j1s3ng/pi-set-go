#!/usr/bin/env bash
# Bootstrap Raspberry Pi OS / Debian with network services.
set -Eeuo pipefail
trap 'printf "pi-set-go: failed at line %s (exit %s).\n" "$LINENO" "$?" >&2' ERR

usage() {
  cat <<'EOF'
Usage: sudo ./pi-set-go.sh [--yes | --interactive] [--dry-run] [--radius-only | --dns-only | --radsec-only]
                          [--dns-interface=NAME]

Update APT, fully upgrade installed packages, then install FreeRADIUS,
radsecproxy, and BIND9 with their command-line utilities.
Configure FreeRADIUS PEAP/MSCHAPv2 with dynamic VLAN reply support.
Install SSH, xrdp, and Tailscale remote access (Tailscale sign-in is separate).

  -y, --yes    Unattended packages: accept prompts and skip patch notes (default).
  --interactive Show normal package prompts and patch notes.
  --dry-run    Print commands without changing the system (no sudo needed).
  --radius-only Configure installed FreeRADIUS without running APT.
  --dns-only   Configure installed BIND9 without APT or FreeRADIUS changes.
  --radsec-only Deploy config/radsecproxy.conf to installed radsecproxy only.
  --dns-interface=NAME Select an Ethernet interface instead of auto-detection.
  -h, --help   Show this help.
EOF
}

assume_yes=true
dry_run=false
radius_only=false
dns_only=false
radsec_only=false
dns_args=(--interface "")
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for arg in "$@"; do
  case "$arg" in
    -y|--yes) assume_yes=true ;;
    --interactive) assume_yes=false ;;
    --dry-run) dry_run=true ;;
    --radius-only) radius_only=true ;;
    --dns-only) dns_only=true ;;
    --radsec-only) radsec_only=true ;;
    --dns-interface=*) dns_args=(--interface "${arg#*=}") ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$arg" >&2; usage >&2; exit 2 ;;
  esac
done
mode_count=0
for mode in "$radius_only" "$dns_only" "$radsec_only"; do
  if "$mode"; then mode_count=$((mode_count + 1)); fi
done
if (( mode_count > 1 )); then
  printf 'Choose only one service-only option.\n' >&2
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

# Package post-install scripts may otherwise start radsecproxy on FreeRADIUS's port.
proxy_mask_added=false
release_proxy_mask() {
  if "$proxy_mask_added"; then
    # Keep the service disabled even if APT exits before normal configuration.
    run systemctl disable --now radsecproxy || true
    run systemctl unmask --runtime radsecproxy
    proxy_mask_added=false
  fi
}
trap 'setup_status=$?; release_proxy_mask; exit "$setup_status"' EXIT

apt_options=(-o DPkg::Lock::Timeout=120)
apt_command=(env)
if "$assume_yes"; then
  # Scope these settings to APT; certificate generation remains interactive.
  apt_command+=(DEBIAN_FRONTEND=noninteractive APT_LISTCHANGES_FRONTEND=none NEEDRESTART_MODE=a)
  apt_options+=(-y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)
fi

if (( mode_count == 0 )); then
if [[ ! -e /run/systemd/system/radsecproxy.service && ! -L /run/systemd/system/radsecproxy.service ]]; then
  proxy_mask_added=true
fi
run systemctl mask --runtime --now radsecproxy
run "${apt_command[@]}" apt-get "${apt_options[@]}" -o APT::Update::Error-Mode=any update
# dist-upgrade is apt-get's equivalent of apt full-upgrade.
run "${apt_command[@]}" apt-get "${apt_options[@]}" dist-upgrade
run "${apt_command[@]}" apt-get "${apt_options[@]}" install freeradius freeradius-utils radsecproxy bind9 bind9-utils dnsutils python3 iproute2 openssl
if "$proxy_mask_added"; then
  release_proxy_mask
else
  run systemctl disable --now radsecproxy
fi
remote_args=(--skip-update)
if "$dry_run"; then remote_args+=(--dry-run); fi
if "$assume_yes"; then remote_args+=(--yes); else remote_args+=(--interactive); fi
run bash "$script_dir/setup-remote.sh" "${remote_args[@]}"
fi
if ! "$dns_only"; then
run bash "$script_dir/certs.sh" --install
fi
if ! "$dns_only" && ! "$radsec_only"; then
run python3 "$script_dir/scripts/configure-radius.py" "$script_dir/config/freeradius/users"
fi
if ! "$radius_only" && ! "$radsec_only"; then
run bash "$script_dir/manage-dns.sh" "${dns_args[@]}"
fi
if ! "$radius_only" && ! "$dns_only"; then
run python3 "$script_dir/scripts/configure-radsecproxy.py" "$script_dir/config/radsecproxy.conf"
fi

if "$dry_run"; then
  printf 'Preview complete; no changes made.\n'
else
  packages=(freeradius radsecproxy bind9 tailscale)
  if "$radsec_only"; then packages=(radsecproxy); fi
  if "$radius_only"; then packages=(freeradius); fi
  if "$dns_only"; then packages=(bind9); fi
  run dpkg-query -W '-f=${binary:Package}\t${Status}\t${Version}\n' "${packages[@]}"
  printf '\nSetup complete. Configure RADIUS clients, RadSec TLS/peers, and client DNS settings before use.\n'
  printf 'Package installers may start services with their packaged defaults.\n'
  if [[ -f /var/run/reboot-required ]]; then
    printf 'A reboot is required. Reboot when ready with: sudo reboot\n'
  else
    printf 'Consider rebooting after kernel or firmware updates.\n'
  fi
fi
