"""Seam: `python3 scripts/opencode_auth.py load|save <from> <to>` → exit code + files.

The auth.json shape follows what `opencode auth login` writes (opencode 2.0.16):
API-key providers as `{"type": "api", "key": ...}`, the ChatGPT Plus/Pro login
as `{"type": "oauth", "access", "refresh", "expires", "accountId"}`, with
`expires` in epoch milliseconds.
"""

import json
import stat
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "opencode_auth.py"


def _oauth(refresh, expires):
    return {"type": "oauth", "access": f"acc-{refresh}", "refresh": refresh,
            "expires": expires, "accountId": "acct-1"}


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True)


def test_load_copies_the_host_login_into_the_job_home_private(tmp_path):
    host = tmp_path / "host" / "auth.json"
    job = tmp_path / "home" / ".local" / "share" / "opencode" / "auth.json"
    _write(host, {"openai": _oauth("r1", 1000)})

    proc = _run("load", host, job)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(job.read_text()) == {"openai": _oauth("r1", 1000)}
    assert stat.S_IMODE(job.stat().st_mode) == 0o600


def test_load_fails_readably_when_the_host_was_never_logged_in(tmp_path):
    # docker bind-mounts a missing source as an empty directory
    host = tmp_path / "auth.json"
    host.mkdir()

    proc = _run("load", host, tmp_path / "job" / "auth.json")

    assert proc.returncode == 1
    assert "opencode auth login" in proc.stdout


def test_load_onto_itself_is_a_no_op(tmp_path):
    # host-mode jobs run as the fleet user: its auth.json is already in place
    host = tmp_path / "auth.json"
    _write(host, {"openai": _oauth("r1", 1000)})

    proc = _run("load", host, host)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(host.read_text()) == {"openai": _oauth("r1", 1000)}


def test_save_writes_back_a_refreshed_login_keeping_other_host_entries(tmp_path):
    host = tmp_path / "host.json"
    job = tmp_path / "job.json"
    _write(host, {"openai": _oauth("r1", 1000), "opencode": {"type": "api", "key": "k"}})
    _write(job, {"openai": _oauth("r2", 2000)})
    inode = host.stat().st_ino

    proc = _run("save", job, host)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(host.read_text()) == {
        "openai": _oauth("r2", 2000), "opencode": {"type": "api", "key": "k"}}
    # a bind-mounted file cannot be replaced by rename — same inode, rewritten
    assert host.stat().st_ino == inode


def test_save_never_downgrades_a_login_another_job_already_refreshed(tmp_path):
    host = tmp_path / "host.json"
    job = tmp_path / "job.json"
    _write(host, {"openai": _oauth("r3", 3000)})
    _write(job, {"openai": _oauth("r2", 2000)})
    before = host.read_bytes()

    proc = _run("save", job, host)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert host.read_bytes() == before


def test_save_ignores_api_key_entries_from_the_job(tmp_path):
    host = tmp_path / "host.json"
    job = tmp_path / "job.json"
    _write(host, {"openai": _oauth("r1", 1000)})
    _write(job, {"openai": _oauth("r1", 1000), "opencode": {"type": "api", "key": "k"}})
    before = host.read_bytes()

    proc = _run("save", job, host)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert host.read_bytes() == before


def test_save_without_a_job_login_leaves_the_host_alone(tmp_path):
    host = tmp_path / "host.json"
    _write(host, {"openai": _oauth("r1", 1000)})
    before = host.read_bytes()

    proc = _run("save", tmp_path / "missing.json", host)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert host.read_bytes() == before


def test_secrets_never_reach_the_output(tmp_path):
    host = tmp_path / "host.json"
    job = tmp_path / "job" / "auth.json"
    _write(host, {"openai": _oauth("r1", 1000)})
    loaded = _run("load", host, job)
    _write(job, {"openai": _oauth("r2", 2000)})
    saved = _run("save", job, host)

    out = loaded.stdout + loaded.stderr + saved.stdout + saved.stderr
    assert "r1" not in out and "r2" not in out and "acc-" not in out

