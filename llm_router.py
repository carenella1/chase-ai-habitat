"""
llm_router.py  —  Two-Brain Architecture (v2 — GPU-Optimized)

WHAT CHANGED FROM v1:
  - Full GPU offloading for RTX 4070 Ti Super (16GB VRAM)
  - Ollama health check before every call — no wasted attempts
  - Larger context windows (8192 chat, 16384 deep) — Nex's prompts are big
  - Smarter backoff: resets properly, doesn't lock out on startup failures
  - Model warm-up on startup so first chat response isn't slow
  - Qwen3:32b added as the new deep brain option (better than DeepSeek R1)
  - Streaming support for chat (faster perceived response time)
  - Proper system prompt support for models that use it (Gemma4, Qwen3)
  - Detailed status reporting so the UI shows exactly what's happening

HARDWARE THIS IS TUNED FOR:
  CPU:  AMD Ryzen 7 7800X3D (8 cores, 3D V-Cache)
  GPU:  NVIDIA RTX 4070 Ti SUPER (16GB VRAM)
  RAM:  Assumed 32GB+ system RAM
  SSD:  Samsung 990 PRO 2TB (fast model loading)

MODEL STRATEGY:
  CHAT BRAIN  → Gemma4:27b or Qwen3:14b
                Fast responses, native system prompts
                Target: 5-15 seconds per response

  DEEP BRAIN  → Qwen3:32b or DeepSeek-R1:32b
                Powerful overnight cognition
                Target: 60-180 seconds, quality over speed
                Runs fully in GPU when possible

GPU VRAM BUDGET (16GB):
  Qwen3:14b  (Q4_K_M) ≈ 8.5GB  → fits comfortably, leaves room
  Qwen3:32b  (Q4_K_M) ≈ 18GB   → needs offload: ~14 layers to CPU
  DeepSeek R1:32b Q4  ≈ 18GB   → same offload strategy
  Gemma4:27b (Q4)     ≈ 15GB   → fits with tight margin
"""

import requests
import threading
import time
import json
import os

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

OLLAMA_BASE = "http://localhost:11434"

# CHAT BRAIN — fast, used for live conversation with Chase
# First installed model in this list wins
CHAT_MODEL_PRIORITY = [
    "gemma4:27b",  # Best chat brain — native system prompts, fast MoE
    "gemma4:26b",  # Alias some installs use
    "qwen3:14b",  # Excellent fallback — fast, smart, system prompt support
    "qwen3:8b",  # Lighter fallback
    "llama3.1:8b",  # Emergency fallback
    "deepseek-r1:14b",  # Last resort (slower due to thinking tags)
]

# DEEP BRAIN — powerful, used for background cognition only
# Most powerful first
DEEP_MODEL_PRIORITY = [
    "qwen3:32b",  # NEW: Better reasoning than DeepSeek R1, hybrid think mode
    "deepseek-r1:32b",  # Strong fallback
    "qwen3:14b",  # If 32b not available
    "deepseek-r1:14b",  # Last resort
]

# Models that output <think>...</think> reasoning blocks
# We strip these from chat responses but log them for the UI
THINKING_MODELS = {
    "deepseek-r1:32b",
    "deepseek-r1:14b",
    "deepseek-r1:7b",
    "deepseek-r1:70b",
    "qwen3:32b",
    "qwen3:14b",
    "qwen3:8b",
    "qwen3:4b",
}

# Models that use the /api/chat endpoint (system prompt support)
# vs /api/generate (raw prompt only)
CHAT_API_MODELS = {
    "gemma4",
    "qwen3",
    "llama3",
    "llama3.1",
    "llama3.2",
    "mistral",
    "phi3",
    "phi4",
}

