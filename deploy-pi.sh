#!/usr/bin/env bash
# Transfer tracked project files plus private config, optionally apply via sudo.
set -Eeuo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
target=''
directory=pi-set-go
apply=false
mode=''
for arg in "$@"; do
  case "$arg" in
    --apply) apply=true ;;
    --radius-only|--dns-only|--radsec-only)
      [[ -z "$mode" ]] || { echo 'Choose only one service-only option.' >&2; exit 2; }
      mode="$arg" ;;
    --directory=*) directory="${arg#*=}" ;;
    -h|--help)
      cat <<'EOF'
Usage: ./deploy-pi.sh USER@HOST [--directory=NAME] [--apply]
                      [--radius-only | --dns-only | --radsec-only]

Copy tracked project files and the ignored config/ directory to ~/pi-set-go
on the Pi. Existing files with matching names are replaced; other files remain.
Private backup/log files are excluded. Nothing is committed or uploaded to Git.

  --apply          Run setup over SSH with an interactive sudo password prompt.
  --radsec-only    With --apply, deploy to an already installed radsecproxy.
  --radius-only    With --apply, configure installed FreeRADIUS only.
  --dns-only       With --apply, regenerate/configure installed BIND only.
  --directory=NAME Remote folder under the SSH user's home (default pi-set-go).

Examples:
  ./deploy-pi.sh pi@192.168.21.130
  ./deploy-pi.sh pi@192.168.21.130 --apply
  ./deploy-pi.sh pi@192.168.21.130 --apply --radsec-only

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
[[ -d "$script_dir/config" ]] || { echo 'Missing local config/ directory.' >&2; exit 1; }
for command in python3 git ssh; do command -v "$command" >/dev/null; done
archive="$(mktemp "${TMPDIR:-/tmp}/pi-set-go-sync.XXXXXXXX")"
trap 'rm -f -- "$archive"' EXIT
# The private archive has mode 600 and is removed even if SSH fails.
python3 "$script_dir/scripts/package-deploy.py" "$script_dir" "$archive"
printf 'Copying project and private config to %s:~/%s\n' "$target" "$directory"
# directory is restricted to a simple basename before interpolation into remote code.
ssh "$target" "umask 077; mkdir -p \"\$HOME/$directory\" && chmod 700 \"\$HOME/$directory\" && tar --no-same-owner -xpf - -C \"\$HOME/$directory\"" < "$archive"
if "$apply"; then
  ssh -t "$target" "cd \"\$HOME/$directory\" && sudo bash ./pi-set-go.sh $mode"
else
  printf 'Files copied. Use --apply to run setup, or run sudo bash ~/%s/pi-set-go.sh on the Pi.\n' "$directory"
fi
