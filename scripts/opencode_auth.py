#!/usr/bin/env python3
"""Carry the runner host's opencode OAuth login (ChatGPT Plus/Pro) through a job.

Usage: python3 scripts/opencode_auth.py load <host-auth.json> <job-auth.json>
       python3 scripts/opencode_auth.py save <job-auth.json> <host-auth.json>
Exit:  0 done (or nothing to do); 1 the host has no login to load

The login lives in one file on the runner host, bind-mounted into the job
container. `load` copies it to where opencode reads it ($XDG_DATA_HOME). The
refresh token rotates: opencode trades it for a new one whenever the access
token expires, and the old one stops working. `save` writes a refreshed OAuth
entry back to the host — only when it is newer than the host's, so a job that
started earlier never undoes another job's refresh. The host file is rewritten
in place (a bind-mounted file cannot be swapped by rename). Nothing from the
file is ever printed.
"""

import json
import os
import sys
from pathlib import Path


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _same(a: Path, b: Path) -> bool:
    return a.exists() and b.exists() and os.path.samefile(a, b)


def load(host: Path, job: Path) -> int:
    if not host.is_file():
        print(f"::error title=No ChatGPT login::{host} is not a file on the runner host — "
              "log in once as the runner user with `opencode auth login` (README: ChatGPT login)")
        return 1
    if _same(host, job):
        print("opencode login already in place (host mode)")
        return 0
    job.parent.mkdir(parents=True, exist_ok=True)
    job.touch(mode=0o600, exist_ok=True)
    job.chmod(0o600)
    job.write_bytes(host.read_bytes())
    print(f"opencode login loaded: {', '.join(sorted(_read(job))) or 'no providers'}")
    return 0


def refreshed(job: dict, host: dict) -> dict:
    """Host entries, with each job OAuth entry that expires later than the host's."""
    merged = dict(host)
    for name, entry in job.items():
        if not (isinstance(entry, dict) and entry.get("type") == "oauth"):
            continue
        current = host.get(name) if isinstance(host.get(name), dict) else {}
        if entry.get("expires", 0) > current.get("expires", 0):
            merged[name] = entry
    return merged


def save(job: Path, host: Path) -> int:
    if not job.is_file() or not host.is_file() or _same(job, host):
        return 0
    current = _read(host)
    merged = refreshed(_read(job), current)
    if merged == current:
        print("opencode login unchanged")
        return 0
    with open(host, "r+") as f:   # in place: keeps the inode the container mounts
        f.write(json.dumps(merged, indent=2))
        f.truncate()
    changed = sorted(k for k in merged if merged[k] != current.get(k))
    print(f"opencode login refreshed on the host: {', '.join(changed)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("load", "save"):
        print(__doc__.split("\n\n")[1], file=sys.stderr)
        sys.exit(2)
    action = load if sys.argv[1] == "load" else save
    sys.exit(action(Path(sys.argv[2]), Path(sys.argv[3])))