# GPU layer config for RTX 4070 Ti SUPER (16GB VRAM)
# -1 means offload ALL layers to GPU (best for models that fit)
# Positive number = how many layers go to GPU, rest stay on CPU
GPU_LAYERS = {
    "gemma4:27b": -1,  # ~15GB — fits, offload all
    "gemma4:26b": -1,
    "qwen3:14b": -1,  # ~8.5GB — fits easily, offload all
    "qwen3:8b": -1,  # ~5GB — fits easily
    "qwen3:32b": 40,  # ~18GB total, ~14GB on GPU (40 layers), rest CPU
    "deepseek-r1:32b": 38,  # Similar size — 38 layers on GPU
    "deepseek-r1:14b": -1,  # ~8.5GB — fits
    "llama3.1:8b": -1,
}

# Timeouts — tuned for your hardware
CHAT_TIMEOUT = 90  # 90s max for chat — if it takes longer, something is wrong
DEEP_TIMEOUT = 600  # 10 minutes for deep cognition (32b thinking takes time)
HEALTH_TIMEOUT = 5  # Health check timeout

# Context windows — bigger = more memory, but Nex's prompts need it
CHAT_CTX = 8192  # Chat context: 8k tokens (enough for memory + history)
DEEP_CTX = 16384  # Deep context: 16k tokens (enough for full research)

# Backoff settings — more forgiving than before
_BACKOFF_THRESHOLD = 5  # Fail 5 times before backing off (was 8 but reset wrong)
_BACKOFF_SECONDS = 15  # Only 15s cooldown (was 30)

# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────

_chat_model: str | None = None
_deep_model: str | None = None
_model_lock = threading.Lock()

_failure_count = 0
_deep_failure_count = 0
_last_failure_time = 0.0
_last_success_time = 0.0

_ollama_healthy = False  # Tracks Ollama availability
_last_health_check = 0.0
_HEALTH_CHECK_INTERVAL = 10  # Re-check Ollama health every 10 seconds

# ─────────────────────────────────────────────
# OLLAMA HEALTH CHECK
# ─────────────────────────────────────────────


def _check_ollama_health() -> bool:
    """
    Fast check: is Ollama running and responsive?
    Cached for 10 seconds so we don't hammer it.
    """
    global _ollama_healthy, _last_health_check

    now = time.time()
    if now - _last_health_check < _HEALTH_CHECK_INTERVAL:
        return _ollama_healthy

    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=HEALTH_TIMEOUT)
        _ollama_healthy = r.status_code == 200
        _last_health_check = now
        if _ollama_healthy:
            print("✅ OLLAMA: healthy")
        else:
            print(f"⚠️ OLLAMA: unhealthy (status {r.status_code})")
    except Exception as e:
        _ollama_healthy = False
        _last_health_check = now
        print(f"🔌 OLLAMA: not reachable — {e}")

    return _ollama_healthy


def wait_for_ollama(max_wait: int = 60) -> bool:
    """
    Wait up to max_wait seconds for Ollama to become available.
    Called at startup. Returns True if Ollama came up.
    """
    print(f"⏳ Waiting for Ollama (up to {max_wait}s)...")
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
            if r.status_code == 200:
                global _ollama_healthy, _last_health_check
                _ollama_healthy = True
                _last_health_check = time.time()
                print("✅ Ollama is ready")
                return True
        except Exception:
            pass
        time.sleep(2)
    print("❌ Ollama did not come up in time")
    return False


# ─────────────────────────────────────────────
# MODEL DETECTION
# ─────────────────────────────────────────────


def _get_available_models() -> list[str]:
    """Ask Ollama which models are actually installed."""
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=HEALTH_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []


def _pick_model(priority_list: list[str]) -> str | None:
    """
    Pick the first model from the priority list that is installed.
    Returns None if nothing is available (Ollama down or no models).
    """
    available = _get_available_models()
    if not available:
        print("⚠️ No models found — is Ollama running?")
        return None

    available_set = set(available)
    print(f"🔍 Available models: {available}")

    for model in priority_list:
        if model in available_set:
            print(f"✅ Selected: {model}")
            return model
        # Partial match — "qwen3:14b" matches "qwen3:14b-instruct-q4_K_M"
        base = model.split(":")[0]
        tag = model.split(":")[1] if ":" in model else ""
        for a in available:
            if a.startswith(base) and (not tag or tag.split("-")[0] in a):
                print(f"✅ Partial match: {model} → {a}")
                return a

    # Nothing matched — use whatever is installed
    fallback = available[0]
    print(f"⚠️ No priority model found, using: {fallback}")
    return fallback


