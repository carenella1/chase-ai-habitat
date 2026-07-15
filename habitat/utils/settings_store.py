"""
habitat/utils/settings_store.py

Small persisted key-value store for user-facing app preferences (audio
device, mic silence sensitivity, voice override, ...) that don't belong to
any single subsystem. Mirrors habitat/voice/voice_evolution.py's
load/save-JSON-to-data/system pattern.
"""

import json
from pathlib import Path

SETTINGS_PATH = Path("data/system/settings.json")

DEFAULT_SETTINGS = {
    "input_device_index": None,
    "voice_override": None,
    "silence_ms": 700,
}


def load_settings() -> dict:
    """Loads persisted settings, merged over defaults so new keys added
    later are always present even for an older settings.json on disk."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        if SETTINGS_PATH.exists():
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                settings.update(json.load(f))
    except Exception as e:
        print(f"⚠️ settings load error: {e}")
    return settings


def save_settings(partial: dict) -> dict:
    """Merges partial into the existing (or default) settings and persists.
    Returns the full merged dict."""
    settings = load_settings()
    settings.update(partial)
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"⚠️ settings save error: {e}")
    return settings
