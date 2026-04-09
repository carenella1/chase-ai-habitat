"""
nex_brain_setup.py  —  Brain Diagnostic & Setup

Run this once to:
  1. Check that Ollama is running and healthy
  2. See what models are installed
  3. Get exact commands to install the recommended models
  4. Verify GPU (RTX 4070 Ti SUPER) is being used
  5. Test the chat and deep brain with a real prompt

HOW TO RUN:
  In your project folder:
    python nex_brain_setup.py

Or from the Habitat sandbox tab.
"""

import requests
import subprocess
import sys
import json
import time

OLLAMA_BASE = "http://localhost:11434"

# ─────────────────────────────────────────────
# COLOR OUTPUT (Windows CMD compatible)
# ─────────────────────────────────────────────


def ok(msg):
    print(f"  [OK]  {msg}")


def warn(msg):
    print(f"  [!!]  {msg}")


def err(msg):
    print(f"  [XX]  {msg}")


def info(msg):
    print(f"  [--]  {msg}")


def head(msg):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")


# ─────────────────────────────────────────────
# CHECK 1: OLLAMA RUNNING
# ─────────────────────────────────────────────


def check_ollama():
    head("CHECK 1: Ollama Service")
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        if r.status_code == 200:
            ok("Ollama is running and responding")
            return True
        else:
            err(f"Ollama returned status {r.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        err("Ollama is NOT running")
        warn("Fix: Open a terminal and run:  ollama serve")
        warn("Or: Search for 'Ollama' in your Start menu and launch it")
        return False
    except Exception as e:
        err(f"Unexpected error: {e}")
        return False


# ─────────────────────────────────────────────
# CHECK 2: INSTALLED MODELS
# ─────────────────────────────────────────────


def check_models():
    head("CHECK 2: Installed Models")

    try:
        r = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        models = r.json().get("models", [])
    except Exception:
        err("Cannot get model list — is Ollama running?")
        return []

    if not models:
        err("No models installed!")
        warn("You need to install at least one model for NEX to work.")
        print()
        print("  REQUIRED — run these commands in a terminal:")
        print()
        print("    Chat brain (pick ONE):")
        print("    > ollama pull qwen3:14b          # Recommended, ~8.5GB VRAM, fast")
        print("    > ollama pull gemma4:27b          # Alternative, ~15GB VRAM")
        print()
        print("    Deep brain (pick ONE):")
        print("    > ollama pull qwen3:32b           # Recommended, best reasoning")
        print("    > ollama pull deepseek-r1:32b     # Alternative, proven quality")
        print()
        return []

    ok(f"Found {len(models)} model(s) installed:")
    for m in models:
        size_gb = m.get("size", 0) / 1e9
        print(f"    • {m['name']}  ({size_gb:.1f} GB)")

    # Check for recommended models
    names = [m["name"] for m in models]
    names_str = " ".join(names).lower()

    print()
    print("  Model recommendations for your RTX 4070 Ti SUPER (16GB VRAM):")
    print()

    # Chat brain check
    has_good_chat = any(
        n in names_str for n in ["qwen3:14b", "qwen3:8b", "gemma4", "llama3"]
    )
    if has_good_chat:
        ok("Chat brain: good model available")
    else:
        warn("Chat brain: recommend installing qwen3:14b")
        print("    > ollama pull qwen3:14b")

    # Deep brain check
    has_good_deep = any(n in names_str for n in ["qwen3:32b", "deepseek-r1:32b"])
    if has_good_deep:
        ok("Deep brain: good model available")
    else:
        warn("Deep brain: recommend installing qwen3:32b")
        print("    > ollama pull qwen3:32b")

    # Thinking model check
    has_thinking = any(n in names_str for n in ["deepseek-r1", "qwen3"])
    if has_thinking:
        ok("Reasoning model: available (chain-of-thought enabled)")
    else:
        warn("No reasoning model — Nex's deep thinking will be weaker")

    return names


# ─────────────────────────────────────────────
# CHECK 3: GPU USAGE
# ─────────────────────────────────────────────


def check_gpu():
    head("CHECK 3: GPU — RTX 4070 Ti SUPER")

    # Check nvidia-smi
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            line = result.stdout.strip()
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                name, total, used, util = parts[0], parts[1], parts[2], parts[3]
                ok(f"GPU detected: {name}")
                ok(f"VRAM: {used}MB used / {total}MB total")
                ok(f"Utilization: {util}%")

                total_mb = int(total)
                used_mb = int(used)
                free_mb = total_mb - used_mb

                if free_mb > 8000:
                    ok(f"{free_mb}MB VRAM free — enough for qwen3:14b chat brain")
                elif free_mb > 4000:
                    warn(f"Only {free_mb}MB VRAM free — qwen3:8b recommended")
                else:
                    warn(f"Low VRAM ({free_mb}MB) — close other GPU applications")

                # Check if Ollama is using GPU
                if used_mb > 1000:
                    ok("Ollama appears to be using GPU (VRAM consumed)")
                else:
                    warn("Ollama may be running on CPU only")
                    warn("Fix: In llm_router.py, ensure num_gpu=-1 in options")
                    warn("Also check: OLLAMA_NUM_GPU=999 environment variable")
            return True
        else:
            warn("nvidia-smi found but returned an error")
    except FileNotFoundError:
        warn("nvidia-smi not found in PATH — trying alternative check")
    except Exception as e:
        warn(f"GPU check error: {e}")

    # Alternative: check via Ollama ps
    try:
        r = requests.get(f"{OLLAMA_BASE}/api/ps", timeout=5)
        if r.status_code == 200:
            data = r.json()
            models_running = data.get("models", [])
            if models_running:
                for m in models_running:
                    name = m.get("name", "?")
                    size = m.get("size", 0) / 1e9
                    info(f"Running: {name} ({size:.1f}GB)")
            else:
                info("No models currently loaded in Ollama")
    except Exception:
        pass

    return False


# ─────────────────────────────────────────────
# CHECK 4: LIVE CHAT TEST
# ─────────────────────────────────────────────


def check_chat_test(model: str):
    head(f"CHECK 4: Live Chat Test — {model}")

    use_chat_api = any(
        n in model.lower() for n in ["gemma", "qwen3", "llama3", "mistral"]
    )

    info(f"Sending test prompt to {model}...")
    start = time.time()

    try:
        if use_chat_api:
            r = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "user", "content": "Say exactly: BRAIN ONLINE"}
                    ],
                    "stream": False,
                    "options": {
                        "num_predict": 20,
                        "temperature": 0.1,
                        "num_gpu": -1,
                    },
                },
                timeout=60,
            )
            response = r.json().get("message", {}).get("content", "")
        else:
            r = requests.post(
                f"{OLLAMA_BASE}/api/generate",
                json={
                    "model": model,
                    "prompt": "Say exactly: BRAIN ONLINE",
                    "stream": False,
                    "options": {
                        "num_predict": 20,
                        "temperature": 0.1,
                        "num_gpu": -1,
                    },
                },
                timeout=60,
            )
            response = r.json().get("response", "")

        elapsed = time.time() - start

        if response and response.strip():
            ok(f"Response received in {elapsed:.1f}s: '{response.strip()[:60]}'")
            if elapsed < 5:
                ok("Speed: FAST (GPU is working)")
            elif elapsed < 20:
                ok("Speed: Normal")
            else:
                warn(f"Speed: Slow ({elapsed:.0f}s) — check GPU usage")
            return True
        else:
            err("Empty response — model may have crashed")
            return False

    except requests.exceptions.Timeout:
        err(f"Timeout after 60s — model may be loading or GPU is not engaged")
        warn("If this is the first run, wait 30s and try again (model loading)")
        return False
    except Exception as e:
        err(f"Error: {e}")
        return False


