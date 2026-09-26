#!/usr/bin/env python3
"""Read the reviewer's comment (stdin) and emit JSON: BLOCKING count and block.

Usage: python3 scripts/review_blocking.py < comment.md
       python3 scripts/review_blocking.py --comments [--since ISO] < comments.json
Output: {"blocking": N, "block": "<BLOCKING block text or empty>"}
        with --comments, also "url" and "summary": "ok" | "missing"

The count comes from the `SUMMARY: N BLOCKING, ...` line — the reviewer writes
`BLOCKING\n  (none)` when it is zero, so the block cannot serve as the count.
No SUMMARY (off-format review) -> 0 plus a stderr warning; exit is always 0,
the open-issue decision belongs to the YAML (.github/workflows/agents.yml).
With --comments, `summary: missing` tells the YAML the count is unknown,
not zero.

`--since` limits the search to comments from the current run. Without the
cutoff an off-format review on a new SHA fell back to the previous SHA's
review, and the step reported the stale count against the new SHA
(intrador #1415).

`blocking_count` is importable; do not copy the regex into callers.
"""

import argparse
import json
import re
import sys
from datetime import datetime

_SUMMARY = re.compile(r"^SUMMARY:\s*(\d+)\s+BLOCKING", re.MULTILINE)
_BOT_LOGIN = "github-actions[bot]"


def blocking_count(text: str) -> int | None:
    """N from the SUMMARY line; None when the comment has no such line."""
    match = _SUMMARY.search(text)
    return int(match.group(1)) if match else None


def latest_review(comments: list[dict], since: datetime | None = None) -> dict | None:
    """Latest valid-SUMMARY comment from the bot at or after `since`,
    regardless of page order."""
    reviews = [
        (datetime.fromisoformat(c["created_at"]), c)
        for c in comments
        if c["user"]["login"] == _BOT_LOGIN and blocking_count(c["body"]) is not None
    ]
    in_window = [(at, c) for at, c in reviews if since is None or at >= since]
    return max(in_window, key=lambda pair: pair[0])[1] if in_window else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--comments", action="store_true",
                        help="stdin: JSON array of comments; includes url in output")
    parser.add_argument("--since", type=datetime.fromisoformat,
                        help="with --comments: ignore comments created before this (ISO 8601)")
    args = parser.parse_args()
    review = latest_review(json.load(sys.stdin) or [], args.since) if args.comments else None
    text = (review or {}).get("body", "") if args.comments else sys.stdin.read()
    blocking = blocking_count(text)
    if blocking is None:
        print("review_blocking: SUMMARY line absent; treating as 0 BLOCKING", file=sys.stderr)
        blocking = 0
    block = re.search(r"^BLOCKING\n(.*?)(?=^(?:WARNING|NIT|SUMMARY)\b|\Z)",
                      text, re.MULTILINE | re.DOTALL)
    out = {"blocking": blocking, "block": block.group(1).strip("\n") if block and blocking else ""}
    if args.comments:
        out["url"] = (review or {}).get("html_url", "")
        out["summary"] = "ok" if review else "missing"
    print(json.dumps(out))
