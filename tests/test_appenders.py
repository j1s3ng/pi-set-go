import importlib.util
import ipaddress
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
import io

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from append_config import append_block


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


mab = module('mab', 'add-mab.py')
radsec = module('radsec', 'add-radsec-subnet.py')


class AppenderTests(unittest.TestCase):
    def test_mac_expansion_and_repeat(self):
        prefix, count = mab.prefix_range('02:00:00:00:01:*')
        self.assertEqual(count, 256)
        block = mab.make_entries('', prefix, count, 'plain', False, 3, None, None)
        self.assertEqual(block.count('Cleartext-Password'), 256)
        self.assertIn('020000000100 Cleartext-Password := "020000000100"', block)
        self.assertIn('0200000001ff Cleartext-Password := "0200000001ff"', block)
        self.assertEqual(mab.make_entries(block, prefix, count, 'plain', False, 3, None, None), '')

    def test_formats_and_validation(self):
        self.assertEqual(mab.mac_format('02000000aabb', 'hyphen', True), '02-00-00-00-AA-BB')
        self.assertEqual(mab.mac_format('02000000aabb', 'cisco'), '0200.0000.aabb')
        for prefix in ('*', '02:*:ff', '03:00:*', '0:*', '02;evil'):
            with self.assertRaises(ValueError):
                mab.prefix_range(prefix)

    def test_airespace_and_timeout(self):
        block = mab.make_entries('', '02000000aabb', 1, 'colon', False, None, 'vlan3', 600)
        self.assertIn('Session-Timeout := 600,', block)
        self.assertIn('Airespace-Interface-Name := "vlan3"', block)
        self.assertNotIn('Tunnel-Private-Group-Id', block)

    def test_cidr_and_secret_encoding(self):
        net = ipaddress.IPv4Network('192.0.2.0/24')
        block = radsec.client_block('', net, 'test_subnet', 'UDP', 'a%12"b', None)
        self.assertIn('host 192.0.2.0/24', block)
        encoded = block.split('secret %%')[1].splitlines()[0]
        self.assertEqual(bytes.fromhex(encoded).decode(), 'a%12"b')
        with self.assertRaises(ValueError):
            radsec.client_block(block, net, 'another_name', 'UDP', 'other', None)
        with self.assertRaises(ValueError):
            radsec.client_block(block, ipaddress.IPv4Network('198.51.100.0/24'), 'test_subnet', 'UDP', 'other', None)

    def test_tls_keeps_validation(self):
        block = radsec.client_block('', ipaddress.IPv4Network('192.0.2.0/24'), 'test', 'TLS', None, 'trusted_clients')
        self.assertIn('tls trusted_clients', block)
        self.assertNotIn('secret', block)
        self.assertNotIn('CertificateNameCheck off', block)

    def test_append_preserves_original_and_backups(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            path = Path(directory) / 'users'
            original = b'# original comments\nexisting entry'
            path.write_bytes(original)
            append_block(path, lambda text: '# block\nnew entry\n')
            self.assertTrue(path.read_bytes().startswith(original + b'\n\n'))
            backups = list(path.parent.glob('users.backup-*'))
            self.assertEqual(backups[0].read_bytes(), original)
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
            before = path.read_bytes()
            append_block(path, lambda text: '')
            self.assertEqual(path.read_bytes(), before)
            append_block(path, lambda text: 'preview', dry_run=True)
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
