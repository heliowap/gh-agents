"""The model list can continue when the ChatGPT login is unavailable."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_preflight import available_models


def test_missing_login_uses_fireworks_fallback(tmp_path: Path) -> None:
    assert available_models(
        "openai/gpt-6-luna-fast#xhigh",
        "fireworks-ai/accounts/fireworks/models/glm-5p3-flash",
        tmp_path / "missing.json",
        {"FIREWORKS_API_KEY": "test-key"},
    ) == ["fireworks-ai/accounts/fireworks/models/glm-5p3-flash"]


def test_invalid_login_without_fallback_credentials_fails(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"openai": {"type": "api"}}))
    assert available_models("openai/gpt-6-luna-fast", "fireworks-ai/glm", auth, {}) == []


def test_valid_login_still_selects_primary(tmp_path: Path) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"openai": {"type": "oauth"}}))
    assert available_models("openai/gpt-6-luna-fast", "", auth, {}) == ["openai/gpt-6-luna-fast"]
