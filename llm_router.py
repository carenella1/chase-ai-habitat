"""
llm_router.py  —  Two-Brain Architecture (v3 — 2026 Model Refresh)

WHAT CHANGED FROM v2:
  - New deep brain: gpt-oss:20b (OpenAI open-weight, MXFP4). Verified live
    on this machine: 100% GPU-resident, ~13-14GB VRAM even at 32k context,
    fast, and its native reasoning trace works with the "thinking" handling
    below.
  - New chat brain: qwen3:30b-a3b (Qwen3 MoE, 30.5B total / 3B active).
    Verified live: safe at 26 GPU layers (of 48) even at full 16k context —
    11.4GB VRAM, ~40 tokens/sec. NOTE: this model does NOT fit fully in
    16GB VRAM despite being MoE — num_gpu:-1 pushes it to ~15.8GB at 16k
    context, which is too tight in practice. 26 layers is the tested,
    safe value.
  - A newer "qwen3.6" model was evaluated and rejected: it's a real,
    installable Ollama model (36B MoE, ~23GB), but attempting to run it —
    even with partial GPU offload — caused this machine to hang/thrash
    twice. It was removed. Lesson baked into this file: never trust VRAM
    math alone for a new model; verify with a real load before configuring
    num_gpu for it.
  - Larger context windows (16384 chat, 32768 deep) — both new models
    handle it comfortably and Nex's prompts are big
  - Shorter deep timeout (420s, was 600s) — the new deep brain is faster
  - _get_gpu_layers now does exact-match-first, then longest-prefix-match
    on the FULL model string (not just the base name before ":"). The old
    logic compared bare prefixes and could make an unrelated model whose
    name happens to start with the same letters accidentally match another
    model's GPU_LAYERS rule. See _selftest_gpu_layers() below.
  - Reads Ollama's native message.thinking field (newer Ollama versions)
    in addition to <think> tag stripping, so reasoning logging works on
    both old and new Ollama versions
  - Removed gemma4:27b/26b, llama3, llama3.1, qwen3:32b, and
    deepseek-r1:32b from disk (freed ~65GB) since gpt-oss:20b and
    qwen3:30b-a3b supersede them. qwen3:32b/deepseek-r1:32b are kept as
    *config* fallback entries (in GPU_LAYERS/DEEP_MODEL_PRIORITY) in case
    they're ever reinstalled, even though the files are gone right now.
  - Everything else from v2 (GPU offloading, health checks, backoff,
    warm-up, status reporting) is unchanged

HARDWARE THIS IS TUNED FOR:
  CPU:  AMD Ryzen 7 7800X3D (8 cores, 3D V-Cache)
  GPU:  NVIDIA RTX 4070 Ti SUPER (16GB VRAM)
  RAM:  Assumed 32GB+ system RAM
  SSD:  Samsung 990 PRO 2TB (fast model loading)

MODEL STRATEGY:
  CHAT BRAIN  → qwen3:30b-a3b (MoE, 26 GPU layers) or dense qwen3:14b
                Fast responses, native system prompts
                Target: 5-15 seconds per response

  DEEP BRAIN  → gpt-oss:20b (fully GPU-resident) or qwen3:30b-a3b
                Powerful background cognition, faster than the old 32b
                models it replaces

GPU VRAM BUDGET (16GB), all verified by live testing on this machine:
  gpt-oss:20b     (MXFP4)   → 100% GPU, ~13-14GB even at 32k context
  qwen3:30b-a3b   (MoE Q4)  → 26/48 layers on GPU, ~11.4GB at 16k context
  Qwen3:14b       (Q4_K_M)  → ~8.5GB, fits fully, offload all
  Qwen3:32b       (Q4_K_M)  → ~18GB, needs ~40/64 layers on GPU (not
                               currently installed, kept as a fallback)
  DeepSeek R1:32b (Q4)      → ~18GB, same offload strategy (not currently
                               installed, kept as a fallback)
  DeepSeek R1:14b (Q4)      → ~8.5GB, fits fully
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
    "qwen3:30b-a3b",  # NEW: MoE, verified ~40 tok/s at 26 GPU layers
    "qwen3:14b",  # proven fallback, fits fully on GPU
    "qwen3:8b",  # smaller fallback if 14b not installed
    "deepseek-r1:14b",  # last resort
]

# DEEP BRAIN — powerful, used for background cognition only
# Most powerful first
DEEP_MODEL_PRIORITY = [
    "gpt-oss:20b",  # NEW: OpenAI open-weight, verified 100% GPU, fast
    "qwen3:30b-a3b",  # can double as deep brain if gpt-oss unavailable
    "qwen3:32b",  # old fallback — not installed right now, kept for
    #                graceful degradation if it's ever reinstalled
    "deepseek-r1:32b",  # same — not installed, kept as a fallback
    "qwen3:14b",  # if nothing bigger is available
    "deepseek-r1:14b",  # last resort
]

# Models that output <think>...</think> reasoning blocks (or a native
# reasoning field — see the "thinking" handling in call_llm/call_llm_deep)
# We strip/collect these from chat responses but log them for the UI
THINKING_MODELS = {
    "deepseek-r1:32b",
    "deepseek-r1:14b",
    "deepseek-r1:7b",
    "deepseek-r1:70b",
    "qwen3:32b",
    "qwen3:14b",
    "qwen3:8b",
    "qwen3:4b",
    "qwen3:30b-a3b",
    "gpt-oss",
}

# Models that use the /api/chat endpoint (system prompt support)
# vs /api/generate (raw prompt only)
CHAT_API_MODELS = {
    "gemma4",
    "qwen3",  # covers qwen3:14b, qwen3:32b, qwen3:30b-a3b, etc. (substring match)
    "llama3",
    "llama3.1",
    "llama3.2",
    "mistral",
    "phi3",
    "phi4",
    "gpt-oss",
}

# GPU layer config for RTX 4070 Ti SUPER (16GB VRAM)
# -1 means offload ALL layers to GPU (best for models that fit)
# Positive number = how many layers go to GPU, rest stay on CPU
# Every value below was checked with a real load on this machine (via
# /api/chat + `ollama ps` + nvidia-smi), not estimated from model size.
# Order matters for readability, but _get_gpu_layers() below matches on
# exact-name-first then longest-prefix, so lookup no longer depends on it.
GPU_LAYERS = {
    "gpt-oss:20b": -1,  # verified: 100% GPU, ~13-14GB even at 32k context
    "qwen3:30b-a3b": 26,  # verified: ~11.4GB at 16k context, ~40 tok/s.
    #                        NOTE: -1 (full GPU) does NOT fit — that was
    #                        tested too and leaves under 1GB headroom.
    "qwen3:14b": -1,  # ~8.5GB — fits easily, offload all
    "qwen3:8b": -1,  # ~5GB — fits easily
    "qwen3:32b": 40,  # ~18GB total, ~14GB on GPU (40 layers), rest CPU
    #                    (not installed right now — kept as a fallback)
    "deepseek-r1:32b": 38,  # Similar size — 38 layers on GPU
    #                          (not installed right now — kept as a fallback)
    "deepseek-r1:14b": -1,  # ~8.5GB — fits
}

# Timeouts — tuned for your hardware
CHAT_TIMEOUT = 90  # 90s max for chat — if it takes longer, something is wrong
DEEP_TIMEOUT = 420  # 7 minutes — the new deep brain (gpt-oss/qwen3.6) is much faster
HEALTH_TIMEOUT = 5  # Health check timeout

# Context windows — bigger = more memory, but Nex's prompts need it
CHAT_CTX = 16384  # Chat context: 16k tokens (enough for memory + history)
DEEP_CTX = 32768  # Deep context: 32k tokens (enough for full research)

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

    Matching rules:
      1. An exact match on the full model string always wins.
      2. Otherwise, the LONGEST GPU_LAYERS key that the model name starts
         with wins. This matters because "qwen3.6:..." models contain
         "qwen3" as a substring/prefix-of-prefix of "qwen3:32b" — comparing
         against the base name alone (the old behavior) let a qwen3.6 model
         accidentally match the qwen3:32b rule and get throttled to 40
         layers. Comparing against the full key (with tag) fixes that.
    """
    if model in GPU_LAYERS:
        return GPU_LAYERS[model]

    best_key = None
    for key in GPU_LAYERS:
        if model.startswith(key) and (best_key is None or len(key) > len(best_key)):
            best_key = key

    if best_key is not None:
        return GPU_LAYERS[best_key]

    # Unknown model — try full GPU offload, fall back gracefully
    return -1


