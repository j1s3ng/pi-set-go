import importlib.util
from pathlib import Path
import shlex
import subprocess
import unittest

spec = importlib.util.spec_from_file_location('remote', Path(__file__).resolve().parents[1] / 'scripts/configure-remote.py')
remote = importlib.util.module_from_spec(spec)
spec.loader.exec_module(remote)


class RemoteTests(unittest.TestCase):
    def test_tailscale_repository_bootstrap_and_manual_login(self):
        script = Path(__file__).resolve().parents[1] / 'setup-remote.sh'
        output = subprocess.check_output(['bash', str(script), '--dry-run', '--skip-update'], text=True)
        commands = [shlex.split(line)[1:] for line in output.splitlines() if line.startswith('+')]
        apt = [command for command in commands if 'apt-get' in command]
        self.assertIn('curl', apt[0])
        self.assertIn('ca-certificates', apt[0])
        downloads = [command for command in commands if command[0] == 'curl']
        self.assertEqual(len(downloads), 2)
        self.assertTrue(any(url.startswith('https://pkgs.tailscale.com/stable/') and url.endswith('.noarmor.gpg')
                            for url in downloads[0]))
        self.assertTrue(any(url.endswith('.tailscale-keyring.list') for url in downloads[1]))
        key_install = next(command for command in commands if command[0] == 'install'
                           and command[-1] == '/usr/share/keyrings/tailscale-archive-keyring.gpg')
        self.assertLess(commands.index(downloads[1]), commands.index(key_install))
        # Even --skip-update must load the newly added repository before installing.
        self.assertEqual(len(apt), 3)
        self.assertEqual(apt[1][-1], 'update')
        self.assertEqual(apt[2][-1], 'tailscale')
        self.assertLess(commands.index(key_install), commands.index(apt[1]))
        self.assertIn(['systemctl', 'enable', '--now', 'tailscaled'], commands)
        self.assertIn(['systemctl', 'is-active', '--quiet', 'tailscaled'], commands)
        self.assertFalse(any(command[0] == 'tailscale' for command in commands))
        self.assertIn('sudo tailscale up --accept-dns=false', output)

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
