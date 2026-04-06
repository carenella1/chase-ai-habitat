"""
llm_router.py  —  Phase 1: Nex Brain Upgrade

DROP-IN REPLACEMENT for the call_llm() function in run_ui.py.

WHAT THIS DOES:
  Nex currently hard-codes deepseek-r1:14b with no fallback.
  This router tries models in priority order, picks the best one
  available on your machine, and uses "thinking mode" if the model
  supports it (DeepSeek V3.2 / R1 stream their chain-of-thought,
  which dramatically improves reasoning quality).

WHY THIS MATTERS:
  The model IS Nex's brain. Every cognition cycle, every debate,
  every hypothesis — all of it gets smarter when the underlying
  model is smarter. This is the single highest-leverage upgrade.

INSTALL:
  1. Run:  ollama pull deepseek-r1:32b
     (or)  ollama pull deepseek-r1:70b   (needs ~40GB VRAM)
     (or)  ollama pull glm4:9b            (lighter, still excellent)
  2. Replace call_llm() in run_ui.py with: from llm_router import call_llm
  3. That's it. The router auto-detects what's available.

MODEL PRIORITY (best → fallback):
  1. deepseek-r1:32b   — Best reasoning, chain-of-thought, ~18GB RAM
  2. deepseek-r1:14b   — Current Nex model, kept as fallback
  3. glm4:9b           — Excellent agentic model, lighter
  4. deepseek-r1:7b    — Minimal footprint fallback
  5. llama3.1:8b       — Last resort fallback
"""

import requests
import threading
import time

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

OLLAMA_BASE = "http://localhost:11434"

# Models in priority order — first available wins at startup
MODEL_PRIORITY = [
    "deepseek-r1:32b",
    "deepseek-r1:14b",
    "glm4:9b",
    "deepseek-r1:7b",
    "llama3.1:8b",
]

# Models that support thinking/reasoning mode (strip <think> tags from output)
THINKING_MODELS = {
    "deepseek-r1:32b",
    "deepseek-r1:14b",
    "deepseek-r1:7b",
    "deepseek-r1:70b",
}

# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────

_active_model: str | None = None
_active_model_lock = threading.Lock()
_failure_count = 0
_last_success = 0.0
_BACKOFF_THRESHOLD = 3
_BACKOFF_SECONDS = 120


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


def _select_best_model() -> str:
    """Pick the highest-priority model that's actually available."""
    available = _get_available_models()
    available_set = set(available)

    for model in MODEL_PRIORITY:
        # Exact match or prefix match (e.g. "deepseek-r1:32b" matches "deepseek-r1:32b-q4_K_M")
        if model in available_set:
            return model
        for a in available:
            if (
                a.startswith(model.split(":")[0])
                and ":" in model
                and model.split(":")[1] in a
            ):
                return a

    # If nothing matches, use whatever is first available
    if available:
        return available[0]

    # Absolute fallback — Ollama will error if not installed
    return "deepseek-r1:14b"


def get_active_model() -> str:
    """Get (or lazily detect) the active model."""
    global _active_model
    with _active_model_lock:
        if _active_model is None:
            _active_model = _select_best_model()
            print(f"🧠 LLM ROUTER: Selected model → {_active_model}")
        return _active_model


def refresh_model_selection():
    """Force re-detection (call after pulling a new model)."""
    global _active_model
    with _active_model_lock:
        _active_model = None
    return get_active_model()


# ─────────────────────────────────────────────
# THINKING MODE
# ─────────────────────────────────────────────


def _strip_thinking_tags(text: str) -> str:
    """
    DeepSeek R1 outputs <think>...</think> blocks containing its
    chain-of-thought. These are valuable internally but shouldn't
    appear in Nex's spoken responses. We strip them here.

    IMPORTANT: We log the thinking separately so it can optionally
    be stored in cognition history for transparency.
    """
    import re

    thinking = re.findall(r"<think>(.*?)</think>", text, re.DOTALL)
    clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return clean, thinking


