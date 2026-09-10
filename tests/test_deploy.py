import importlib.util
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


radsec = load('radsec_deploy', 'configure-radsecproxy.py')
pack = load('package_deploy', 'package-deploy.py')


class DeploymentTests(unittest.TestCase):
    def test_setup_prevents_proxy_start_during_apt(self):
        script = Path(__file__).resolve().parents[1] / 'pi-set-go.sh'
        output = subprocess.check_output(['bash', str(script), '--dry-run'], text=True)
        self.assertLess(output.index('mask --runtime --now radsecproxy'), output.index('apt-get'))
        self.assertLess(output.index('disable --now radsecproxy'), output.index('configure-radius.py'))
        self.assertNotIn('1814', output)

    def test_missing_and_placeholder_config_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source'
            with self.assertRaises(ValueError):
                radsec.read_config(source)
            source.write_text('# example\n\n')
            with self.assertRaises(ValueError):
                radsec.read_config(source)

    def run_deployment(self, fail_at=None, require_valid=True):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()) as output:
            root = Path(folder)
            source, target = root / 'source', root / 'radsecproxy.conf'
            source.write_text('client new {\n type UDP\n}\n')
            target.write_text('# original config\n')
            failed = False
            calls = []

            def run(command, **kwargs):
                nonlocal failed
                calls.append(command)
                if not failed and fail_at and fail_at in command:
                    failed = True
                    if not kwargs.get('check', False):
                        return subprocess.CompletedProcess(command, 1)
                    raise subprocess.CalledProcessError(1, command)
                return subprocess.CompletedProcess(command, 0)

            with patch.object(radsec.subprocess, 'check_output', side_effect=['root', '']), \
                 patch.object(radsec.os, 'chown'), patch.object(radsec.subprocess, 'run', side_effect=run):
                if fail_at and (fail_at != '-p' or require_valid):
                    with self.assertRaises(subprocess.CalledProcessError):
                        radsec.deploy(source, target, root, require_valid=require_valid)
                    self.assertEqual(target.read_text(), '# original config\n')
                else:
                    validated = radsec.deploy(source, target, root, require_valid=require_valid)
                    self.assertEqual(validated, fail_at is None)
                    if fail_at:
                        self.assertIn('Validation pending', output.getvalue())
                    self.assertEqual(target.read_bytes(), source.read_bytes())
                    self.assertEqual(target.stat().st_mode & 0o777, 0o640)
                    self.assertIn(['systemctl', 'disable', '--now', 'radsecproxy'], calls)
                    self.assertFalse(any(command[0] == 'systemctl' and command[1] in ('start', 'restart', 'enable') for command in calls))
                self.assertEqual(list(root.glob('.pi-set-go-radsec-*')), [])

    def test_successful_deploy(self):
        self.run_deployment()

    def test_invalid_config_keeps_installed_file(self):
        self.run_deployment('-p')

    def test_failed_stop_keeps_installed_file(self):
        self.run_deployment('disable')

    def test_missing_certificates_can_be_provisioned_later(self):
        self.run_deployment('-p', require_valid=False)

    def test_private_archive_and_exclusions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'config').mkdir()
            (root / 'setup.sh').write_text('#!/bin/sh\n')
            (root / 'config/radsecproxy.conf').write_text('private-config')
            (root / 'config/dns').mkdir()
            (root / 'config/dns/zones.list').write_text('private.test\n')
            (root / 'config/old.backup-123').write_text('old secret')
            (root / 'config/validation.log').write_text('log')
            (root / 'untracked.txt').write_text('untracked')
            archive = root / 'transfer.tar'
            with patch.object(pack.subprocess, 'check_output', return_value=b'setup.sh\0'):
                pack.package(root, archive)
            with tarfile.open(archive) as tar:
                self.assertEqual(set(tar.getnames()), {'setup.sh', 'config', 'config/radsecproxy.conf', 'config/dns', 'config/dns/zones.list'})
                self.assertEqual(tar.getmember('config').mode, 0o700)
                self.assertEqual(tar.getmember('config/radsecproxy.conf').mode, 0o600)
                self.assertEqual(tar.extractfile('config/radsecproxy.conf').read(), b'private-config')
                self.assertEqual(tar.extractfile('config/dns/zones.list').read(), b'private.test\n')

    def test_archive_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'config').mkdir()
            (root / 'config/link').symlink_to('/etc/passwd')
            with patch.object(pack.subprocess, 'check_output', return_value=b''):
                with self.assertRaises(ValueError):
                    pack.package(root, root / 'transfer.tar')


if __name__ == '__main__':
    unittest.main()
