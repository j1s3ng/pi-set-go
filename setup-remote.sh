#!/usr/bin/env bash
# Headless console boot with SSH and an on-demand Openbox RDP desktop.
set -Eeuo pipefail
export PATH="/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
dry_run=false
assume_yes=true
skip_update=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run=true ;;
    --skip-update) skip_update=true ;;
    -y|--yes) assume_yes=true ;;
    --interactive) assume_yes=false ;;
    -h|--help)
      cat <<'EOF'
Usage: sudo ./setup-remote.sh [--yes | --interactive] [--dry-run] [--skip-update]

Install and enable SSH plus xrdp/xorgxrdp with a minimal Openbox desktop.
Stop the local display manager and boot to multi-user.target.
Disable swap persistently for the next reboot; do not reboot automatically.
Existing SSH authentication settings are preserved.
Packages run unattended by default (-y/--yes), skipping patch notes and
automatically restarting services that need updated libraries.
--interactive restores normal package prompts and patch notes.
--skip-update reuses APT indexes refreshed by the parent setup script.
EOF
      exit 0 ;;
    *) printf 'Unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done
run() {
  printf '+'; printf ' %q' "$@"; printf '\n'
  if ! "$dry_run"; then "$@"; fi
}
if ! "$dry_run"; then
  [[ "$(uname -s)" == Linux && -r /etc/os-release ]] || { echo 'Run on Raspberry Pi OS / Debian.' >&2; exit 1; }
  . /etc/os-release
  [[ "${ID:-}" == debian || "${ID:-}" == raspbian ]] || { echo 'Unsupported OS.' >&2; exit 1; }
  (( EUID == 0 )) || { echo 'Run with sudo.' >&2; exit 1; }
fi
apt_options=(-o DPkg::Lock::Timeout=120)
apt_command=(env)
if "$assume_yes"; then
  apt_command+=(DEBIAN_FRONTEND=noninteractive APT_LISTCHANGES_FRONTEND=none NEEDRESTART_MODE=a)
  apt_options+=(-y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)
fi
if ! "$skip_update"; then
run "${apt_command[@]}" apt-get "${apt_options[@]}" -o APT::Update::Error-Mode=any update
fi
run "${apt_command[@]}" apt-get "${apt_options[@]}" install --no-install-recommends openssh-server xrdp xorgxrdp xserver-xorg-core openbox xterm dbus-x11 ssl-cert python3 iproute2
run python3 "$script_dir/scripts/configure-remote.py"
