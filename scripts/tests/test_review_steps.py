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

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = Path(os.environ.get("GH_AGENTS_WORKFLOW_UNDER_TEST", ROOT / ".github/workflows/agents.yml"))


def _step(job: str, step_id: str) -> str:
    return _step_def(job, step_id)["run"]


def _step_def(job: str, step_id: str) -> dict:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"][job]["steps"]
    return next(s for s in steps if s.get("id") == step_id)


def _literal_env(job: str, step_id: str) -> dict:
    """The step's env entries that are plain values (expressions are doubled by the test)."""
    env = _step_def(job, step_id).get("env") or {}
    return {k: str(v) for k, v in env.items() if "${{" not in str(v)}


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


# --- PR state before checkout (#28) -------------------------------------------

def _pr_state(tmp_path: Path, job: str, responses: list[str]):
    fake = (
        "responses = json.loads(os.environ['GH_RESPONSES'])\n"
        "call_number = len(open(os.environ['GH_CALLS']).read().splitlines())\n"
        "state = responses[call_number - 1]\n"
        "if state == 'ERROR': sys.exit(1)\n"
        "print(state)\n"
    )
    env = _fake_gh(tmp_path, fake) | {"PR": "23", "GH_RESPONSES": json.dumps(responses)}
    # The workflow waits between API attempts; the test only needs to observe
    # that it makes the second call.
    sleep = tmp_path / "bin" / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o755)
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"][job]["steps"]
    assert steps[0]["id"] == "pr-state"
    return _run(tmp_path, _step(job, "pr-state"), env, tmp_path)


@pytest.mark.parametrize("job", ["review", "fix"])
@pytest.mark.parametrize("state,expected_rc", [("OPEN", 0), ("MERGED", 1), ("CLOSED", 1)])
def test_pr_state_is_reported_before_checkout(tmp_path: Path, job: str, state: str, expected_rc: int) -> None:
    proc, calls, _ = _pr_state(tmp_path, job, [state])
    assert proc.returncode == expected_rc, proc.stdout + proc.stderr
    assert f"PR #23 is {state}" in proc.stdout
    assert ("::error" in proc.stdout) == (state != "OPEN")
    assert calls == [["pr", "view", "23", "--repo", "example/repo", "--json", "state", "--jq", ".state"]]


