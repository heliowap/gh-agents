"""Keep the distributed caller template aligned with this repo's dogfood caller."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_caller_concurrency_matches_dogfood() -> None:
    dogfood = yaml.safe_load((ROOT / ".github/workflows/dogfood.yml").read_text())
    template = yaml.safe_load((ROOT / "templates/caller-agents.yml").read_text())
    callee = yaml.safe_load((ROOT / ".github/workflows/agents.yml").read_text())
    caller_group = dogfood["jobs"]["agents"]["concurrency"]
    assert template["jobs"]["agents"]["concurrency"] == caller_group
    assert callee["concurrency"]["group"] == caller_group["group"].replace(
        "gh-agents-", "gh-agents-callee-", 1
    )
    assert callee["concurrency"]["cancel-in-progress"] == caller_group["cancel-in-progress"]
