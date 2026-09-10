#!/usr/bin/env python3
"""Configure the Debian FreeRADIUS 3 package; preserve its TLS settings."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def setting(text, name, value):
    pattern = rf"(?m)^([ \t]*){re.escape(name)}[ \t]*=.*$"
    if len(re.findall(pattern, text)) != 1:
        raise ValueError(f"Expected exactly one active {name} setting")
    return re.sub(pattern, lambda m: f"{m[1]}{name} = {value}", text)


def configure_eap(text):
    # Match the packaged PEAP block by its indentation, including nested blocks.
    pattern = r"(?ms)^([ \t]+)peap[ \t]*\{.*?^\1\}"
    blocks = list(re.finditer(pattern, text))
    if len(blocks) != 1:
        raise ValueError("Expected one packaged PEAP block")
    block = blocks[0]
    peap = block.group()
    peap = setting(peap, "default_eap_type", "mschapv2")
    peap = setting(peap, "use_tunneled_reply", "yes")
    peap = setting(peap, "virtual_server", '"inner-tunnel"')
    text = text[:block.start()] + peap + text[block.end():]
    # The first active default_eap_type must belong to the outer eap module.
    pattern = r"(?m)^([ \t]+)default_eap_type[ \t]*=.*$"
    first = re.search(pattern, text)
    first_child = re.search(r"(?m)^[ \t]+[^#\n]+\{[ \t]*(?:#.*)?$", text)
    if not first or (first_child and first.start() > first_child.start()):
        raise ValueError("Cannot locate the outer EAP default safely")
    return text[:first.start()] + first[1] + "default_eap_type = peap" + text[first.end():]


def main():
    root = Path("/etc/freeradius/3.0")
    users = Path(sys.argv[1])
    eap = root / "mods-available/eap"
    if eap.is_symlink():
        raise ValueError("Custom EAP symlink requires manual review")
    updated = configure_eap(eap.read_text())
    links = [(root / f"mods-enabled/{name}", Path(f"../mods-available/{name}"))
             for name in ("eap", "mschap", "files")]
    links.append((root / "sites-enabled/inner-tunnel", Path("../sites-available/inner-tunnel")))
    for link, target in links:
        if not (link.parent / target).is_file():
            raise ValueError(f"Missing packaged configuration: {target}")
        if os.path.lexists(link) and (not link.is_symlink() or link.resolve() != (link.parent / target).resolve()):
            raise ValueError(f"Custom enabled configuration requires manual review: {link}")
    content = users.read_text() if users.is_file() else ""
    has_users = any(line.strip() and not line.lstrip().startswith("#") for line in content.splitlines())
    backup = Path(tempfile.mkdtemp(prefix="pi-set-go-radius-", dir="/var/backups"))
    shutil.copytree(root, backup / "config", symlinks=True)
    print(f"FreeRADIUS backup: {backup}", flush=True)
    changed = []
    owners = {}
    created = []
    try:
        changed.append(eap)
        owners[eap] = (eap.stat().st_uid, eap.stat().st_gid)
        eap.write_text(updated)
        if has_users:
            destination = (root / "mods-config/files/authorize").resolve()
            if not destination.is_relative_to(root):
                raise ValueError("Users destination points outside the FreeRADIUS directory")
            if not destination.is_file():
                raise ValueError("Missing packaged users file")
            changed.append(destination)
            owners[destination] = (destination.stat().st_uid, destination.stat().st_gid)
            destination.write_text(content)
            destination.chmod(0o640)
            shutil.chown(destination, user="root", group="freerad")
        for link, target in links:
            if not os.path.lexists(link):
                link.symlink_to(target)
                created.append(link)
        # Validation output may include credentials; keep it in the private backup.
        with (backup / "validation.log").open("w") as log:
            subprocess.run(["freeradius", "-XC"], stdout=log, stderr=subprocess.STDOUT, check=True)
        subprocess.run(["systemctl", "restart", "freeradius"], check=True)
        subprocess.run(["systemctl", "is-active", "--quiet", "freeradius"], check=True)
    except Exception:
        for link in created:
            link.unlink()
        for path in changed:
            original = backup / "config" / path.relative_to(root)
            shutil.copy2(original, path)
            os.chown(path, *owners[path])
        print(f"Restored changed files. Inspect {backup}/validation.log and service status.", file=sys.stderr)
        raise
    print("Configured PEAP/MSCHAPv2 with tunneled VLAN replies; existing TLS settings retained.")
    if not has_users:
        print("No local user entries supplied; existing server users were preserved.")
    print("Set per-user VLAN attributes, RADIUS clients, and trusted server certificates before use.")


if __name__ == "__main__":
    main()
