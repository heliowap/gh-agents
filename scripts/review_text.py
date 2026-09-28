#!/usr/bin/env python3
"""Extract the review from `opencode run --format json` events.

Usage: opencode run --format json … | python3 scripts/review_text.py > review.md
Exit:  0 review text on stdout
       1 the provider call failed, or the run produced no text (reason on stderr)

The review job runs the reviewer with `opencode run` instead of the opencode
GitHub action: the action requires write permission from whoever triggered
it, and `/oc review` is open to read-only users in private repos. The agent
narrates before its tool calls, so the review is the text of the last message
that has any, joined in order.
"""

import json
import sys


def review_text(lines) -> tuple[str, str]:
    """(review, error) from JSON event lines; exactly one is non-empty."""
    parts: dict[str, list[str]] = {}
    last = ""
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "error":
            error = event.get("error") or {}
            data = error.get("data") if isinstance(error.get("data"), dict) else {}
            return "", data.get("message") or error.get("name") or "opencode reported an error"
        part = event.get("part") if isinstance(event.get("part"), dict) else {}
        if event.get("type") == "text" and part.get("text"):
            msg = part.get("messageID") or ""
            parts.setdefault(msg, []).append(part["text"].strip("\n"))
            last = msg
    if not parts:
        return "", "no review text in the opencode output"
    return "\n".join(parts[last]), ""


if __name__ == "__main__":
    review, error = review_text(sys.stdin)
    if error:
        print(f"review_text: {error}", file=sys.stderr)
        sys.exit(1)
    print(review)