# ─────────────────────────────────────────────
# CHECK 5: NEX INTEGRATION
# ─────────────────────────────────────────────


def check_nex_integration():
    head("CHECK 5: NEX Integration Files")

    import os

    files_to_check = [
        ("llm_router.py", "LLM router — brain routing logic"),
        ("run_ui.py", "Main Flask server"),
        ("nex_trainer.py", "Continuous knowledge reinforcement"),
        ("structured_memory.py", "Phase 2 memory system"),
        ("knowledge_graph.py", "Phase 5 knowledge graph"),
        ("self_optimizer.py", "Phase 3 agent self-improvement"),
    ]

    all_ok = True
    for fname, desc in files_to_check:
        if os.path.exists(fname):
            size = os.path.getsize(fname)
            ok(f"{fname} ({size:,} bytes) — {desc}")
        else:
            warn(f"{fname} — MISSING — {desc}")
            all_ok = False

    return all_ok


# ─────────────────────────────────────────────
# ENVIRONMENT VARIABLE RECOMMENDATIONS
# ─────────────────────────────────────────────


def show_env_recommendations():
    head("RECOMMENDATIONS: Environment Variables")

    print("  Set these environment variables to maximize GPU performance.")
    print("  In Windows: Search 'Environment Variables' > System Variables > New")
    print()
    print("  OLLAMA_NUM_GPU=999")
    print("    Forces Ollama to use all available GPU layers")
    print()
    print("  OLLAMA_NUM_PARALLEL=2")
    print("    Allows 2 simultaneous requests (chat + deep cognition)")
    print()
    print("  OLLAMA_FLASH_ATTENTION=1")
    print("    Enables flash attention — faster and uses less VRAM")
    print()
    print("  OLLAMA_MAX_LOADED_MODELS=2")
    print("    Keeps both chat and deep brain loaded simultaneously")
    print("    WARNING: Both models at once need ~25GB VRAM")
    print("    With 16GB VRAM: only set this if using smaller models")
    print()
    print("  To set for current session (PowerShell):")
    print("    $env:OLLAMA_NUM_GPU=999")
    print("    $env:OLLAMA_FLASH_ATTENTION=1")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────


