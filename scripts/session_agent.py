#!/usr/bin/env python3
"""Check that an opencode session ran as the expected agent.

Usage: opencode export <session> | python3 scripts/session_agent.py --expect reviewer
Exit:  0 every message ran as the expected agent
       1 some message ran as another agent (named on stdout)
       2 cannot verify — export unreadable or without an agent field

`opencode github run` ignores the action's `agent:` input and falls back to
the config's `default_agent`, then to `build` (heliowap/gh-agents#25). The
workflow pins the agent through OPENCODE_CONFIG_CONTENT; this check proves,
from the session itself, that the pin held — the action installs the latest
CLI on every run, so a release that drops the pin must fail loudly.
"""

import argparse
import json
import sys


def session_agents(export: dict) -> set[str]:
    """Agent names recorded on the session's messages."""
    return {
        m["info"]["agent"]
        for m in export.get("messages") or []
        if isinstance(m, dict) and isinstance(m.get("info"), dict) and m["info"].get("agent")
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--expect", required=True, help="agent the session must have run as")
    args = parser.parse_args()
    try:
        agents = session_agents(json.load(sys.stdin))
    except (ValueError, AttributeError):
        print("session_agent: cannot verify — export is not a JSON object")
        sys.exit(2)
    if not agents:
        print("session_agent: cannot verify — no agent recorded on the session's messages")
        sys.exit(2)
    if agents != {args.expect}:
        print(f"session_agent: session ran as {sorted(agents)}, expected only {args.expect!r}")
        sys.exit(1)
    print(f"session_agent: session ran as {args.expect!r}")