@pytest.mark.parametrize("job", ["review", "fix"])
def test_pr_state_retries_api_failure_once(tmp_path: Path, job: str) -> None:
    proc, calls, _ = _pr_state(tmp_path, job, ["ERROR", "OPEN"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PR #23 is OPEN" in proc.stdout
    assert len(calls) == 2


@pytest.mark.parametrize("job", ["review", "fix"])
def test_pr_state_fails_when_both_api_attempts_fail(tmp_path: Path, job: str) -> None:
    proc, calls, _ = _pr_state(tmp_path, job, ["ERROR", "ERROR"])
    assert proc.returncode == 1
    assert "Could not determine the state of PR #23" in proc.stdout
    assert len(calls) == 2


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


def test_blocking_issue_keeps_fenced_examples_inside_the_report(tmp_path: Path) -> None:
    review = "BLOCKING\n- a.py:1 replace with:\n```py\nvalue = 1\n```\n\nSUMMARY: 1 BLOCKING, 0 WARNING, 0 NIT"
    comments = [_comment(review, "2026-09-13T20:43:14Z", "https://example/current")]
    proc, calls, _ = _blocking(tmp_path, comments, [], since="2026-09-13T20:30:00Z")
    assert proc.returncode == 0, proc.stderr
    created = next(c for c in calls if c[:2] == ["issue", "create"])
    body = created[created.index("--body") + 1]
    assert "\n    BLOCKING\n    - a.py:1 replace with:\n    ```py\n    value = 1\n    ```\n" in body
    assert "Triage: `/oc <request>` on PR #1609" in body


def test_blocking_reopens_the_closed_issue_of_the_same_pr(tmp_path: Path) -> None:
    comments = [_comment(BLOCKING_REVIEW, "2026-09-13T20:43:14Z", "https://example/current")]
    issues = [{"number": 7, "title": "review-blocking: PR #1609 with BLOCKING in review", "state": "closed"},
              {"number": 8, "title": "review-blocking: PR #16090 with BLOCKING in review", "state": "open"}]
    proc, calls, _ = _blocking(tmp_path, comments, issues, since="2026-09-13T20:30:00Z")
    assert proc.returncode == 0, proc.stderr
    assert ["issue", "reopen", "7"] in calls
    assert any(c[:3] == ["issue", "comment", "7"] for c in calls)
    assert not any(c[:2] == ["issue", "create"] for c in calls)


def test_usage_footer_selects_the_marked_translated_review(tmp_path: Path) -> None:
    review_body = "BLOCKING\n  (none)\n\n**RESUMO**: 0 BLOQUEIO, 1 AVISO, 0 NIT"
    comments = [
        _comment("SUMMARY: 1 BLOCKING", "2026-09-13T20:02:20Z", "https://example/old") | {"id": 40},
        _comment(review_body, "2026-09-13T20:43:14Z", "https://example/review") | {"id": 42},
        _comment("The word SUMMARY: appears in this fix log", "2026-09-13T20:44:00Z", "https://example/fix") | {"id": 43},
    ]
    fake = (
        "comments = json.loads(os.environ['GH_COMMENTS'])\n"
        "if '--paginate' in args: print(json.dumps(comments))\n"
        "elif '--jq' in args:\n"
        "    cid = int(args[1].rsplit('/', 1)[-1])\n"
        "    print(next(c['body'] for c in comments if c['id'] == cid))\n"
    )
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".gh-agents").symlink_to(ROOT)
    env = _fake_gh(tmp_path, fake) | {
        "GH_COMMENTS": json.dumps(comments), "PR": "1609", "STARTED": "1",
        "SINCE": "2026-09-13T20:30:00Z",
    }
    opencode = tmp_path / "bin" / "opencode"
    opencode.write_text("#!/bin/sh\nprintf '[]\\n'\n")
    opencode.chmod(0o755)
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["review"]["steps"]
    script = next(s["run"] for s in steps if s.get("name") == "Annotate review comment with usage")
    proc, calls, _ = _run(tmp_path, script, env, workspace)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    patches = [c for c in calls if c[:3] == ["api", "-X", "PATCH"]]
    assert len(patches) == 1
    assert patches[0][3] == "repos/example/repo/issues/comments/42"
    assert any(review_body in arg and "<sub>review by" in arg for arg in patches[0])


# --- the session ran as the pinned agent (#25) --------------------------------

def _agent_check(tmp_path: Path, job: str, sessions: list[dict], agents_by_session: dict):
    """Fake `opencode`: `session list` answers `sessions`, `export <id>` answers
    messages carrying the agent recorded for that session."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".gh-agents").symlink_to(ROOT)
    for s in sessions:
        s.setdefault("directory", str(workspace))
    opencode = tmp_path / "bin" / "opencode"
    opencode.parent.mkdir(exist_ok=True)
    opencode.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"sessions = {sessions!r}\n"
        f"agents = {agents_by_session!r}\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['session', 'list']:\n"
        "    print(json.dumps(sessions))\n"
        "elif args[0] == 'export':\n"
        "    msgs = [{'info': {'role': 'assistant', 'agent': a}} for a in agents[args[1]]]\n"
        "    print(json.dumps({'messages': msgs}))\n"
    )
    opencode.chmod(0o755)
    env = _literal_env(job, "agent-check") | {"PATH": f"{opencode.parent}:{os.environ['PATH']}", "STARTED": "1000"}
    return _run(tmp_path, _step(job, "agent-check"), env, workspace)


def test_agent_check_fails_the_review_that_ran_as_build(tmp_path: Path) -> None:
    proc, _, _ = _agent_check(tmp_path, "review", [{"id": "root", "created": 1_000_500}],
                              {"root": ["build", "build"]})
    assert proc.returncode == 1
    assert "::error" in proc.stdout and "build" in proc.stdout


def test_agent_check_passes_the_review_that_ran_as_reviewer(tmp_path: Path) -> None:
    proc, _, _ = _agent_check(tmp_path, "review", [{"id": "root", "created": 1_000_500}],
                              {"root": ["reviewer"]})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "::warning" not in proc.stdout and "ran as 'reviewer'" in proc.stdout


def test_agent_check_reads_the_root_session_not_a_newer_subagent_one(tmp_path: Path) -> None:
    # the reviewer spawns `general` subagents: child sessions, created later
    sessions = [{"id": "child", "parentID": "root", "created": 1_000_900},
                {"id": "root", "created": 1_000_500},
                {"id": "stale", "created": 999_000}]
    proc, _, _ = _agent_check(tmp_path, "review", sessions,
                              {"root": ["reviewer"], "child": ["general"], "stale": ["build"]})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "::warning" not in proc.stdout and "ran as 'reviewer'" in proc.stdout


def test_agent_check_fails_the_fix_that_ran_as_build(tmp_path: Path) -> None:
    proc, _, _ = _agent_check(tmp_path, "fix", [{"id": "root", "created": 1_000_500}],
                              {"root": ["build"]})
    assert proc.returncode == 1


def test_agent_check_without_a_session_warns_instead_of_passing_silently(tmp_path: Path) -> None:
    proc, _, _ = _agent_check(tmp_path, "review", [], {})
    assert proc.returncode == 0
    assert "::warning" in proc.stdout


# --- ChatGPT login (vars.AGENT_OPENCODE_AUTH) ---------------------------------

def _step_by_name(job: str, name: str) -> str:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"][job]["steps"]
    return next(s for s in steps if s.get("name") == name)["run"]


def _login_env(tmp_path: Path, host_auth: Path) -> dict:
    # the job copies .gh-agents/scripts from the gh-agents checkout
    (tmp_path / ".gh-agents").symlink_to(ROOT)
    home = tmp_path / "home"
    home.mkdir()
    return {"HOME": str(home), "XDG_DATA_HOME": "", "HOST_AUTH": str(host_auth),
            "OPENCODE_API_KEY": "", "FIREWORKS_API_KEY": ""}


@pytest.mark.parametrize("job", ["review", "fix", "ci-doctor"])
def test_openai_model_runs_on_the_loaded_chatgpt_login(tmp_path: Path, job: str) -> None:
    host_auth = tmp_path / "host-auth.json"
    host_auth.write_text(json.dumps({"openai": {"type": "oauth", "refresh": "r", "access": "a", "expires": 1}}))
    env = _login_env(tmp_path, host_auth) | {"MODEL": "openai/gpt-5.5"}

    load, _, _ = _run(tmp_path, _step(job, "auth"), env, tmp_path)
    assert load.returncode == 0, load.stdout + load.stderr
    preflight, _, _ = _run(tmp_path, _step(job, "preflight"), env, tmp_path)
    assert preflight.returncode == 0, preflight.stdout + preflight.stderr


@pytest.mark.parametrize("job", ["review", "fix", "ci-doctor"])
def test_openai_model_without_a_login_fails_naming_the_variable(tmp_path: Path, job: str) -> None:
    env = _login_env(tmp_path, tmp_path / "missing.json") | {"MODEL": "openai/gpt-5.5"}
    proc, _, _ = _run(tmp_path, _step(job, "preflight"), env, tmp_path)
    assert proc.returncode == 1
    assert "AGENT_OPENCODE_AUTH" in proc.stdout


@pytest.mark.parametrize("job", ["review", "fix", "ci-doctor"])
def test_refreshed_login_is_saved_back_to_the_host(tmp_path: Path, job: str) -> None:
    host_auth = tmp_path / "host-auth.json"
    host_auth.write_text(json.dumps({"openai": {"type": "oauth", "refresh": "r1", "access": "a1", "expires": 1}}))
    env = _login_env(tmp_path, host_auth)
    _run(tmp_path, _step(job, "auth"), env, tmp_path)
    job_auth = Path(env["HOME"]) / ".local/share/opencode/auth.json"
    job_auth.write_text(json.dumps({"openai": {"type": "oauth", "refresh": "r2", "access": "a2", "expires": 2}}))

    proc, _, _ = _run(tmp_path, _step_by_name(job, "Save refreshed ChatGPT login"), env, tmp_path)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(host_auth.read_text())["openai"]["refresh"] == "r2"


# --- model#variant (reasoning effort) -----------------------------------------

def _resolve(tmp_path: Path, job: str, model: str) -> tuple[subprocess.CompletedProcess, str]:
    # a fake opencode that answers every probe: the step only parses the id
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # opencode v1 (what CI runs) rejects `#variant` in --model: it takes --variant
    (bin_dir / "opencode").write_text(
        "#!/bin/sh\n"
        "echo \"$*\" >> \"$OPENCODE_CALLS\"\n"
        "case \"$*\" in *'#'*) exit 1 ;; esac\n"
        "echo ok\n")
    (bin_dir / "opencode").chmod(0o755)
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "MODEL": model, "FALLBACKS": "",
           "OPENCODE_CALLS": str(tmp_path / "opencode_calls")}
    proc, _, output = _run(tmp_path, _step(job, "model"), env, tmp_path)
    return proc, output


@pytest.mark.parametrize("job", ["review", "fix", "ci-doctor"])
def test_probe_passes_the_variant_as_a_flag(tmp_path: Path, job: str) -> None:
    proc, _ = _resolve(tmp_path, job, "openai/gpt-6-luna-fast#xhigh")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    call = (tmp_path / "opencode_calls").read_text()
    assert "--model openai/gpt-6-luna-fast --variant xhigh" in call


def test_ci_doctor_runs_the_model_and_variant_apart() -> None:
    step = next(s for s in yaml.safe_load(WORKFLOW.read_text())["jobs"]["ci-doctor"]["steps"]
                if s.get("name") == "Diagnose failed run")
    assert step["env"]["MODEL"] == "${{ steps.model.outputs.base }}"
    assert step["env"]["VARIANT"] == "${{ steps.model.outputs.variant }}"
    assert '${VARIANT:+--variant "$VARIANT"}' in step["run"]


@pytest.mark.parametrize("job", ["review", "fix", "ci-doctor"])
def test_model_variant_is_split_for_the_opencode_action(tmp_path: Path, job: str) -> None:
    proc, output = _resolve(tmp_path, job, "openai/gpt-6-luna-fast#xhigh")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "model=openai/gpt-6-luna-fast#xhigh\n" in output
    assert "base=openai/gpt-6-luna-fast\n" in output
    assert "variant=xhigh\n" in output


@pytest.mark.parametrize("job", ["review", "fix", "ci-doctor"])
def test_model_without_variant_passes_no_variant(tmp_path: Path, job: str) -> None:
    proc, output = _resolve(tmp_path, job, "opencode-go/glm-5.3-flash")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "base=opencode-go/glm-5.3-flash\n" in output
    assert "variant=" not in output


@pytest.mark.parametrize("job,step_id", [("fix", "fix")])
def test_opencode_action_gets_the_model_and_variant_apart(job: str, step_id: str) -> None:
    # the action's MODEL must be provider/model; the effort is its `variant` input
    with_ = _step_def(job, step_id)["with"]
    assert with_["model"] == "${{ steps.model.outputs.base }}"
    assert with_["variant"] == "${{ steps.model.outputs.variant }}"


# --- manual review: `/oc review` (2026-09-28) ---------------------------------

def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]


def test_no_job_reviews_on_its_own() -> None:
    # reviews are manual: a push or an opened PR never starts one
    jobs = _jobs()
    assert "gate" not in jobs
    assert "pull_request'" not in jobs["review"]["if"].replace("pull_request_review_comment'", "")
    assert "/oc review" in jobs["review"]["if"] and "/opencode review" in jobs["review"]["if"]


def test_review_is_open_to_any_human_in_private_repos_only() -> None:
    gate = _jobs()["review"]["if"]
    assert "github.event.comment.user.type != 'Bot'" in gate
    assert "github.event.repository.private" in gate
    assert "author_association" in gate  # public repos keep the collaborator gate


def test_oc_review_never_starts_the_fixer() -> None:
    gate = _jobs()["fix"]["if"]
    assert "!contains(github.event.comment.body, '/oc review')" in gate
    assert "!contains(github.event.comment.body, '/opencode review')" in gate
    assert "author_association" in gate  # the fixer pushes: collaborators only


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          cwd=cwd, check=True, capture_output=True, text=True).stdout


def _pr_checkout(tmp_path: Path, base_files: dict, pr_files: dict) -> Path:
    """A clone whose HEAD is the PR and whose origin/main is the base."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    for name, text in base_files.items():
        (origin / name).parent.mkdir(parents=True, exist_ok=True)
        (origin / name).write_text(text)
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "--allow-empty", "-m", "base")
    _git(origin, "checkout", "-q", "-b", "pr")
    for name, text in pr_files.items():
        (origin / name).parent.mkdir(parents=True, exist_ok=True)
        (origin / name).write_text(text)
    _git(origin, "add", "-A")
    _git(origin, "commit", "-q", "-m", "pr")
    work = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    _git(work, "checkout", "-q", "pr")
    (work / ".gh-agents").symlink_to(ROOT)
    return work


