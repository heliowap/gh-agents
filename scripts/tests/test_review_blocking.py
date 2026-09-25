"""Seam: the module's public functions + the CLI contract the workflow parses."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from review_blocking import blocking_count, latest_review

SCRIPT = Path(__file__).resolve().parents[1] / "review_blocking.py"


def _comment(login, body, created="2026-09-24T10:00:00Z", url="https://example/c/1"):
    return {"user": {"login": login}, "body": body, "created_at": created, "html_url": url}


def test_blocking_count_reads_summary():
    assert blocking_count("BLOCKING\n- x\nSUMMARY: 2 BLOCKING, 1 WARNING, 0 NIT") == 2


def test_blocking_count_none_without_summary():
    assert blocking_count("looks fine") is None


def test_latest_review_picks_latest_bot_comment_with_summary():
    older = _comment("github-actions[bot]", "SUMMARY: 3 BLOCKING, 0 WARNING, 0 NIT",
                     created="2026-09-24T09:00:00Z")
    newer = _comment("github-actions[bot]", "SUMMARY: 0 BLOCKING, 0 WARNING, 0 NIT",
                     created="2026-09-24T11:00:00Z")
    human = _comment("heliowap", "SUMMARY: 9 BLOCKING, 0 WARNING, 0 NIT",
                     created="2026-09-24T12:00:00Z")
    assert latest_review([newer, human, older]) is newer


def test_latest_review_empty():
    assert latest_review([]) is None
    assert latest_review([_comment("heliowap", "hi")]) is None


def test_cli_comments_outputs_url_and_block():
    body = "BLOCKING\n- foo.py:10 bad\n\nWARNING\n  (nenhum)\n\nSUMMARY: 1 BLOCKING, 0 WARNING, 0 NIT"
    comments = json.dumps([_comment("github-actions[bot]", body, url="https://example/c/9")])
    out = subprocess.run([sys.executable, str(SCRIPT), "--comments"],
                         input=comments, capture_output=True, text=True)
    assert out.returncode == 0
    data = json.loads(out.stdout)
    assert data["blocking"] == 1 and data["url"] == "https://example/c/9"
    assert "foo.py:10" in data["block"]


def test_cli_missing_summary_exits_zero_with_warning():
    out = subprocess.run([sys.executable, str(SCRIPT)],
                         input="no summary here", capture_output=True, text=True)
    assert out.returncode == 0
    assert json.loads(out.stdout)["blocking"] == 0
    assert "SUMMARY" in out.stderr
