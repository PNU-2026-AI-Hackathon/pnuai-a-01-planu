"""Small OpenAI Chat Completions client helpers for PlaNU parsers."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
OPENAI_API_KEY_PLACEHOLDER = "여기에 OpenAI API 키 입력"
OPENAI_API_KEY_PLACEHOLDERS = {
    OPENAI_API_KEY_PLACEHOLDER,
    "여기에 api key 입력",
    "여기에 토큰 입력",
}


def load_openai_env() -> None:
    """Load OpenAI settings from backend/.env or root .env if present."""

    for path in _candidate_env_paths():
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def _candidate_env_paths() -> list[Path]:
    cwd = Path.cwd()
    module_root = Path(__file__).resolve().parents[3]
    candidates = [
        module_root / "backend" / ".env",
        cwd / ".env",
        module_root / ".env",
    ]
    unique: list[Path] = []
    for path in candidates:
        if path not in unique:
            unique.append(path)
    return unique


def has_openai_api_key(value: str | None) -> bool:
    """Return whether an OPENAI_API_KEY value looks usable."""

    if not value:
        return False
    return value.strip() not in OPENAI_API_KEY_PLACEHOLDERS


def normalize_openai_model_name(value: str) -> str:
    """Normalize legacy proxy-style OpenAI model slugs for the official API."""

    model = value.strip()
    if model.startswith("openai/"):
        return model.removeprefix("openai/")
    return model


def chat_completions_url(base_url: str | None = None) -> str:
    """Return the OpenAI Chat Completions endpoint URL."""

    stripped = (base_url or DEFAULT_OPENAI_BASE_URL).rstrip("/")
    if stripped.endswith("/chat/completions"):
        return stripped
    return f"{stripped}/chat/completions"


def request_chat_completions(
    payload: dict[str, Any],
    *,
    api_key: str | None,
    base_url: str | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """POST a Chat Completions request and return the decoded response JSON."""

    if not has_openai_api_key(api_key):
        raise RuntimeError("OPENAI_API_KEY is not configured")

    request = urllib.request.Request(
        chat_completions_url(base_url),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except TimeoutError:
        raise
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API returned HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", "unknown")
        if isinstance(reason, TimeoutError):
            raise reason
        raise RuntimeError(f"OpenAI API request failed: {reason}") from exc
