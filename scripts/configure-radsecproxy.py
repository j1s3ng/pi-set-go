#!/usr/bin/env python3
"""Deploy the ignored local radsecproxy.conf to /etc after validation."""
import argparse
import grp
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import tempfile


def read_config(source):
    if not source.is_file():
        raise ValueError(f'Missing local configuration: {source}. Copy your ignored config/ directory onto the Pi first.')
    content = source.read_bytes()
    if not any(line.strip() and not line.lstrip().startswith(b'#') for line in content.splitlines()):
        raise ValueError('Local radsecproxy.conf is empty or contains only example comments; supply a working configuration.')
    return content


def deploy(source, destination=Path('/etc/radsecproxy.conf'), backup_root=Path('/var/backups')):
    content = read_config(source)
    if destination.is_symlink():
        raise ValueError('Destination is a symlink; review its target before deployment.')
    # The package's service account must be able to read the secret-bearing file.
    user = subprocess.check_output(['systemctl', 'show', 'radsecproxy', '-p', 'User', '--value'], text=True).strip() or 'root'
    group = subprocess.check_output(['systemctl', 'show', 'radsecproxy', '-p', 'Group', '--value'], text=True).strip()
    gid = grp.getgrnam(group).gr_gid if group else pwd.getpwnam(user).pw_gid
    backup = Path(tempfile.mkdtemp(prefix='pi-set-go-radsec-', dir=backup_root))
    existed = destination.exists()
    previous_owner = None
    if existed:
        stat = destination.stat()
        previous_owner = (stat.st_uid, stat.st_gid)
        shutil.copy2(destination, backup / 'radsecproxy.conf')
    was_active = subprocess.run(['systemctl', 'is-active', '--quiet', 'radsecproxy']).returncode == 0
    fd, staged_name = tempfile.mkstemp(prefix='.pi-set-go-radsec-', dir=destination.parent)
    staged = Path(staged_name)
    installed = False
    print(f'Radsecproxy backup and validation log: {backup}', flush=True)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(content)
        os.chown(staged, 0, gid)
        staged.chmod(0o640)
        with (backup / 'validation.log').open('w') as log:
            subprocess.run(['radsecproxy', '-p', '-c', str(staged)], cwd=destination.parent,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        os.replace(staged, destination)
        installed = True
        subprocess.run(['systemctl', 'restart', 'radsecproxy'], check=True)
        subprocess.run(['systemctl', 'is-active', '--quiet', 'radsecproxy'], check=True)
        subprocess.run(['systemctl', 'enable', 'radsecproxy'], check=True)
    except Exception:
        if installed:
            if existed:
                shutil.copy2(backup / 'radsecproxy.conf', destination)
                os.chown(destination, *previous_owner)
            else:
                destination.unlink()
            subprocess.run(['systemctl', 'restart' if was_active else 'stop', 'radsecproxy'], check=False)
        print(f'Deployment failed; previous configuration retained/restored. Inspect {backup}/validation.log.')
        raise
    finally:
        if staged.exists():
            staged.unlink()
    print(f'Deployed {source} to {destination}; radsecproxy is enabled and active.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run with sudo.')
    if not shutil.which('radsecproxy'):
        parser.error('radsecproxy is not installed. Run the full setup first or install the package.')
    try:
        deploy(args.source)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
