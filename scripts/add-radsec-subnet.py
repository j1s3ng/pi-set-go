#!/usr/bin/env python3
"""Append one radsecproxy client block covering an IPv4 subnet."""
import argparse
import getpass
import ipaddress
from pathlib import Path
import re
from append_config import append_block


def client_block(original, network, name, protocol, secret, tls):
    if re.search(r'(?im)^\s*client\s+[\"\']?' + re.escape(name) + r'[\"\']?\s*\{', original):
        raise ValueError(f'Client {name} already exists; edit it instead of appending a duplicate')
    host = str(network)
    if re.search(r'(?im)^\s*(?:host|client)\s+[\"\']?' + re.escape(host) + r'[\"\']?(?:\s|$)', original):
        raise ValueError('This subnet is already declared; review the existing configuration')
    lines = [f'# BEGIN pi-set-go subnet {network}', f'client {name} {{',
             f'    host {network}', f'    type {protocol}']
    if tls:
        lines.append(f'    tls {tls}')
    if secret is not None:
        # radsecproxy supports %% hex encoding; preserves %, quotes and spaces exactly.
        lines.append('    secret %%' + secret.encode().hex())
    lines.extend(['}', '# END pi-set-go subnet', ''])
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('subnet', help='IPv4 CIDR, e.g. 192.0.2.0/24')
    parser.add_argument('--name')
    parser.add_argument('--type', choices=['UDP', 'TCP', 'TLS', 'DTLS'], default='UDP')
    parser.add_argument('--tls', help='Existing TLS block name, required for TLS/DTLS')
    parser.add_argument('--secret-file', type=Path, help='Read shared secret from a file instead of a hidden prompt')
    parser.add_argument('--file', type=Path, default=Path(__file__).resolve().parents[1] / 'config/radsecproxy.conf')
    parser.add_argument('--dry-run', action='store_true', help='Preview with a placeholder secret; no writes')
    args = parser.parse_args()
    try:
        if '/' not in args.subnet:
            raise ValueError('Specify a CIDR prefix length')
        network = ipaddress.IPv4Network(args.subnet, strict=True)
        name = args.name or f'subnet_{str(network.network_address).replace(".", "_")}_{network.prefixlen}'
        for value in (name, args.tls):
            if value is not None and not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', value):
                raise ValueError('Block names must contain letters, digits, _, . or -')
        if args.type in ('TLS', 'DTLS') and not args.tls:
            raise ValueError('--tls must reference an existing TLS block')
        if args.type in ('UDP', 'TCP') and args.tls:
            raise ValueError('--tls applies only to TLS/DTLS')
        secret = None
        if args.type in ('UDP', 'TCP'):
            secret = 'REPLACE-WITH-SHARED-SECRET' if args.dry_run else (
                args.secret_file.read_text().rstrip('\r\n') if args.secret_file else getpass.getpass('RADIUS shared secret: '))
            if not secret or any(c in secret for c in '\x00\r\n'):
                raise ValueError('Shared secret must be nonempty and on one line')
        elif args.secret_file:
            raise ValueError('TLS/DTLS use the protocol default secret; omit --secret-file')
        append_block(args.file, lambda original: client_block(original, network, name, args.type, secret, args.tls), args.dry_run)
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
