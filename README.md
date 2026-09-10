# pi-set-go

Ready, set, network. A Raspberry Pi OS / Debian bootstrap script for FreeRADIUS, radsecproxy, and BIND9.

## Run on your Pi

```bash
chmod +x pi-set-go.sh
./pi-set-go.sh --dry-run
sudo ./pi-set-go.sh
```

For unattended installation, use `sudo ./pi-set-go.sh --yes`. This accepts APT prompts and preserves locally modified package configuration files using the package manager's default action where available.

The script refreshes package lists, runs `apt-get dist-upgrade`, and installs `freeradius`, `freeradius-utils`, `radsecproxy`, `bind9`, `bind9-utils`, `dnsutils`, and `python3`. It then configures FreeRADIUS 3 for PEAP/MSCHAPv2 and dynamic VLAN replies. It stops on errors and can be rerun. Full upgrades may remove packages to resolve dependencies; review APT's proposal when running interactively.

Raspberry Pi [recommends full-upgrade](https://www.raspberrypi.com/documentation/computers/os.html#update-software) for package updates. `apt-get dist-upgrade` performs that operation without changing your configured OS release or repositories.

## Configure services

Keep your real service files in `config/`. The entire directory and all its
contents are ignored by Git. A tracked, placeholder-only layout lives in
`examples/config/`; never add real credentials or private network data there.

Create your local copy after cloning:

```bash
cp -Rn examples/config/. config/
```

The `-n` option preserves any files you already have. The layout is:

```text
config/                       # Everything here is ignored
├── freeradius/
│   └── users
├── radsecproxy.conf
└── dns/
    ├── named.conf.local
    ├── named.conf.options
    └── zones/
        └── db.example.test
```

These are placeholders showing file locations, not working service configurations.
The setup script installs `config/freeradius/users` into
`/etc/freeradius/3.0/mods-config/files/authorize` when it contains active entries,
replacing that server file after backing it up. Comment-only files preserve the
existing server users. DNS and radsecproxy files are not automatically deployed.

Package installers may start services automatically. The script validates and
restarts FreeRADIUS after configuration; it does not automatically reboot.

### PEAP and dynamic VLANs

The script sets the outer EAP default to PEAP, the PEAP inner method to MSCHAPv2,
and `use_tunneled_reply = yes` so authenticated user reply attributes reach the
access point. It enables the packaged `eap`, `mschap`, `files`, and `inner-tunnel`
configurations. This follows the [FreeRADIUS 3 PEAP configuration](https://github.com/FreeRADIUS/freeradius-server/blob/v3.2.x/raddb/mods-available/eap).
Existing TLS certificate settings are preserved; configure a trusted server
certificate and require clients to validate its CA and server name before use.

Local accounts `avlan1` through `avlan6` use `Airespace-Interface-Name` with values
`1` through `6`. Those values must match controller interface **names** mapped to
the corresponding VLANs, per [Cisco's dynamic VLAN guide](https://www.cisco.com/c/en/us/support/docs/wireless-mobility/wireless-vlan/71683-dynamicvlan-config.html).
Accounts `tvlan1` through `tvlan6` use `Tunnel-Type = VLAN`,
`Tunnel-Medium-Type = IEEE-802`, and `Tunnel-Private-Group-Id` values `1` through
`6`. Real accounts/passwords exist only in your ignored local `users` file;
clones receive commented examples. Configure AAA override/dynamic VLAN support
on the AP/controller and provision the VLANs and trunks there as well.

After editing local user assignments, apply them without another package upgrade:

```bash
sudo ./pi-set-go.sh --radius-only
```

This targets the Debian FreeRADIUS 3 package layout and its standard `files`
module. Customized virtual servers or user-file paths require review. Each run
backs up `/etc/freeradius/3.0` into a private `/var/backups/pi-set-go-radius-*`
directory and runs `freeradius -XC` before restarting. Validation logs stay in
that private backup because they may include credentials. On failure, modified
files are restored; inspect the log and service status before restarting manually.

Before using the services, configure:

- FreeRADIUS: clients, shared secrets, and authentication under `/etc/freeradius/`.
- radsecproxy: peers, routing, and TLS certificates in `/etc/radsecproxy.conf`. It may not start until a valid configuration is supplied. See the [Debian radsecproxy manual](https://manpages.debian.org/trixie/radsecproxy/index.html).
- BIND9: zones, listening interfaces, and recursion access in `/etc/bind/`. Check for an existing DNS service using port 53.

Check service status on the Pi with `systemctl status freeradius radsecproxy named`. Actual installation and service behavior must be verified on the target Pi.
