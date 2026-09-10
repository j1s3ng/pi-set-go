import importlib.util
import ipaddress
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import io

spec = importlib.util.spec_from_file_location('dns', Path(__file__).resolve().parents[1] / 'scripts/configure-dns.py')
dns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dns)


def interface(name, address='192.0.2.10', prefix=24):
    return {'ifname': name, 'flags': ['UP'], 'addr_info': [
        {'family': 'inet', 'scope': 'global', 'local': address, 'prefixlen': prefix}]}


class DnsTests(unittest.TestCase):
    def test_eth0_and_subnet(self):
        name, addr = dns.select_address([interface('eth0')], [], {'eth0'})
        self.assertEqual(name, 'eth0')
        self.assertEqual(str(addr.network), '192.0.2.0/24')

    def test_predictable_name_and_wifi_exclusion(self):
        items = [interface('wlan0'), interface('enx001122334455')]
        route = [{'dst': 'default', 'dev': 'wlan0'}]
        self.assertEqual(dns.select_address(items, route, {'enx001122334455'})[0], 'enx001122334455')

    def test_default_route_and_override(self):
        items = [interface('eth0'), interface('enp2s0', '198.51.100.5')]
        route = [{'dst': 'default', 'dev': 'enp2s0'}]
        self.assertEqual(dns.select_address(items, route, {'eth0', 'enp2s0'})[0], 'enp2s0')
        self.assertEqual(dns.select_address(items, route, {'eth0', 'enp2s0'}, 'eth0')[0], 'eth0')

    def test_ambiguity_and_missing_address(self):
        for items in ([], [interface('eth0'), interface('enp2s0')]):
            with self.assertRaises(ValueError):
                dns.select_address(items, [], {'eth0', 'enp2s0'})

    def test_private_zone_list_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'zones.list'
            with self.assertRaises(ValueError):
                dns.domains_from(path)
            path.write_text('super.local\nprivate.test # local only\n')
            self.assertEqual(dns.domains_from(path), ['super.local', 'private.test'])
            path.write_text('../escape\n')
            with self.assertRaises(ValueError):
                dns.domains_from(path)

    def test_records_follow_address(self):
        zone = dns.zone_text('super.local', ipaddress.IPv4Address('198.51.100.8'), 123)
        self.assertEqual(zone.count('IN A 198.51.100.8'), 2)
        self.assertIn('123 ; serial', zone)
        for number in range(1, 4):
            self.assertIn(f'; ise0{number}.super.local. IN A 192.0.2.{10 + number}', zone)

    def test_options_use_detected_cidr_and_reference_forwarders(self):
        address = ipaddress.IPv4Interface('198.51.100.130/25')
        options = dns.options_text('enx001122334455', address)
        self.assertIn('listen-on { 127.0.0.1; 198.51.100.130; };', options)
        self.assertIn('198.51.100.128/25;', options)
        self.assertNotIn('198.51.100.0/24', options)
        self.assertIn('allow-recursion { trusted; };', options)
        self.assertIn('allow-query-cache { trusted; };', options)
        self.assertIn('allow-transfer { none; };', options)
        self.assertIn('forwarders { 8.8.8.8; 8.8.4.4; };', options)

    def test_reverse_authority_covers_exact_subnet_for_any_prefix(self):
        for prefix in range(33):
            with self.subTest(prefix=prefix):
                network = ipaddress.IPv4Interface(f'192.0.2.130/{prefix}').network
                zones = dns.reverse_networks(network)
                self.assertLessEqual(len(zones), 128)
                self.assertEqual(list(ipaddress.collapse_addresses(zones)), [network])
                self.assertTrue(all(zone.prefixlen % 8 == 0 for zone in zones))

    def test_reverse_ptr_owners_for_different_subnets(self):
        for address, origin, owner in [
            ('192.0.2.10/24', '2.0.192.in-addr.arpa', '10'),
            ('198.51.100.10/16', '51.198.in-addr.arpa', '10.100'),
            ('192.0.2.130/25', '130.2.0.192.in-addr.arpa', '@'),
            ('192.0.2.130/32', '130.2.0.192.in-addr.arpa', '@'),
        ]:
            with self.subTest(address=address), tempfile.TemporaryDirectory() as directory:
                zones = dns.generated_zones(['super.local', 'private.test'], ipaddress.IPv4Interface(address), Path(directory))
                self.assertIn(f'{owner} IN PTR ns1.super.local.\n', zones[origin])
                self.assertEqual(sum(text.count(' IN PTR ') for text in zones.values()), 1)
                self.assertIn('private.test', zones)
                self.assertIn('ise03.private.test.', zones['private.test'])

    def test_regeneration_advances_serials_and_replaces_old_address_and_domains(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(dns.time, 'time', return_value=100):
            managed = Path(directory)
            old = dns.generated_zones(['super.local', 'old.test'], ipaddress.IPv4Interface('192.0.2.10/24'), managed)
            for name, text in old.items():
                (managed / f'db.{name}').write_text(text)
            current = dns.generated_zones(['super.local'], ipaddress.IPv4Interface('192.0.2.20/24'), managed)
            self.assertIn('101 ; serial', current['super.local'])
            self.assertIn('101 ; serial', current['2.0.192.in-addr.arpa'])
            self.assertIn('20 IN PTR ns1.super.local.', current['2.0.192.in-addr.arpa'])
            self.assertNotIn('192.0.2.10', ''.join(current.values()))
            self.assertNotIn('old.test', dns.zone_declarations(current, managed))
            moved = dns.generated_zones(['super.local'], ipaddress.IPv4Interface('198.51.100.20/24'), managed)
            self.assertNotIn('2.0.192.in-addr.arpa', dns.zone_declarations(moved, managed))
            self.assertIn('100.51.198.in-addr.arpa', moved)

    def test_private_list_cannot_override_generated_reverse_zone(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                dns.generated_zones(['super.local', '2.0.192.in-addr.arpa'],
                                    ipaddress.IPv4Interface('192.0.2.10/24'), Path(directory))

    def test_zone_preflight_needs_no_network_or_root(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'zones.list').write_text('super.local\nprivate.test\n')
            with patch('sys.argv', ['configure-dns.py', directory, '--check-zones']), \
                 patch.object(dns.os, 'geteuid', return_value=1000), \
                 patch.object(dns.subprocess, 'check_output', side_effect=AssertionError('Preflight accessed the network')), \
                 patch('sys.stdout', io.StringIO()) as output:
                dns.main()
            self.assertIn('2 zones', output.getvalue())

    def test_dry_run_reads_network_without_writing(self):
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'zones.list').write_text('super.local\n')
            with patch('sys.argv', ['configure-dns.py', directory, '--dry-run']), \
                 patch.object(dns.subprocess, 'check_output', side_effect=[b'[]', b'[]']) as read_network, \
                 patch.object(dns.Path, 'iterdir', return_value=[]), \
                 patch.object(dns, 'select_address', return_value=('eth0', ipaddress.IPv4Interface('192.0.2.10/24'))), \
                 patch.object(dns.Path, 'write_text', side_effect=AssertionError('Dry run wrote a file')), \
                 patch.object(dns.tempfile, 'mkdtemp', side_effect=AssertionError('Dry run created a backup')), \
                 patch.object(dns.subprocess, 'run', side_effect=AssertionError('Dry run changed a service')), \
                 patch('sys.stdout', output):
                dns.main()
        self.assertEqual(read_network.call_count, 2)
        self.assertIn('Detected eth0: 192.0.2.10/24', output.getvalue())
        self.assertIn('zone "super.local"', output.getvalue())
        self.assertIn('IN A 192.0.2.10', output.getvalue())
        self.assertIn('192.0.2.0/24;', output.getvalue())
        self.assertIn('zone "2.0.192.in-addr.arpa"', output.getvalue())
        self.assertIn('10 IN PTR ns1.super.local.', output.getvalue())


if __name__ == '__main__':
    unittest.main()
