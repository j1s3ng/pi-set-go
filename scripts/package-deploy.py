"""Build a private SSH transfer archive; never upload ignored configuration to Git."""
from pathlib import Path
import subprocess
import sys
import tarfile


def package(root, output):
    tracked = subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z']).decode().split('\0')
    paths = {Path(name) for name in tracked if name and (root / name).exists()}
    paths.add(Path('config'))
    paths.update(path.relative_to(root) for path in (root / 'config').rglob('*'))
    with tarfile.open(output, 'w') as archive:
        for relative in sorted(paths):
            path = root / relative
            private = relative.parts[0] == 'config'
            if private and any('.backup-' in part or part.endswith('.log') or part == '__pycache__' for part in relative.parts):
                continue
            if path.is_symlink():
                raise ValueError(f'Transfer requires regular files/directories; replace symlink: {relative}')
            if not path.is_file() and not path.is_dir():
                raise ValueError(f'Unsupported file type: {relative}')
            info = archive.gettarinfo(str(path), arcname=str(relative))
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            if private:
                info.mode = 0o700 if path.is_dir() else 0o600
            if path.is_file():
                with path.open('rb') as stream:
                    archive.addfile(info, stream)
            else:
                archive.addfile(info)


if __name__ == '__main__':
    package(Path(sys.argv[1]).resolve(), Path(sys.argv[2]))
