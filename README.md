# pi-set-go

Ready, set, network. A Raspberry Pi OS / Debian bootstrap script for FreeRADIUS, radsecproxy, and BIND9.

## Run on your Pi

```bash
chmod +x pi-set-go.sh
./pi-set-go.sh --dry-run
sudo ./pi-set-go.sh
```

For unattended installation, use `sudo ./pi-set-go.sh --yes`. This accepts APT prompts and preserves locally modified package configuration files using the package manager's default action where available.

The script refreshes package lists, runs `apt-get dist-upgrade`, and installs `freeradius`, `freeradius-utils`, `radsecproxy`, `bind9`, `bind9-utils`, and `dnsutils`. It stops on errors and can be rerun. Full upgrades may remove packages to resolve dependencies; review APT's proposal when running interactively.

Raspberry Pi [recommends full-upgrade](https://www.raspberrypi.com/documentation/computers/os.html#update-software) for package updates. `apt-get dist-upgrade` performs that operation without changing your configured OS release or repositories.

## Configure services

This prepares the packages. Package installers may start services automatically; the script does not replace service configurations or automatically reboot.

Before using the services, configure:

- FreeRADIUS: clients, shared secrets, and authentication under `/etc/freeradius/`.
- radsecproxy: peers, routing, and TLS certificates in `/etc/radsecproxy.conf`. It may not start until a valid configuration is supplied. See the [Debian radsecproxy manual](https://manpages.debian.org/trixie/radsecproxy/index.html).
- BIND9: zones, listening interfaces, and recursion access in `/etc/bind/`. Check for an existing DNS service using port 53.

Check service status on the Pi with `systemctl status freeradius radsecproxy named`. Actual installation and service behavior must be verified on the target Pi.
