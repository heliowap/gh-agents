"""Fail early only when no requested OpenCode model has usable credentials."""

import json
import os
from pathlib import Path


def has_openai_login(path: Path) -> bool:
    try:
        auth = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    return isinstance(auth, dict) and isinstance(auth.get("openai"), dict) and auth["openai"].get("type") == "oauth"


def available_models(model: str, fallbacks: str, auth_path: Path, keys: dict[str, str]) -> list[str]:
    candidates = [part.strip() for part in f"{model},{fallbacks}".split(",") if part.strip()]
    available = []
    for candidate in candidates:
        provider = candidate.split("/", 1)[0]
        if provider == "openai":
            ready = has_openai_login(auth_path)
        elif provider.startswith("fireworks"):
            ready = bool(keys.get("FIREWORKS_API_KEY"))
        else:
            ready = bool(keys.get("OPENCODE_API_KEY"))
        if ready:
            available.append(candidate)
    return available


if __name__ == "__main__":
    auth = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "opencode/auth.json"
    available = available_models(
        os.environ.get("MODEL", ""),
        os.environ.get("FALLBACKS", ""),
        auth,
        {name: os.environ.get(name, "") for name in ("OPENCODE_API_KEY", "FIREWORKS_API_KEY")},
    )
    if not available:
        print("::error::No requested model has credentials. Set the provider secret or ChatGPT login (vars.AGENT_OPENCODE_AUTH; README onboarding step 2).")
        raise SystemExit(1)
    print(f"Credentials available for {', '.join(available)}")
