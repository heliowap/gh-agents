"""Seam: the checked-in `run:` shell of the review steps in agents.yml.

Each test executes the step's script as written in the workflow; only the
external GitHub CLI is doubled (a fake `gh` on PATH that logs its argv and
answers from fixtures).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/agents.yml"


def _step(job: str, step_id: str) -> str:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"][job]["steps"]
    return next(s for s in steps if s.get("id") == step_id)["run"]


def _fake_gh(tmp_path: Path, body: str) -> dict:
    gh = tmp_path / "bin" / "gh"
    gh.parent.mkdir()
    gh.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['GH_CALLS'], 'a') as log:\n"
        "    log.write(json.dumps(args) + '\\n')\n"
        + body
    )
    gh.chmod(0o755)
    return {"PATH": f"{gh.parent}:{os.environ['PATH']}", "GH_CALLS": str(tmp_path / "calls.jsonl")}


def _run(tmp_path: Path, script: str, env: dict, cwd: Path) -> tuple[subprocess.CompletedProcess, list, str]:
    output = tmp_path / "github_output"
    output.touch()
    proc = subprocess.run(
        ["bash", "-c", script], cwd=cwd, text=True, capture_output=True, check=False,
        env={**os.environ, "GITHUB_REPOSITORY": "example/repo", "GH_TOKEN": "test",
             "GITHUB_OUTPUT": str(output), **env},
    )
    log = tmp_path / "calls.jsonl"
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return proc, calls, output.read_text()


# --- actor gate (#19) ---------------------------------------------------------

def _gate(tmp_path: Path, actor: str, permission: str | None):
    answer = f"print({permission!r})\n" if permission else "sys.exit(1)\n"
    env = _fake_gh(tmp_path, answer) | {"ACTOR": actor}
    return _run(tmp_path, _step("gate", "actor"), env, tmp_path)


def test_gate_skips_actor_without_write(tmp_path: Path) -> None:
    proc, calls, output = _gate(tmp_path, "devin-ai-integration[bot]", "none")
    assert proc.returncode == 0, proc.stderr
    assert "reviewable=false" in output
    assert "::notice" in proc.stdout and "devin-ai-integration[bot]" in proc.stdout
    assert calls[0][:2] == ["api", "repos/example/repo/collaborators/devin-ai-integration[bot]/permission"]


def test_gate_skips_read_only_actor(tmp_path: Path) -> None:
    _, _, output = _gate(tmp_path, "someone", "read")
    assert "reviewable=false" in output


def test_gate_reviews_actor_with_write(tmp_path: Path) -> None:
    for perm in ("write", "maintain", "admin"):
        (tmp_path / perm).mkdir()
        _, _, output = _gate(tmp_path / perm, "heliowap", perm)
        assert "reviewable=true" in output, perm


def test_gate_fails_open_when_the_lookup_fails(tmp_path: Path) -> None:
    proc, _, output = _gate(tmp_path, "heliowap", None)
    assert proc.returncode == 0, proc.stderr
    assert "reviewable=true" in output


# --- BLOCKING -> review-blocking issue (#20) ----------------------------------

BLOCKING_REVIEW = "BLOCKING\n- a.py:1 breaks the build\n\nWARNING\n  (none)\n\nSUMMARY: 1 BLOCKING, 0 WARNING, 0 NIT"


def _comment(body: str, created: str, url: str, login: str = "github-actions[bot]") -> dict:
    return {"user": {"login": login}, "body": body, "created_at": created, "html_url": url}


def _blocking(tmp_path: Path, comments: list[dict], issues: list[dict], since: str):
    fake = (
        f"comments = {comments!r}\n"
        f"issues = {issues!r}\n"
        "if args[0] == 'api':\n"
        "    endpoint = next(a for a in args if a.startswith('repos/'))\n"
        "    print(json.dumps(comments if '/comments?' in endpoint else issues))\n"
    )
    # the step calls `.gh-agents/scripts/review_blocking.py` relative to the workspace
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".gh-agents").symlink_to(ROOT)
    env = _fake_gh(tmp_path, fake) | {"PR": "1609", "SHA": "abc123", "SINCE": since}
    return _run(tmp_path, _step("review", "blocking"), env, workspace)


def test_blocking_ignores_valid_review_from_before_the_run(tmp_path: Path) -> None:
    # intrador #1415: this run's review is off-format; the previous SHA's
    # valid review must not be reported against the new SHA.
    comments = [
        _comment(BLOCKING_REVIEW, "2026-09-13T20:02:20Z", "https://example/previous-sha"),
        _comment("SUMMARY: the earlier BLOCKING is fixed", "2026-09-13T20:43:14Z", "https://example/current"),
    ]
    proc, calls, _ = _blocking(tmp_path, comments, [], since="2026-09-13T20:30:00Z")
    assert proc.returncode == 0, proc.stderr
    assert not any(c[:2] in (["issue", "create"], ["issue", "comment"]) for c in calls)
    assert "::warning" in proc.stdout


def test_blocking_in_this_run_opens_an_issue_with_the_block(tmp_path: Path) -> None:
    comments = [
        _comment(BLOCKING_REVIEW, "2026-09-13T20:43:14Z", "https://example/current"),
        _comment("SUMMARY: 9 BLOCKING", "2026-09-13T20:50:00Z", "https://example/human", login="heliowap"),
    ]
    proc, calls, _ = _blocking(tmp_path, comments, [], since="2026-09-13T20:30:00Z")
    assert proc.returncode == 0, proc.stderr
    created = next(c for c in calls if c[:2] == ["issue", "create"])
    body = created[created.index("--body") + 1]
    assert "https://example/current" in body and "a.py:1 breaks the build" in body
    assert "PR #1609 " in created[created.index("--title") + 1]


def test_blocking_reopens_the_closed_issue_of_the_same_pr(tmp_path: Path) -> None:
    comments = [_comment(BLOCKING_REVIEW, "2026-09-13T20:43:14Z", "https://example/current")]
    issues = [{"number": 7, "title": "review-blocking: PR #1609 with BLOCKING in review", "state": "closed"},
              {"number": 8, "title": "review-blocking: PR #16090 with BLOCKING in review", "state": "open"}]
    proc, calls, _ = _blocking(tmp_path, comments, issues, since="2026-09-13T20:30:00Z")
    assert proc.returncode == 0, proc.stderr
    assert ["issue", "reopen", "7"] in calls
    assert any(c[:3] == ["issue", "comment", "7"] for c in calls)
    assert not any(c[:2] == ["issue", "create"] for c in calls)