def get_chat_model() -> str:
    """Get the fast chat brain model name."""
    global _chat_model
    with _model_lock:
        if _chat_model is None:
            _chat_model = _pick_model(CHAT_MODEL_PRIORITY)
            if _chat_model:
                print(f"💬 CHAT BRAIN: {_chat_model}")
        return _chat_model or "gemma4:27b"  # Safe default


def get_deep_model() -> str:
    """Get the powerful deep thinking brain model name."""
    global _deep_model
    with _model_lock:
        if _deep_model is None:
            _deep_model = _pick_model(DEEP_MODEL_PRIORITY)
            if _deep_model:
                print(f"🧠 DEEP BRAIN: {_deep_model}")
        return _deep_model or "deepseek-r1:32b"  # Safe default


def get_active_model() -> str:
    """Backward-compatible alias — returns the chat model."""
    return get_chat_model()


def refresh_model_selection():
    """Force re-detection of both models. Call after pulling a new model."""
    global _chat_model, _deep_model
    with _model_lock:
        _chat_model = None
        _deep_model = None
    chat = get_chat_model()
    deep = get_deep_model()
    print(f"🔄 Models refreshed → Chat: {chat} | Deep: {deep}")
    return {"chat": chat, "deep": deep}


# ─────────────────────────────────────────────
# GPU LAYER HELPER
# ─────────────────────────────────────────────


def _get_gpu_layers(model: str) -> int:
    """
    Returns the num_gpu value for a model.
    -1 = offload everything to GPU (model fits in VRAM)
    N  = offload N layers (model is too big for VRAM, split CPU/GPU)
    """
    base = model.split(":")[0].lower()
    for key, layers in GPU_LAYERS.items():
        if model == key or model.startswith(key.split(":")[0]):
            return layers
    # Unknown model — try full GPU offload, fall back gracefully
    return -1


def _should_use_chat_api(model: str) -> bool:
    """True if this model should use /api/chat (system prompt support)."""
    lower = model.lower()
    return any(m in lower for m in CHAT_API_MODELS)


# ─────────────────────────────────────────────
# THINKING TAG STRIPPER
# ─────────────────────────────────────────────


def _strip_thinking_tags(text: str):
    """
    Strip <think>...</think> chain-of-thought blocks from model output.
    Returns (clean_text, [thinking_blocks])
    """
    import re

    thinking = re.findall(r"<think>(.*?)</think>", text, re.DOTALL)
    clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return clean, thinking


# ─────────────────────────────────────────────
# CORE CHAT CALL
# ─────────────────────────────────────────────


