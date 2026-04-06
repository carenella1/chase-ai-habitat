"""
llm_router.py  —  Two-Brain Architecture

WHY TWO BRAINS?
  Real intelligence uses fast reflexes AND slow deep reasoning separately.
  deepseek-r1:14b  → Chat brain  (fast, ~10-30s, used for all conversation)
  deepseek-r1:32b  → Deep brain  (powerful, ~2-4min, used for background cognition)

  This fixes the timeout/backoff issue: the 32b model was being used for
  live chat, timing out in 90s, failing 3x, then locking Nex out for 2 minutes.
  Now chat always uses the fast 14b, and 32b is reserved for when speed
  doesn't matter (background research, cognition cycles, deep reasoning).

RESULT:
  - Chat responses: fast and reliable again
  - Background cognition: more powerful than ever (32b thinking)
  - Nex gets smarter over time from 32b insights without chat being blocked
"""

import requests
import threading
import time

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

OLLAMA_BASE = "http://localhost:11434"

# CHAT BRAIN — fast, used for live conversation with Chase
# Priority order: first one found installed wins
CHAT_MODEL_PRIORITY = [
    "deepseek-r1:14b",
    "deepseek-r1:7b",
    "llama3.1:8b",
]

# DEEP BRAIN — powerful, used for background cognition only
# Priority order: most powerful first
DEEP_MODEL_PRIORITY = [
    "deepseek-r1:32b",
    "deepseek-r1:14b",  # fallback if 32b not available
]

# Models that output <think>...</think> reasoning blocks
THINKING_MODELS = {
    "deepseek-r1:32b",
    "deepseek-r1:14b",
    "deepseek-r1:7b",
    "deepseek-r1:70b",
}

# Timeouts — chat needs to be fast, deep can take its time
CHAT_TIMEOUT = 120  # 2 minutes max for chat responses
DEEP_TIMEOUT = 300  # 5 minutes allowed for deep cognition

# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────

_chat_model: str | None = None
_deep_model: str | None = None
_model_lock = threading.Lock()

_failure_count = 0
_last_success = 0.0
_BACKOFF_THRESHOLD = 5  # raised from 3 — more tolerance before lockout
_BACKOFF_SECONDS = 60  # reduced from 120 — shorter penalty


# ─────────────────────────────────────────────
# MODEL DETECTION
# ─────────────────────────────────────────────


def _get_available_models() -> list[str]:
    """Ask Ollama which models are actually installed."""
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        if r.status_code == 200:
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []


def _pick_model(priority_list: list[str]) -> str:
    """Pick the first model from the priority list that is actually installed."""
    available = _get_available_models()
    available_set = set(available)

    for model in priority_list:
        if model in available_set:
            return model
        # Partial match — e.g. "deepseek-r1:14b" matches "deepseek-r1:14b-q4_K_M"
        for a in available:
            if a.startswith(model.split(":")[0]) and ":" in model:
                if model.split(":")[1] in a:
                    return a

    # Last resort: return first available model
    if available:
        return available[0]

    return "deepseek-r1:14b"


def get_chat_model() -> str:
    """Get the fast chat brain model."""
    global _chat_model
    with _model_lock:
        if _chat_model is None:
            _chat_model = _pick_model(CHAT_MODEL_PRIORITY)
            print(f"💬 CHAT BRAIN: {_chat_model}")
        return _chat_model


def get_deep_model() -> str:
    """Get the powerful deep thinking brain model."""
    global _deep_model
    with _model_lock:
        if _deep_model is None:
            _deep_model = _pick_model(DEEP_MODEL_PRIORITY)
            print(f"🧠 DEEP BRAIN: {_deep_model}")
        return _deep_model


def get_active_model() -> str:
    """Backward-compatible alias — returns the chat model."""
    return get_chat_model()


def refresh_model_selection():
    """Force re-detection of both models (call after pulling a new model)."""
    global _chat_model, _deep_model
    with _model_lock:
        _chat_model = None
        _deep_model = None
    chat = get_chat_model()
    deep = get_deep_model()
    print(f"🔄 Models refreshed → Chat: {chat} | Deep: {deep}")
    return chat


# ─────────────────────────────────────────────
# THINKING TAG STRIPPER
# ─────────────────────────────────────────────


def _strip_thinking_tags(text: str):
    """
    DeepSeek R1 outputs <think>...</think> chain-of-thought blocks.
    We strip them from Nex's spoken output but log them for transparency.
    """
    import re

    thinking = re.findall(r"<think>(.*?)</think>", text, re.DOTALL)
    clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return clean, thinking


# ─────────────────────────────────────────────
# CORE CALL — used by run_ui.py for CHAT
# ─────────────────────────────────────────────


