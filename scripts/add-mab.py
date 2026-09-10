#!/usr/bin/env python3
"""Expand a trailing MAC wildcard into explicit FreeRADIUS users at EOF."""
import argparse
from pathlib import Path
import re
from append_config import append_block


def prefix_range(value):
    if not re.fullmatch(r'[0-9a-fA-F:.-]+\*?', value):
        raise ValueError('Use a hexadecimal MAC prefix with an optional trailing *, e.g. 02:00:00:00:01:*')
    prefix = re.sub(r'[:.-]', '', value.rstrip('*')).lower()
    if not 2 <= len(prefix) <= 12 or len(prefix) % 2:
        raise ValueError('Prefix must contain 1-6 complete MAC octets')
    if int(prefix[:2], 16) & 1:
        raise ValueError('MAB device prefixes must be unicast MAC addresses')
    return prefix, 16 ** (12 - len(prefix))


def mac_format(value, style, uppercase=False):
    value = value.upper() if uppercase else value
    width, separator = {'plain': (12, ''), 'colon': (2, ':'), 'hyphen': (2, '-'), 'cisco': (4, '.')}[style]
    return separator.join(value[i:i + width] for i in range(0, 12, width))


def make_entries(original, prefix, count, style, uppercase, vlan, airespace, timeout):
    existing = set(re.findall(r'(?m)^\s*"?([0-9a-fA-F:.-]+)"?\s+[^\n]*', original))
    lines = []
    width = 12 - len(prefix)
    for index in range(count):
        value = prefix + (f'{index:0{width}x}' if width else '')
        mac = mac_format(value, style, uppercase)
        if mac in existing:
            continue
        lines.extend([f'{mac} Cleartext-Password := "{mac}"',
                      f'    Session-Timeout := {timeout},' if timeout else '    # Session-Timeout := 3600,'])
        if airespace:
            lines.append(f'    Airespace-Interface-Name := "{airespace}"')
        else:
            lines.extend(['    Tunnel-Type := VLAN,', '    Tunnel-Medium-Type := IEEE-802,',
                          f'    Tunnel-Private-Group-Id := "{vlan}"'])
        lines.append('')
    if not lines:
        return ''
    return f'# BEGIN pi-set-go MAB prefix {prefix}* ({style})\n' + '\n'.join(lines) + '# END pi-set-go MAB prefix\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prefix', help='Quote the wildcard: "02:00:00:00:01:*"')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--vlan', type=int)
    group.add_argument('--airespace', help='Controller interface name')
    parser.add_argument('--format', choices=['plain', 'colon', 'hyphen', 'cisco'], default='plain')
    parser.add_argument('--uppercase', action='store_true')
    parser.add_argument('--session-timeout', type=int)
    parser.add_argument('--max-entries', type=int, default=65536, help='Maximum expansion size (default 65536)')
    parser.add_argument('--file', type=Path, default=Path(__file__).resolve().parents[1] / 'config/freeradius/users')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        prefix, count = prefix_range(args.prefix)
        if args.max_entries < 1 or count > args.max_entries:
            raise ValueError(f'Prefix expands to {count:,} MACs; narrow it or explicitly raise --max-entries')
        if args.vlan is not None and not 1 <= args.vlan <= 4094:
            raise ValueError('VLAN must be 1-4094')
        if args.airespace is not None and not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', args.airespace):
            raise ValueError('Use an interface name containing letters, digits, _, . or -')
        if args.session_timeout is not None and not 1 <= args.session_timeout <= 4294967295:
            raise ValueError('Session timeout must be 1-4294967295 seconds')
        append_block(args.file, lambda original: make_entries(original, prefix, count, args.format,
                     args.uppercase, args.vlan, args.airespace, args.session_timeout), args.dry_run)
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
