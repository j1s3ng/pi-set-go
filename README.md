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
    ├── zones.list
    └── zones/
        └── db.super.local
```

These are placeholders showing file locations, not working service configurations.
The setup script installs `config/freeradius/users` into
`/etc/freeradius/3.0/mods-config/files/authorize` when it contains active entries,
replacing that server file after backing it up. Comment-only files preserve the
existing server users. DNS is generated and deployed as described below;
radsecproxy files are not automatically deployed.

Package installers may start services automatically. The script validates and
restarts FreeRADIUS and BIND9 after configuration; it does not automatically reboot.

### DNS from the Ethernet address

For standalone DNS management, run this **on the Pi**:

```bash
# Edit config/dns/zones.list: one domain per line is all you need.
./manage-dns.sh --dry-run
sudo ./manage-dns.sh
# Optional explicit Ethernet adapter:
sudo ./manage-dns.sh --interface eth0
```

This reads the Pi's own live network state, generates the zone records and BIND
settings, validates them, and restarts BIND. It does not connect to a remote Pi
or install packages. Install BIND9, bind9-utils, iproute2, and Python 3 first
(the full setup script includes them). A dry run detects the real address and
prints the proposed files without writing anything. Add or remove domains in
the local zone list and rerun to update the served zones. Generated records and
options are replaced on each run; no manual zone-file edits are needed.

The normal setup also generates BIND9 DNS. To update DNS alone after an IP change:

```bash
sudo ./pi-set-go.sh --dns-only
# Select an interface when the Pi has multiple Ethernet connections:
sudo ./pi-set-go.sh --dns-only --dns-interface=enp1s0
```

Detection uses `ip -j -4 address show` (the structured form of `ip a`) and the
default routes. It chooses an active physical Ethernet adapter, including USB
Ethernet, excludes Wi-Fi and virtual adapters, and prefers the Ethernet default
route. Ambiguous addresses fail with an explanation instead of guessing.
The full install includes `iproute2` and Python 3 for this helper.

`config/dns/zones.list` lists one domain per line. Without it, only `super.local`
is generated. The tracked example contains only that domain; add private domains
to the ignored local list. Each zone gets SOA/NS records and A records for its
root name and `ns1`, pointing at the detected IPv4 address. Zone serials advance
on reruns. No wildcard or reverse zones are generated.

The helper preserves existing declarations in `/etc/bind/named.conf.local` and
adds an include for `/etc/bind/pi-set-go/zones.conf`. It replaces
`named.conf.options` with generated settings: listen on localhost and the
Ethernet IP, answer authoritative queries from any client that can reach it,
and allow recursion only from localhost and the detected Ethernet subnet.
Routed VLAN clients can query the local zones; additional recursion subnets
require editing the options. Settings regenerate on every DNS run.

It backs up affected configuration in `/var/backups/pi-set-go-dns-*`, checks
zones with `named-checkzone` and the whole configuration with `named-checkconf -z`,
then restarts `named`. Failed deployment restores the changed files; inspect
service status before restarting manually. Generated review copies are saved
under ignored `config/dns/`. Duplicate existing zone declarations will fail
validation and must be resolved before rerunning.

Point clients/DHCP DNS settings at the Pi and allow TCP/UDP port 53 through your
network. `.local` is reserved for [multicast DNS](https://www.rfc-editor.org/rfc/rfc6762.html);
clients may need explicit unicast DNS routing for these zones. Test BIND directly
with `dig @<PI_ETHERNET_IP> super.local A`. DNS is regenerated when the script
runs, not automatically on DHCP renewals; a DHCP reservation keeps the IP stable.

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

Both users files include commented MAB-only and MAB + RADIUS PPSK templates,
each with Airespace and standard tunnel VLAN variants. The PPSK templates use
[Cisco iPSK reply attributes](https://www.cisco.com/c/en/us/td/docs/wireless/controller/8-7/config-guide/b_cg87/m_wlan_security.html)
(`Cisco-AVPair` for `psk-mode` and `psk`); other vendors may require different
attributes. The MAB templates assume the NAS sends the device MAC as both
username and password, with matching formatting; see the
[FreeRADIUS MAC authentication guide](https://wiki.freeradius.org/guide/Mac-Auth).
They use the outer/default server, so its `files` and PAP/CHAP handling must be
enabled. These comments do not enable MAB or PPSK on the controller.

Each account/template has an optional commented `Session-Timeout := 3600,`
as its first reply attribute. To activate an example, remove one leading `# `
from every line of its entry; the timeout remains commented until you enable
it separately. Replace placeholder credentials and MAC addresses first.

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
