"""Seam: `opencode run --format json … | python3 scripts/review_text.py` → stdout + exit code.

Event shapes as opencode v1.18.32 prints them (captured in the runtime image):
`step_start`, `tool_use`, `text` (`part.text`, `part.messageID`), `step_finish`,
and `error` (`error.data.message`) when the provider call fails.
"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "review_text.py"


def _text(msg, text):
    return {"type": "text", "part": {"type": "text", "text": text, "messageID": msg}}


def _tool(msg):
    return {"type": "tool_use", "part": {"type": "tool", "tool": "bash", "messageID": msg}}


def _run(*events, raw=""):
    stdin = raw or "".join(json.dumps(e) + "\n" for e in events)
    return subprocess.run([sys.executable, str(SCRIPT)], input=stdin,
                          capture_output=True, text=True)


def test_prints_the_final_message_not_the_narration_before_tools():
    proc = _run(_text("m1", "Let me read the diff."), _tool("m1"),
                _text("m2", "BLOCKING\n(none)"), _text("m2", "SUMMARY: 0 BLOCKING, 0 WARNING, 0 NIT"))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "BLOCKING\n(none)\nSUMMARY: 0 BLOCKING, 0 WARNING, 0 NIT\n"


def test_provider_error_fails_with_its_message():
    err = {"type": "error", "error": {"name": "APIError",
                                      "data": {"message": "Insufficient account funds"}}}
    proc = _run(err)
    assert proc.returncode == 1
    assert "Insufficient account funds" in proc.stderr
    assert proc.stdout == ""


def test_a_run_that_said_nothing_fails():
    proc = _run(_tool("m1"))
    assert proc.returncode == 1
    assert "no review text" in proc.stderr


def test_non_json_lines_are_skipped():
    # the CLI may interleave a plain warning line on stdout
    proc = _run(raw="warning: something\n" + json.dumps(_text("m1", "ok")) + "\n")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "ok\n"
