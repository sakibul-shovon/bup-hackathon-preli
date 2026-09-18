"""Environment configuration for GridWise (plan Section 4). Read once at import time."""
import os

EMIT_DP = 8
REPLAY_EPS = 1e-6


def _parse_keys(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


GROQ_API_KEYS: list[str] = _parse_keys(os.environ.get("GROQ_API_KEYS"))
if not GROQ_API_KEYS:
    GROQ_API_KEYS = _parse_keys(os.environ.get("GROQ_API_KEY"))

PORT = int(os.environ.get("PORT", "8000"))
PRIMARY_MODEL = os.environ.get("PRIMARY_MODEL", "openai/gpt-oss-20b")
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "openai/gpt-oss-120b")
LLM_TIMEOUT_PRIMARY = float(os.environ.get("LLM_TIMEOUT_PRIMARY", "6.0"))
LLM_TIMEOUT_FALLBACK = float(os.environ.get("LLM_TIMEOUT_FALLBACK", "8.0"))
LLM_DEADLINE_SECONDS = float(os.environ.get("LLM_DEADLINE_SECONDS", "20.0"))
PROMPT_COMPACT = os.environ.get("PROMPT_COMPACT", "0") == "1"

ALT_BASE_URL = os.environ.get("ALT_BASE_URL") or None
ALT_API_KEY = os.environ.get("ALT_API_KEY") or None
ALT_MODEL = os.environ.get("ALT_MODEL") or None
