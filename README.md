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

### Headless boot, swap, and remote access

The full setup also runs `setup-remote.sh`. It can be run independently:

```bash
./setup-remote.sh --dry-run
sudo ./setup-remote.sh --yes
```

This installs and enables OpenSSH and [xrdp with xorgxrdp](https://github.com/neutrinolabs/xrdp),
using a minimal Openbox desktop for remote sessions. FreeRDP is an RDP client
option; xrdp provides the graphical login server needed here. Openbox keeps
the session small for low-memory Pi boards. Right-click the remote desktop to
open the applications menu and terminal. The RDP service starts at boot; the
desktop session starts when you log in.

SSH configuration is checked and its service is enabled before the local
display manager is stopped. The default boot target becomes `multi-user.target`,
so the local desktop stays off. SSH authentication policy is preserved. Connect
your RDP client to the Pi on TCP 3389 and log in with an existing local account's
password. Existing xrdp user-session overrides can supersede the configured
Openbox startup script. SSH/SFTP and RDP are the configured remote access paths;
other remote-access products are not enabled automatically.

Swap is disabled persistently: fstab swap entries are commented out, legacy
swap services are disabled, known swap units are masked, and zram settings are
overridden. On Raspberry Pi OS Trixie, a drop-in sets `Mechanism=none` for
[rpi-swap](https://github.com/raspberrypi/rpi-swap). **Reboot is required to finish
disabling active swap.** The script leaves live swap in place until that reboot
and does not reboot automatically. Backups of modified configuration and the
previous default boot target are stored in `/var/backups/pi-set-go-remote-*`.

After reboot, verify:

```bash
cat /proc/swaps  # Only the header should remain
systemctl get-default  # multi-user.target
systemctl is-enabled ssh xrdp
systemctl is-active ssh xrdp xrdp-sesman
```

The script checks service state and displays TCP listeners. Firewall rules are
preserved; confirm SSH and an actual RDP login from your client. It does not
claim end-to-end access from service status alone. Stopping the display manager
ends any local graphical session.

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

Each zone also includes commented FQDN placeholders for `ise01`, `ise02`, and
`ise03` (for example, `ise01.super.local.`), with example IPs `192.0.2.11`–`13`.
They do not resolve until assigned real IPs and enabled. Manual changes to
generated zone files are overwritten on regeneration.

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

### Append MAB prefixes and radsecproxy subnets

Keep the original installed comments and configuration. These helpers append
marked blocks at EOF and create a mode-600 backup beside the target file.
They default to the ignored local files and do not restart services. Use
`--file` to target an installed file directly. The attached/reference users
file is not imported automatically.

```bash
# Add 256 MAC users ending in 00-ff, each assigned VLAN 3:
./add-mab.sh '02:00:00:00:01:*' --vlan 3 --dry-run
./add-mab.sh '02:00:00:00:01:*' --vlan 3
# Controller interface names, MAC formatting, and timeout are optional choices:
./add-mab.sh '02:00:00:00:02:*' --airespace vlan3 --format colon --uppercase --session-timeout 3600
# Append directly to an installed users file, preserving its comments:
sudo ./add-mab.sh '02:00:00:00:01:*' --vlan 3 --file /etc/freeradius/3.0/mods-config/files/authorize

# Append an entire IPv4 client subnet; shared secret is prompted without echo:
./add-radsec-subnet.sh 192.0.2.0/24 --dry-run
./add-radsec-subnet.sh 192.0.2.0/24
# Or read a secret from an ignored file:
./add-radsec-subnet.sh 198.51.100.0/24 --secret-file config/radius.secret
# TLS references a TLS block already defined earlier in the target config:
./add-radsec-subnet.sh 192.0.2.0/24 --type TLS --tls trusted_clients --file /etc/radsecproxy.conf
```

Quote MAC wildcards to prevent shell expansion. A prefix consists of complete
hexadecimal octets; an optional trailing `*` fills the remaining octets. Each
generated MAB user's password equals its formatted MAC address. Match the NAS's
case and separators with `--format plain|colon|hyphen|cisco` and `--uppercase`.
Existing exact usernames are skipped, preserving their passwords and VLANs;
rerunning does not modify those entries. Expansions larger than 65,536 addresses
fail unless you explicitly raise `--max-entries` (a three-octet prefix is over
16 million entries). Narrow the prefix for manageable files.

FreeRADIUS processes users in order: an earlier matching entry without
`Fall-Through` can prevent EOF entries from being reached. Review existing
defaults if new users do not match; see the [users manual](https://www.freeradius.org/radiusd/man/users.html).
The normal `--radius-only` setup still replaces its target users file from the
local copy, so keep persistent additions in `config/freeradius/users` as well
if you plan to rerun that setup.

The subnet helper writes one [radsecproxy CIDR client block](https://radsecproxy.github.io/radsecproxy.conf.html)
and rejects duplicate client names or identical CIDRs in the target file.
Overlapping ranges and included files still need review because earlier
clients take precedence. This adds a client source subnet, not upstream
servers or realm routing. UDP/TCP secrets use radsecproxy's reversible hex
encoding for exact handling of special characters; this is not encryption.
Dry runs use a placeholder secret. TLS/DTLS keep certificate validation enabled
and use the protocol default shared secret.

Before using the services, configure:

- FreeRADIUS: clients, shared secrets, and authentication under `/etc/freeradius/`.
- radsecproxy: peers, routing, and TLS certificates in `/etc/radsecproxy.conf`. It may not start until a valid configuration is supplied. See the [Debian radsecproxy manual](https://manpages.debian.org/trixie/radsecproxy/index.html).
- BIND9: zones, listening interfaces, and recursion access in `/etc/bind/`. Check for an existing DNS service using port 53.

Check service status on the Pi with `systemctl status freeradius radsecproxy named`. Actual installation and service behavior must be verified on the target Pi.