def test_review_config_comes_from_the_base_branch_never_the_pr(tmp_path: Path) -> None:
    # a PR could otherwise widen the reviewer's permissions or load a plugin
    # while the job holds the provider keys and the ChatGPT login
    work = _pr_checkout(
        tmp_path,
        {"opencode.json": '{"base": true}'},
        {"opencode.json": '{"agent": {"reviewer": {"permission": {"bash": "allow"}}}}',
         ".opencode/plugin/evil.ts": "steal()", "src/app.py": "print(1)"})
    proc, _, _ = _run(tmp_path, _step("review", "config"), {"BASE": "main"}, work)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads((work / "opencode.json").read_text()) == {"base": True}
    assert not (work / ".opencode").exists()
    assert (work / "src/app.py").read_text() == "print(1)"  # the code under review stays


def test_review_config_falls_back_to_gh_agents_defaults(tmp_path: Path) -> None:
    work = _pr_checkout(tmp_path, {"README.md": "x"}, {"opencode.json": '{"pr": true}'})
    proc, _, _ = _run(tmp_path, _step("review", "config"), {"BASE": "main"}, work)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (work / "opencode.json").read_text() == (ROOT / "agents/opencode.json").read_text()
    assert "/opencode.json" in (work / ".git/info/exclude").read_text()


