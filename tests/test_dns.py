import importlib.util
import ipaddress
from pathlib import Path
import tempfile
import unittest

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
            self.assertEqual(dns.domains_from(path), ['super.local'])
            path.write_text('super.local\nprivate.test # local only\n')
            self.assertEqual(dns.domains_from(path), ['super.local', 'private.test'])
            path.write_text('../escape\n')
            with self.assertRaises(ValueError):
                dns.domains_from(path)

    def test_records_follow_address(self):
        zone = dns.zone_text('super.local', ipaddress.IPv4Address('198.51.100.8'), 123)
        self.assertEqual(zone.count('IN A 198.51.100.8'), 2)
        self.assertIn('123 ; serial', zone)


if __name__ == '__main__':
    unittest.main()
