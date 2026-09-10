#!/usr/bin/env bash
# Transfer tracked project files plus private config, optionally apply via sudo.
set -Eeuo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
target=''
directory=pi-set-go
apply=false
mode=''
dns_interface=''
for arg in "$@"; do
  case "$arg" in
    --apply) apply=true ;;
    --radius-only|--dns-only|--radsec-only)
      [[ -z "$mode" ]] || { echo 'Choose only one service-only option.' >&2; exit 2; }
      mode="$arg" ;;
    --directory=*) directory="${arg#*=}" ;;
    --dns-interface=*) dns_interface="${arg#*=}" ;;
    -h|--help)
      cat <<'EOF'
Usage: ./deploy-pi.sh USER@HOST [--directory=NAME] [--apply]
                      [--radius-only | --dns-only | --radsec-only]
                      [--dns-interface=NAME]

Copy tracked project files and the ignored config/ directory to ~/pi-set-go
on the Pi. Existing files with matching names are replaced; other files remain.
Private backup/log files are excluded. Nothing is committed or uploaded to Git.

  --apply          Run setup over SSH with an interactive sudo password prompt.
  --radsec-only    With --apply, deploy to an already installed radsecproxy.
  --radius-only    With --apply, configure installed FreeRADIUS only.
  --dns-only       With --apply, run manage-dns.sh using the copied zones.list.
  --dns-interface=NAME Select the Pi's Ethernet adapter for DNS generation.
  --directory=NAME Remote folder under the SSH user's home (default pi-set-go).

Examples:
  ./deploy-pi.sh pi@192.168.21.130
  ./deploy-pi.sh pi@192.168.21.130 --apply
  ./deploy-pi.sh pi@192.168.21.130 --apply --radsec-only
  ./deploy-pi.sh pi@192.168.21.130 --apply --dns-only

SSH uses your normal keys/config and host-key verification. The full --apply
installs packages and configures services; service-only modes skip installation.
The sudo password is entered directly into SSH and is not saved by this script.
EOF
      exit 0 ;;
    -*) printf 'Unknown option: %s\n' "$arg" >&2; exit 2 ;;
    *) [[ -z "$target" ]] || { echo 'Specify one USER@HOST.' >&2; exit 2; }; target="$arg" ;;
  esac
done
[[ "$target" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]*@[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || { echo 'Specify USER@HOST (IPv4 or hostname).' >&2; exit 2; }
[[ "$directory" =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]*$ ]] || { echo 'Directory must be a simple folder name.' >&2; exit 2; }
if [[ -n "$mode" ]] && ! "$apply"; then
  echo 'Service-only flags require --apply.' >&2; exit 2
fi
if [[ -n "$dns_interface" ]]; then
  [[ "$dns_interface" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.:-]*$ ]] || { echo 'Invalid Ethernet interface name.' >&2; exit 2; }
  [[ -z "$mode" || "$mode" == --dns-only ]] || { echo '--dns-interface applies to full or DNS-only setup.' >&2; exit 2; }
fi
[[ -d "$script_dir/config" ]] || { echo 'Missing local config/ directory.' >&2; exit 1; }
for command in python3 git ssh; do command -v "$command" >/dev/null; done
if "$apply" && [[ -z "$mode" || "$mode" == --dns-only ]]; then
  # Fail locally before SSH or package changes if the private DNS input is missing/invalid.
  python3 "$script_dir/scripts/configure-dns.py" "$script_dir/config/dns" --check-zones
fi
archive="$(mktemp "${TMPDIR:-/tmp}/pi-set-go-sync.XXXXXXXX")"
trap 'rm -f -- "$archive"' EXIT
# The private archive has mode 600 and is removed even if SSH fails.
python3 "$script_dir/scripts/package-deploy.py" "$script_dir" "$archive"
printf 'Copying project and private config to %s:~/%s\n' "$target" "$directory"
# directory is restricted to a simple basename before interpolation into remote code.
ssh "$target" "umask 077; mkdir -p \"\$HOME/$directory\" && chmod 700 \"\$HOME/$directory\" && tar --no-same-owner -xpf - -C \"\$HOME/$directory\"" < "$archive"
if "$apply"; then
  if [[ "$mode" == --dns-only ]]; then
    dns_option=''
    if [[ -n "$dns_interface" ]]; then dns_option="--interface=$dns_interface"; fi
    ssh -t "$target" "cd \"\$HOME/$directory\" && sudo bash ./manage-dns.sh $dns_option"
  else
    dns_option=''
    if [[ -n "$dns_interface" ]]; then dns_option="--dns-interface=$dns_interface"; fi
    ssh -t "$target" "cd \"\$HOME/$directory\" && sudo bash ./pi-set-go.sh $mode $dns_option"
  fi
else
  printf 'Files copied. Use --apply to run setup, or run sudo bash ~/%s/pi-set-go.sh on the Pi.\n' "$directory"
fi