def main():
    print()
    print("=" * 60)
    print("  NEX BRAIN DIAGNOSTIC & SETUP")
    print("  RTX 4070 Ti SUPER + Ryzen 7 7800X3D")
    print("=" * 60)

    ollama_ok = check_ollama()
    if not ollama_ok:
        print(
            "\n⛔ Ollama is not running. Start Ollama first, then re-run this script."
        )
        return

    installed = check_models()
    check_gpu()

    if installed:
        # Test the first available chat model
        chat_priority = [
            "qwen3:14b",
            "qwen3:8b",
            "gemma4:27b",
            "gemma4:26b",
            "llama3.1:8b",
        ]
        chat_model = None
        for p in chat_priority:
            if any(p.split(":")[0] in m for m in installed):
                chat_model = next(m for m in installed if p.split(":")[0] in m)
                break
        if not chat_model and installed:
            chat_model = installed[0]

        if chat_model:
            check_chat_test(chat_model)

    check_nex_integration()
    show_env_recommendations()

    print()
    print("=" * 60)
    print("  DIAGNOSTIC COMPLETE")
    print()
    print("  NEXT STEPS:")
    print("  1. Install recommended models (commands shown above)")
    print("  2. Copy llm_router.py and nex_trainer.py to your project root")
    print("  3. In run_ui.py, add this near the top:")
    print()
    print("       from nex_trainer import nex_trainer")
    print("       from llm_router import warmup_models")
    print("       warmup_models()  # Add this after app is created")
    print()
    print("  4. In the cognition loop (where cycles run), add:")
    print()
    print("       nex_trainer.on_cycle(cycle, call_llm, call_llm_deep)")
    print()
    print("  5. Set the environment variables above for max GPU performance")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
