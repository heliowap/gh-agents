"""Keep caller and reusable-workflow gates and concurrency policies aligned."""

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


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
    caller_events = set(re.findall(event_equals, dogfood["jobs"]["agents"]["if"]))
    assert lane_events
    assert lane_events == fixer_events
    assert caller_events == lane_events | {"pull_request", "workflow_run"}
    # PyYAML's YAML 1.1 loader reads the Actions `on` key as True.
    for caller in (dogfood, template):
        assert set(caller.get("on", caller.get(True, {}))) == caller_events