# ─────────────────────────────────────────────
# CORE CALL
# ─────────────────────────────────────────────


def call_llm(prompt: str, timeout: int = 90, log_thinking: bool = False) -> str:
    """
    Drop-in replacement for call_llm() in run_ui.py.

    Args:
        prompt:       The full prompt string to send to the model.
        timeout:      Max seconds to wait for response.
        log_thinking: If True, returns a tuple (response, thinking_steps).
                      If False (default), returns just the response string.

    Returns:
        str: Nex's response with thinking tags stripped.
    """
    global _failure_count, _last_success

    # Backoff check
    if _failure_count >= _BACKOFF_THRESHOLD:
        elapsed = time.time() - _last_success
        if elapsed < _BACKOFF_SECONDS:
            print(f"⏸️ LLM BACKOFF: {_failure_count} failures, cooling down")
            return ""
        else:
            _failure_count = 0

    model = get_active_model()
    is_thinking_model = any(tm in model for tm in THINKING_MODELS)

    try:
        response = requests.post(
            f"{OLLAMA_BASE}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                # Thinking models benefit from higher token limits for reasoning
                "options": {
                    "num_predict": 2048 if is_thinking_model else 1024,
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

        if is_thinking_model:
            clean, thinking = _strip_thinking_tags(raw)
            if log_thinking and thinking:
                return clean, thinking
            return clean
        else:
            return raw

    except requests.exceptions.Timeout:
        _failure_count += 1
        print(f"⏱️ LLM TIMEOUT ({_failure_count}) model={model}")
        return ""
    except requests.exceptions.ConnectionError:
        _failure_count += 1
        print(f"🔌 LLM CONNECTION ERROR ({_failure_count}) — is Ollama running?")
        return ""
    except Exception as e:
        _failure_count += 1
        print(f"❌ LLM ERROR: {e}")
        return ""


# ─────────────────────────────────────────────
# COGNITION-OPTIMIZED CALL
# ─────────────────────────────────────────────


def call_llm_with_reasoning(prompt: str, timeout: int = 120) -> dict:
    """
    Enhanced call that captures and stores the reasoning chain.
    Use this for cognition cycles to give Nex's thinking transparency.

    Returns:
        {
          "response": str,           # Clean output
          "thinking": list[str],     # Chain-of-thought steps (if available)
          "model": str,              # Model used
          "reasoning_available": bool
        }
    """
    model = get_active_model()
    is_thinking = any(tm in model for tm in THINKING_MODELS)

    result = call_llm(prompt, timeout=timeout, log_thinking=True)

    if isinstance(result, tuple):
        response, thinking = result
        return {
            "response": response,
            "thinking": thinking,
            "model": model,
            "reasoning_available": True,
        }
    else:
        return {
            "response": result,
            "thinking": [],
            "model": model,
            "reasoning_available": False,
        }


# ─────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────


def get_llm_status() -> dict:
    """Return current LLM router status for the UI."""
    model = get_active_model()
    available = _get_available_models()
    return {
        "active_model": model,
        "available_models": available,
        "is_thinking_model": any(tm in model for tm in THINKING_MODELS),
        "failure_count": _failure_count,
        "status": "backoff" if _failure_count >= _BACKOFF_THRESHOLD else "ok",
    }


# ─────────────────────────────────────────────
# HOW TO WIRE INTO run_ui.py
# ─────────────────────────────────────────────
#
# 1. Copy this file next to run_ui.py
#
# 2. At the top of run_ui.py, REPLACE:
#       def call_llm(prompt, timeout=90):
#           ...
#    WITH:
#       from llm_router import call_llm, get_llm_status
#
# 3. Add a status endpoint to run_ui.py:
#       @app.route("/api/llm/status")
#       def api_llm_status():
#           from llm_router import get_llm_status
#           return jsonify(get_llm_status())
#
# 4. To pull a better model: ollama pull deepseek-r1:32b
#    Then call refresh_model_selection() or restart the app.
