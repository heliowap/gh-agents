"""Keep the distributed caller template aligned with this repo's dogfood caller."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_caller_concurrency_matches_dogfood() -> None:
    dogfood = yaml.safe_load((ROOT / ".github/workflows/dogfood.yml").read_text())
    template = yaml.safe_load((ROOT / "templates/caller-agents.yml").read_text())
    assert template["jobs"]["agents"]["concurrency"] == dogfood["jobs"]["agents"]["concurrency"]