def _fake_opencode(tmp_path: Path, events: list[dict]) -> dict:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    out = "".join(json.dumps(e) + "\n" for e in events)
    (bin_dir / "opencode").write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$OPENCODE_CALLS"\n'
        f"cat <<'EOF'\n{out}EOF\n")
    (bin_dir / "opencode").chmod(0o755)
    return {"OPENCODE_CALLS": str(tmp_path / "opencode_calls")}


def test_review_runs_the_reviewer_and_posts_its_final_message(tmp_path: Path) -> None:
    review = "BLOCKING\n(none)\n\nSUMMARY: 0 BLOCKING, 0 WARNING, 0 NIT"
    env = _fake_gh(tmp_path, "") | _fake_opencode(tmp_path, [
        {"type": "text", "part": {"type": "text", "text": "Reading the diff.", "messageID": "m1"}},
        {"type": "text", "part": {"type": "text", "text": review, "messageID": "m2"}},
    ]) | {"PR": "23", "MODEL": "openai/gpt-6-luna-fast", "VARIANT": "xhigh"}
    (tmp_path / ".gh-agents").symlink_to(ROOT)
    proc, calls, _ = _run(tmp_path, _step("review", "review"), env, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    call = (tmp_path / "opencode_calls").read_text()
    assert "--pure" in call and "--agent reviewer" in call and "--format json" in call
    assert "--model openai/gpt-6-luna-fast --variant xhigh" in call
    comment = next(c for c in calls if c[:2] == ["pr", "comment"])
    assert comment[2] == "23"
    posted = Path(comment[comment.index("--body-file") + 1]).read_text()
    assert posted.strip() == review


def test_review_that_failed_posts_nothing(tmp_path: Path) -> None:
    env = _fake_gh(tmp_path, "") | _fake_opencode(tmp_path, [
        {"type": "error", "error": {"name": "APIError", "data": {"message": "Insufficient account funds"}}},
    ]) | {"PR": "23", "MODEL": "opencode-go/glm-5.3-flash", "VARIANT": ""}
    (tmp_path / ".gh-agents").symlink_to(ROOT)
    proc, calls, _ = _run(tmp_path, _step("review", "review"), env, tmp_path)
    assert proc.returncode == 1
    assert "Insufficient account funds" in proc.stdout + proc.stderr
    assert not any(c[:2] == ["pr", "comment"] for c in calls)
