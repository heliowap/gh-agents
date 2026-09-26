"""Seam: `python3 scripts/session_agent.py --expect NAME < export.json` → exit code.

The export shape follows `opencode export <session>` as the annotate step reads
it (`messages[].info`); the agent field is the one the CLI logs per LLM call
(`agent: "build"` in the stream log of intrador run 36227639420).
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "session_agent.py"


def _export(*agents):
    return {"info": {"id": "ses_1"},
            "messages": [{"info": {"role": role, "agent": agent}, "parts": []}
                         for agent in agents for role in ("user", "assistant")]}


def _run(export, expect="reviewer"):
    return subprocess.run([sys.executable, str(SCRIPT), "--expect", expect],
                          input=json.dumps(export), capture_output=True, text=True)


def test_session_that_ran_as_the_expected_agent_passes():
    proc = _run(_export("reviewer", "reviewer"))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_session_that_fell_back_to_build_fails_naming_the_agent():
    # heliowap/gh-agents#25: `agent: reviewer` ignored, every call ran as build
    proc = _run(_export("build", "build"))
    assert proc.returncode == 1
    assert "build" in proc.stdout and "reviewer" in proc.stdout


def test_one_message_off_agent_is_enough_to_fail():
    proc = _run(_export("reviewer", "build"))
    assert proc.returncode == 1


def test_export_without_agent_field_is_unverifiable_not_a_pass():
    export = {"messages": [{"info": {"role": "assistant"}, "parts": []}]}
    proc = _run(export)
    assert proc.returncode == 2
    assert "cannot verify" in proc.stdout


def test_unreadable_export_is_unverifiable_not_a_crash():
    proc = subprocess.run([sys.executable, str(SCRIPT), "--expect", "fixer"],
                          input="not json", capture_output=True, text=True)
    assert proc.returncode == 2
