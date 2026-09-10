"""Shared append-only file update with locking and a private backup."""
import fcntl
import os
from pathlib import Path
import tempfile


def append_block(path, builder, dry_run=False):
    path = Path(path).expanduser().resolve()
    if dry_run:
        original = path.read_text() if path.exists() else ''
        block = builder(original)
        print(block or 'Nothing to append.')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, 'r+b') as target:
        fcntl.flock(target, fcntl.LOCK_EX)
        original = target.read()
        block = builder(original.decode())
        if not block:
            print('Nothing to append; existing entries preserved.')
            return
        backup_fd, backup = tempfile.mkstemp(prefix=path.name + '.backup-', dir=path.parent)
        with os.fdopen(backup_fd, 'wb') as copy:
            copy.write(original)
        addition = ('\n' if original.endswith(b'\n') or not original else '\n\n') + block.rstrip() + '\n'
        try:
            target.seek(0, os.SEEK_END)
            target.write(addition.encode())
            target.flush()
            os.fsync(target.fileno())
        except Exception:
            target.truncate(len(original))
            raise
        print(f'Appended to {path}; backup: {backup}')