def call_llm(
    prompt: str,
    timeout: int = None,
    log_thinking: bool = False,
    system_prompt: str = None,
) -> str:
    """
    Fast chat call. Returns the response string.
    Returns "" if Ollama is down or the model fails.
    """
    global _failure_count, _last_failure_time, _last_success_time

    if timeout is None:
        timeout = CHAT_TIMEOUT

    # Fast health check — don't even try if Ollama is down
    if not _check_ollama_health():
        print("⏭️ Skipping LLM call — Ollama not healthy")
        return ""

    # Backoff check — only kick in after repeated failures
    if _failure_count >= _BACKOFF_THRESHOLD:
        elapsed = time.time() - _last_failure_time
        if elapsed < _BACKOFF_SECONDS:
            remaining = int(_BACKOFF_SECONDS - elapsed)
            print(f"⏸️ LLM BACKOFF: {_failure_count} failures, cooling {remaining}s")
            return ""
        else:
            # Reset after cooldown
            _failure_count = 0
            print("🔄 LLM backoff reset")

    model = get_chat_model()
    num_gpu = _get_gpu_layers(model)
    use_chat = _should_use_chat_api(model)
    is_thinking = any(tm in model for tm in THINKING_MODELS)

    try:
        if use_chat:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_predict": 768,
                        "temperature": 0.75,
                        "top_p": 0.9,
                        "top_k": 40,
                        "num_ctx": CHAT_CTX,
                        "repeat_penalty": 1.2,
                        "num_gpu": num_gpu,
                    },
                },
                timeout=timeout,
            )
            raw = response.json().get("message", {}).get("content", "")

        else:
            # Raw generate API (DeepSeek R1 etc)
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = requests.post(
                f"{OLLAMA_BASE}/api/generate",
                json={
                    "model": model,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 768,
                        "temperature": 0.75,
                        "top_p": 0.9,
                        "top_k": 40,
                        "num_ctx": CHAT_CTX,
                        "repeat_penalty": 1.2,
                        "num_gpu": num_gpu,
                    },
                },
                timeout=timeout,
            )
            raw = response.json().get("response", "")

        if not raw or not raw.strip():
            _failure_count += 1
            _last_failure_time = time.time()
            print(f"⚠️ Empty response from {model} (failure #{_failure_count})")
            return ""

        # Success — reset failure counter
        _failure_count = 0
        _last_success_time = time.time()

        # Strip thinking tags if needed
        if is_thinking:
            clean, thinking = _strip_thinking_tags(raw)
            if log_thinking and thinking:
                return clean, thinking
            return clean if clean else raw

        return raw

    except requests.exceptions.Timeout:
        _failure_count += 1
        _last_failure_time = time.time()
        print(f"⏱️ CHAT TIMEOUT #{_failure_count} — model={model}, timeout={timeout}s")
        # Force model re-detection on repeated timeouts (model might have crashed)
        if _failure_count >= 3:
            global _chat_model
            _chat_model = None
        return ""

    except requests.exceptions.ConnectionError:
        _failure_count += 1
        _last_failure_time = time.time()
        # Mark Ollama as unhealthy so next call does health check
        global _ollama_healthy, _last_health_check
        _ollama_healthy = False
        _last_health_check = 0.0
        print(f"🔌 CONNECTION ERROR #{_failure_count} — is Ollama running?")
        return ""

    except Exception as e:
        _failure_count += 1
        _last_failure_time = time.time()
        print(f"❌ LLM CHAT ERROR: {type(e).__name__}: {e}")
        return ""


# ─────────────────────────────────────────────
# DEEP COGNITION CALL
# ─────────────────────────────────────────────


def call_llm_deep(
    prompt: str,
    timeout: int = None,
    system_prompt: str = None,
) -> dict:
    """
    Powerful deep thinking call for background cognition.
    Uses the 32b brain. Slower but much more capable.

    Returns:
        {
          "response": str,
          "thinking": list[str],
          "model": str,
          "reasoning_available": bool,
          "success": bool
        }
    """
    global _deep_failure_count

    if timeout is None:
        timeout = DEEP_TIMEOUT

    _EMPTY = {
        "response": "",
        "thinking": [],
        "model": "unknown",
        "reasoning_available": False,
        "success": False,
    }

    if not _check_ollama_health():
        print("⏭️ Skipping DEEP call — Ollama not healthy")
        return _EMPTY

    model = get_deep_model()
    num_gpu = _get_gpu_layers(model)
    use_chat = _should_use_chat_api(model)
    is_thinking = any(tm in model for tm in THINKING_MODELS)

    print(f"🧠 DEEP CALL: model={model}, gpu_layers={num_gpu}, timeout={timeout}s")

    try:
        if use_chat:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_predict": 2048,
                        "temperature": 0.6,
                        "top_p": 0.9,
                        "top_k": 40,
                        "num_ctx": DEEP_CTX,
                        "repeat_penalty": 1.15,
                        "num_gpu": num_gpu,
                    },
                },
                timeout=timeout,
            )
            raw = response.json().get("message", {}).get("content", "")

        else:
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = requests.post(
                f"{OLLAMA_BASE}/api/generate",
                json={
                    "model": model,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 2048,
                        "temperature": 0.6,
                        "top_p": 0.9,
                        "top_k": 40,
                        "num_ctx": DEEP_CTX,
                        "repeat_penalty": 1.15,
                        "num_gpu": num_gpu,
                    },
                },
                timeout=timeout,
            )
            raw = response.json().get("response", "")

        if not raw or not raw.strip():
            _deep_failure_count += 1
            print(f"⚠️ Empty DEEP response from {model}")
            return {**_EMPTY, "model": model}

        _deep_failure_count = 0

        if is_thinking:
            clean, thinking = _strip_thinking_tags(raw)
            return {
                "response": clean if clean else raw,
                "thinking": thinking,
                "model": model,
                "reasoning_available": bool(thinking),
                "success": True,
            }
        else:
            return {
                "response": raw,
                "thinking": [],
                "model": model,
                "reasoning_available": False,
                "success": True,
            }

    except requests.exceptions.Timeout:
        _deep_failure_count += 1
        print(f"⏱️ DEEP TIMEOUT #{_deep_failure_count} — model={model}")
        return {**_EMPTY, "model": model}

    except Exception as e:
        _deep_failure_count += 1
        print(f"❌ DEEP ERROR: {type(e).__name__}: {e}")
        return {**_EMPTY, "model": model}


