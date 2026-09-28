"""Keep caller and reusable-workflow gates and concurrency policies aligned."""

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_trusted_issue_comments_reach_the_callee() -> None:
    for path in (".github/workflows/dogfood.yml", "templates/caller-agents.yml"):
        caller = yaml.safe_load((ROOT / path).read_text())
        gate = caller["jobs"]["agents"]["if"]
        assert "(github.event_name == 'issue_comment' && github.event.issue.pull_request)" not in gate


def test_caller_and_callee_gates_and_concurrency_stay_aligned() -> None:
    dogfood = yaml.safe_load((ROOT / ".github/workflows/dogfood.yml").read_text())
    template = yaml.safe_load((ROOT / "templates/caller-agents.yml").read_text())
    callee = yaml.safe_load((ROOT / ".github/workflows/agents.yml").read_text())
    assert template["jobs"]["agents"]["if"] == dogfood["jobs"]["agents"]["if"]
    caller_group = dogfood["jobs"]["agents"]["concurrency"]
    assert template["jobs"]["agents"]["concurrency"] == caller_group
    assert callee["concurrency"]["group"] == caller_group["group"].replace(
        "gh-agents-", "gh-agents-callee-", 1
    )
    assert callee["concurrency"]["cancel-in-progress"] == caller_group["cancel-in-progress"]
    event_equals = r"github\.event_name\s*==\s*'([^']+)'"
    lane_events = set(re.findall(event_equals, caller_group["group"]))
    fixer_events = set(re.findall(event_equals, callee["jobs"]["fix"]["if"]))
    review_events = set(re.findall(event_equals, callee["jobs"]["review"]["if"]))
    caller_events = set(re.findall(event_equals, dogfood["jobs"]["agents"]["if"]))
    assert lane_events
    assert lane_events == fixer_events == review_events
    # reviews are manual (`/oc review`): no caller listens to pull_request
    assert caller_events == lane_events | {"workflow_run"}
    # Issue fixes are an explicit opt-in: default callers still handle PRs only.
    assert callee.get("on", callee.get(True))["workflow_call"]["inputs"]["allow_issue_fix"]["default"] is False
    fix_gate = callee["jobs"]["fix"]["if"]
    assert "inputs.allow_issue_fix" in fix_gate
    assert "github.event.issue.pull_request != null" in fix_gate
    pr_check = next(step for step in callee["jobs"]["fix"]["steps"] if step.get("id") == "pr-state")
    assert "github.event.issue.pull_request != null" in pr_check["if"]
    # a caller must let `/oc review` through wherever the callee accepts it
    for caller in (dogfood, template):
        gate = caller["jobs"]["agents"]["if"]
        assert "github.event.repository.private" in gate and "/oc review" in gate
    # PyYAML's YAML 1.1 loader reads the Actions `on` key as True.
    for caller in (dogfood, template):
        assert set(caller.get("on", caller.get(True, {}))) == caller_events
