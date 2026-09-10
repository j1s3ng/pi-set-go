import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('remote', Path(__file__).resolve().parents[1] / 'scripts/configure-remote.py')
remote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)


class RemoteTests(unittest.TestCase):
    def test_swap_disabled_without_changing_mounts(self):
        original = '# swap example\nUUID=root / ext4 defaults 0 1\n/var/swap none swap sw 0 0\nUUID=swap none swap defaults 0 0\n'
        expected = '# swap example\nUUID=root / ext4 defaults 0 1\n# pi-set-go disabled swap: /var/swap none swap sw 0 0\n# pi-set-go disabled swap: UUID=swap none swap defaults 0 0\n'
        self.assertEqual(remote.disable_fstab_swap(original), expected)
        self.assertEqual(remote.disable_fstab_swap(expected), expected)

    def test_preserve_comments_and_whitespace(self):
        original = '  # /var/swap none swap sw 0 0\n\nproc /proc proc defaults 0 0\n'
        self.assertEqual(remote.disable_fstab_swap(original), original)


if __name__ == '__main__':
    unittest.main()