def call_llm(prompt: str, timeout: int = None, log_thinking: bool = False) -> str:
    """
    Fast chat call. Always uses the 14b chat brain.
    This is the drop-in replacement for the old call_llm() in run_ui.py.

    Args:
        prompt:       The full prompt string.
        timeout:      Max seconds to wait. Defaults to CHAT_TIMEOUT (120s).
        log_thinking: If True, returns (response, thinking_steps) tuple.

    Returns:
        str: Nex's response with thinking tags stripped.
    """
    global _failure_count, _last_success

    if timeout is None:
        timeout = CHAT_TIMEOUT

    # Backoff check
    if _failure_count >= _BACKOFF_THRESHOLD:
        elapsed = time.time() - _last_success
        if elapsed < _BACKOFF_SECONDS:
            print(
                f"⏸️ LLM BACKOFF: {_failure_count} failures, cooling down {int(_BACKOFF_SECONDS - elapsed)}s"
            )
            return ""
        else:
            _failure_count = 0

    model = get_chat_model()
    is_thinking = any(tm in model for tm in THINKING_MODELS)

    try:
        response = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 1024,
                    "temperature": 0.7,
                    "top_p": 0.9,
                },
            },
            timeout=timeout,
        )

        raw = response.json().get("response", "")

        if not raw:
            _failure_count += 1
            return ""

        _failure_count = 0
        _last_success = time.time()

        if is_thinking:
            clean, thinking = _strip_thinking_tags(raw)
            if log_thinking and thinking:
                return clean, thinking
            return clean
        else:
            return raw

    except requests.exceptions.Timeout:
        _failure_count += 1
        print(f"⏱️ CHAT TIMEOUT ({_failure_count}) model={model} timeout={timeout}s")
        return ""
    except requests.exceptions.ConnectionError:
        _failure_count += 1
        print(f"🔌 CONNECTION ERROR ({_failure_count}) — is Ollama running?")
        return ""
    except Exception as e:
        _failure_count += 1
        print(f"❌ LLM ERROR: {e}")
        return ""


# ─────────────────────────────────────────────
# DEEP CALL — used for background cognition
# ─────────────────────────────────────────────


def call_llm_deep(prompt: str, timeout: int = None) -> dict:
    """
    Powerful deep thinking call. Uses the 32b brain.
    Use this for cognition cycles, research, and background reasoning
    where response time doesn't matter but quality does.

    Returns:
        {
          "response": str,
          "thinking": list[str],
          "model": str,
          "reasoning_available": bool
        }
    """
    if timeout is None:
        timeout = DEEP_TIMEOUT

    model = get_deep_model()
    is_thinking = any(tm in model for tm in THINKING_MODELS)

    try:
        print(f"🧠 DEEP CALL: model={model} timeout={timeout}s")
        response = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 2048,
                    "temperature": 0.7,
                    "top_p": 0.9,
                },
            },
            timeout=timeout,
        )

        raw = response.json().get("response", "")

        if not raw:
            return {
                "response": "",
                "thinking": [],
                "model": model,
                "reasoning_available": False,
            }

        if is_thinking:
            clean, thinking = _strip_thinking_tags(raw)
            return {
                "response": clean,
                "thinking": thinking,
                "model": model,
                "reasoning_available": bool(thinking),
            }
        else:
            return {
                "response": raw,
                "thinking": [],
                "model": model,
                "reasoning_available": False,
            }

    except requests.exceptions.Timeout:
        print(
            f"⏱️ DEEP TIMEOUT — model={model} took >{timeout}s (this is ok for background tasks)"
        )
        return {
            "response": "",
            "thinking": [],
            "model": model,
            "reasoning_available": False,
        }
    except Exception as e:
        print(f"❌ DEEP ERROR: {e}")
        return {
            "response": "",
            "thinking": [],
            "model": model,
            "reasoning_available": False,
        }


# ─────────────────────────────────────────────
# BACKWARD COMPAT — call_llm_with_reasoning
# ─────────────────────────────────────────────


def call_llm_with_reasoning(prompt: str, timeout: int = None) -> dict:
    """
    Now routes to call_llm_deep() for maximum reasoning quality.
    Kept for backward compatibility with any existing code using this function.
    """
    return call_llm_deep(prompt, timeout=timeout)


# ─────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────


def get_llm_status() -> dict:
    """Return current LLM router status for the UI."""
    chat = get_chat_model()
    deep = get_deep_model()
    available = _get_available_models()
    return {
        "chat_model": chat,
        "deep_model": deep,
        "active_model": chat,  # backward compat
        "available_models": available,
        "is_thinking_model": any(tm in chat for tm in THINKING_MODELS),
        "failure_count": _failure_count,
        "status": "backoff" if _failure_count >= _BACKOFF_THRESHOLD else "ok",
        "architecture": "two-brain",
    }
