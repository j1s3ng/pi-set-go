#!/usr/bin/env bash
# Headless console boot with SSH, Tailscale, and an on-demand Openbox RDP desktop.
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

Install and enable SSH, Tailscale, and xrdp/xorgxrdp with a minimal Openbox desktop.
Tailscale uses its official stable APT repository for the detected OS release.
Account sign-in is a separate step: sudo tailscale up --accept-dns=false
Stop the local display manager and boot to multi-user.target.
Disable swap persistently for the next reboot; do not reboot automatically.
Existing SSH authentication settings are preserved.
Packages run unattended by default (-y/--yes), skipping patch notes and
automatically restarting services that need updated libraries.
--interactive restores normal package prompts and patch notes.
--skip-update reuses initial APT indexes refreshed by the parent setup script.
An additional refresh loads the Tailscale repository after it is configured.
EOF
      exit 0 ;;
    *) printf 'Unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done
run() {
  printf '+'; printf ' %q' "$@"; printf '\n'
  if ! "$dry_run"; then "$@"; fi
}
if [[ "$(uname -s)" == Linux && -r /etc/os-release ]]; then
  . /etc/os-release
  tailscale_distro="${ID:-}"
  tailscale_release="${VERSION_CODENAME:-}"
elif "$dry_run"; then
  tailscale_distro=debian
  tailscale_release=trixie
  printf 'Preview uses Debian Trixie; installation detects the Pi OS release.\n'
else
  echo 'Run on Raspberry Pi OS / Debian.' >&2; exit 1
fi
[[ "$tailscale_distro" == debian || "$tailscale_distro" == raspbian ]] || { echo 'Unsupported OS.' >&2; exit 1; }
[[ "$tailscale_release" =~ ^[a-z][a-z0-9-]*$ ]] || { echo 'Missing or invalid VERSION_CODENAME in /etc/os-release.' >&2; exit 1; }
if ! "$dry_run"; then
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
run "${apt_command[@]}" apt-get "${apt_options[@]}" install --no-install-recommends openssh-server xrdp xorgxrdp xserver-xorg-core openbox xterm dbus-x11 ssl-cert python3 iproute2 curl ca-certificates
run python3 "$script_dir/scripts/configure-remote.py"

# Download both repository files successfully before replacing installed copies.
tailscale_stage=/tmp/pi-set-go-tailscale.PREVIEW
if ! "$dry_run"; then
  tailscale_stage="$(mktemp -d /tmp/pi-set-go-tailscale.XXXXXXXX)"
  trap 'rm -rf -- "$tailscale_stage"' EXIT
fi
tailscale_repo="https://pkgs.tailscale.com/stable/$tailscale_distro/$tailscale_release"
run curl -fsSL --retry 3 --connect-timeout 10 --max-time 60 "$tailscale_repo.noarmor.gpg" -o "$tailscale_stage/keyring.gpg"
run curl -fsSL --retry 3 --connect-timeout 10 --max-time 60 "$tailscale_repo.tailscale-keyring.list" -o "$tailscale_stage/tailscale.list"
run test -s "$tailscale_stage/keyring.gpg"
run test -s "$tailscale_stage/tailscale.list"
run install -d -m 0755 /usr/share/keyrings /etc/apt/sources.list.d
run install -m 0644 "$tailscale_stage/keyring.gpg" /usr/share/keyrings/tailscale-archive-keyring.gpg
run install -m 0644 "$tailscale_stage/tailscale.list" /etc/apt/sources.list.d/tailscale.list
run "${apt_command[@]}" apt-get "${apt_options[@]}" -o APT::Update::Error-Mode=any update
run "${apt_command[@]}" apt-get "${apt_options[@]}" install --no-install-recommends tailscale
run systemctl enable --now tailscaled
run systemctl is-active --quiet tailscaled
printf '\nTailscale sign-in (keeps this DNS server\047s resolver settings): sudo tailscale up --accept-dns=false\n'
printf 'After signing in, verify with: tailscale status && tailscale ip -4\n'