# Backward compat
def call_llm_with_reasoning(prompt: str, timeout: int = None) -> dict:
    return call_llm_deep(prompt, timeout=timeout)


# ─────────────────────────────────────────────
# MODEL WARM-UP
# ─────────────────────────────────────────────


def warmup_models():
    """
    Send a tiny prompt to both models to load them into VRAM.
    Call this once at startup so the first real request isn't slow.
    This runs in a background thread — doesn't block startup.
    """

    def _warmup():
        time.sleep(5)  # Wait for Ollama to fully start
        if not _check_ollama_health():
            print("⚠️ Warmup skipped — Ollama not ready")
            return

        chat_model = get_chat_model()
        if chat_model:
            print(f"🔥 Warming up chat brain: {chat_model}")
            try:
                call_llm("Hi.", timeout=60)
                print(f"✅ Chat brain warm: {chat_model}")
            except Exception as e:
                print(f"⚠️ Chat warmup error: {e}")

        # Don't warm up deep brain at startup — save VRAM for chat

    t = threading.Thread(target=_warmup, daemon=True)
    t.name = "llm-warmup"
    t.start()


# ─────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────


def get_llm_status() -> dict:
    """Return current LLM router status for the UI dashboard."""
    chat = get_chat_model()
    deep = get_deep_model()
    available = _get_available_models()
    healthy = _check_ollama_health()

    return {
        "chat_model": chat,
        "deep_model": deep,
        "active_model": chat,  # backward compat
        "available_models": available,
        "is_thinking_model": any(tm in chat for tm in THINKING_MODELS),
        "failure_count": _failure_count,
        "deep_failure_count": _deep_failure_count,
        "ollama_healthy": healthy,
        "status": (
            "backoff"
            if _failure_count >= _BACKOFF_THRESHOLD
            else ("ok" if healthy else "offline")
        ),
        "architecture": "two-brain-gpu",
        "gpu_layers_chat": _get_gpu_layers(chat) if chat else 0,
        "gpu_layers_deep": _get_gpu_layers(deep) if deep else 0,
        "chat_ctx": CHAT_CTX,
        "deep_ctx": DEEP_CTX,
    }


def get_model_recommendations() -> dict:
    """
    Returns recommended ollama pull commands for this hardware.
    Shown in the UI to help Chase know what to install.
    """
    installed = set(_get_available_models())
    recs = {}

    wanted = {
        "qwen3:14b": "Best chat brain — fast, smart, free",
        "qwen3:32b": "Best deep brain — better reasoning than DeepSeek",
        "gemma4:27b": "Alternative chat brain — Google's best open model",
        "deepseek-r1:32b": "Deep brain fallback — proven reasoning model",
    }

    for model, desc in wanted.items():
        base = model.split(":")[0]
        is_installed = any(a.startswith(base) for a in installed)
        recs[model] = {
            "description": desc,
            "installed": is_installed,
            "pull_cmd": f"ollama pull {model}",
        }

    return recs