def _selftest_gpu_layers():
    """Sanity-check the qwen3 vs qwen3.6 substring trap doesn't regress."""
    assert _get_gpu_layers("qwen3.6:latest") == -1, (
        "qwen3.6 models must not fall through to the qwen3:32b rule"
    )
    assert _get_gpu_layers("qwen3:32b") == 40, (
        "qwen3:32b should still offload exactly 40 layers"
    )


try:
    _selftest_gpu_layers()
except AssertionError as e:
    print(f"⚠️ GPU_LAYERS self-test failed: {e}")


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
        native_thinking = ""
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
                        "num_predict": 1536,
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
            message = response.json().get("message", {})
            raw = message.get("content", "")
            # Newer Ollama versions return reasoning in a native field
            # instead of (or in addition to) inline <think> tags
            native_thinking = message.get("thinking", "") or ""

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

        # Strip thinking tags if needed, and merge in native reasoning
        if is_thinking or native_thinking:
            clean, thinking = _strip_thinking_tags(raw)
            if native_thinking:
                thinking = thinking + [native_thinking]
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
            print(
                f"🔄 Chat model reset after {_failure_count} failures — will re-detect"
            )
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
# STREAMING CHAT CALL — yields text chunks as they're generated
# ─────────────────────────────────────────────


def call_llm_stream(prompt: str, timeout: int = None, system_prompt: str = None):
    """
    Same as call_llm, but yields response text incrementally instead of
    waiting for the full generation. Lets the UI show words as they're
    produced instead of a long silent wait.

    Safety: if the model emits a <think>...</think> reasoning block (native
    thinking models), that text is withheld from the stream entirely — we
    only flush text once we're sure we're outside any open <think> tag, so
    raw chain-of-thought never leaks into the chat bubble.

    Yields str chunks. Raises nothing on failure — yields nothing and the
    caller should treat "no chunks yielded" as a failure, same as call_llm
    returning "".
    """
    global _failure_count, _last_failure_time, _last_success_time

    if timeout is None:
        timeout = CHAT_TIMEOUT

    if not _check_ollama_health():
        print("⏭️ Skipping LLM stream — Ollama not healthy")
        return

    if _failure_count >= _BACKOFF_THRESHOLD:
        elapsed = time.time() - _last_failure_time
        if elapsed < _BACKOFF_SECONDS:
            remaining = int(_BACKOFF_SECONDS - elapsed)
            print(f"⏸️ LLM BACKOFF: {_failure_count} failures, cooling {remaining}s")
            return
        else:
            _failure_count = 0
            print("🔄 LLM backoff reset")

    model = get_chat_model()
    num_gpu = _get_gpu_layers(model)
    use_chat = _should_use_chat_api(model)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        if use_chat:
            response = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "options": {
                        "num_predict": 1024,
                        "temperature": 0.65,
                        "top_p": 0.9,
                        "top_k": 40,
                        "num_ctx": CHAT_CTX,
                        "repeat_penalty": 1.15,
                        "num_gpu": num_gpu,
                    },
                },
                timeout=timeout,
                stream=True,
            )
        else:
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            response = requests.post(
                f"{OLLAMA_BASE}/api/generate",
                json={
                    "model": model,
                    "prompt": full_prompt,
                    "stream": True,
                    "options": {
                        "num_predict": 512,
                        "temperature": 0.65,
                        "top_p": 0.9,
                        "top_k": 40,
                        "num_ctx": CHAT_CTX,
                        "repeat_penalty": 1.15,
                        "num_gpu": num_gpu,
                    },
                },
                timeout=timeout,
                stream=True,
            )

        raw_accum = ""
        emitted_len = 0
        got_any = False

        for line in response.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue

            if use_chat:
                delta = data.get("message", {}).get("content", "") or ""
            else:
                delta = data.get("response", "") or ""

            if delta:
                raw_accum += delta
                # Only flush text once no <think> block is currently open —
                # this is what keeps raw reasoning out of the chat bubble.
                open_think = raw_accum.count("<think>") > raw_accum.count("</think>")
                if not open_think:
                    clean, _ = _strip_thinking_tags(raw_accum)
                    if len(clean) > emitted_len:
                        new_text = clean[emitted_len:]
                        emitted_len = len(clean)
                        got_any = True
                        yield new_text

            if data.get("done"):
                break

        if not got_any:
            _failure_count += 1
            _last_failure_time = time.time()
            print(f"⚠️ Empty stream from {model} (failure #{_failure_count})")
            return

        _failure_count = 0
        _last_success_time = time.time()

    except requests.exceptions.Timeout:
        _failure_count += 1
        _last_failure_time = time.time()
        print(f"⏱️ STREAM TIMEOUT #{_failure_count} — model={model}, timeout={timeout}s")
        if _failure_count >= 3:
            global _chat_model
            _chat_model = None
            print(
                f"🔄 Chat model reset after {_failure_count} failures — will re-detect"
            )
        return

    except requests.exceptions.ConnectionError:
        _failure_count += 1
        _last_failure_time = time.time()
        global _ollama_healthy, _last_health_check
        _ollama_healthy = False
        _last_health_check = 0.0
        print(f"🔌 STREAM CONNECTION ERROR #{_failure_count} — is Ollama running?")
        return

    except Exception as e:
        _failure_count += 1
        _last_failure_time = time.time()
        print(f"❌ LLM STREAM ERROR: {type(e).__name__}: {e}")
        return


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
        native_thinking = ""
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
            message = response.json().get("message", {})
            raw = message.get("content", "")
            # Newer Ollama versions return reasoning in a native field
            # instead of (or in addition to) inline <think> tags
            native_thinking = message.get("thinking", "") or ""

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

        if is_thinking or native_thinking:
            clean, thinking = _strip_thinking_tags(raw)
            if native_thinking:
                thinking = thinking + [native_thinking]
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
        "gpt-oss:20b": "Best deep brain — OpenAI open-weight, fits fully in 16GB VRAM",
        "qwen3:30b-a3b": "Best chat brain — MoE, strong reasoning, ~40 tok/s here",
        "qwen3:14b": "Lightweight chat brain fallback — fast, fits fully on GPU",
        "deepseek-r1:14b": "Reasoning fallback — proven, fits fully on GPU",
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
