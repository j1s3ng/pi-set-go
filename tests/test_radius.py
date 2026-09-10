import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("radius", Path(__file__).resolve().parents[1] / "scripts/configure-radius.py")
radius = importlib.util.module_from_spec(spec)
spec.loader.exec_module(radius)

FIXTURE = '''eap {
    default_eap_type = md5
    tls-config tls-common {
        private_key_file = /keep/my/key
    }
    ttls {
        default_eap_type = md5
        use_tunneled_reply = no
    }
    peap {
        # use_tunneled_reply = no (comment must stay)
        default_eap_type = md5
        use_tunneled_reply = no
        virtual_server = "custom"
    }
    mschapv2 {
    }
}
'''


class RadiusTests(unittest.TestCase):
    def test_peap_vlan_and_preservation(self):
        result = radius.configure_eap(FIXTURE)
        self.assertIn('    default_eap_type = peap', result)
        self.assertIn('        default_eap_type = mschapv2', result)
        self.assertIn('        use_tunneled_reply = yes', result)
        self.assertIn('        virtual_server = "inner-tunnel"', result)
        self.assertIn('private_key_file = /keep/my/key', result)
        self.assertIn('ttls {\n        default_eap_type = md5\n        use_tunneled_reply = no', result)
        self.assertIn('# use_tunneled_reply = no (comment must stay)', result)
        self.assertEqual(radius.configure_eap(result), result)

    def test_missing_setting_fails(self):
        with self.assertRaises(ValueError):
            radius.configure_eap(FIXTURE.replace('        virtual_server = "custom"\n', ''))

    def test_duplicate_peap_fails(self):
        with self.assertRaises(ValueError):
            radius.configure_eap(FIXTURE + FIXTURE)

    def test_missing_outer_default_fails(self):
        with self.assertRaises(ValueError):
            radius.configure_eap(FIXTURE.replace('    default_eap_type = md5\n', '', 1))


if __name__ == '__main__':
    unittest.main()
