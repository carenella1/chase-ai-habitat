"""
habitat/voice/kokoro_voices.py

Static catalog of Kokoro-82M's built-in voice pack, for the Settings page's
voice picker. Kept separate from local_tts.py (synthesis logic) and
voice_evolution.py (persona-drift logic) since this is just display/config
data consumed by both the backend and the settings template.

Voice ids are Kokoro's own naming convention: <lang><gender>_<name>
(af = American female, am = American male, bf = British female, bm =
British male). A voice not yet used on this machine downloads from
Hugging Face on first use, same as the two already wired up via
KOKORO_VOICE_MAP in local_tts.py.
"""

KOKORO_VOICE_CATALOG = [
    {"id": "af_heart", "label": "Heart", "gender": "female", "accent": "American"},
    {"id": "af_bella", "label": "Bella", "gender": "female", "accent": "American"},
    {"id": "af_nicole", "label": "Nicole", "gender": "female", "accent": "American"},
    {"id": "af_sky", "label": "Sky", "gender": "female", "accent": "American"},
    {"id": "af_sarah", "label": "Sarah", "gender": "female", "accent": "American"},
    {"id": "af_alloy", "label": "Alloy", "gender": "female", "accent": "American"},
    {"id": "af_aoede", "label": "Aoede", "gender": "female", "accent": "American"},
    {"id": "af_jessica", "label": "Jessica", "gender": "female", "accent": "American"},
    {"id": "af_kore", "label": "Kore", "gender": "female", "accent": "American"},
    {"id": "af_nova", "label": "Nova", "gender": "female", "accent": "American"},
    {"id": "af_river", "label": "River", "gender": "female", "accent": "American"},
    {"id": "am_adam", "label": "Adam", "gender": "male", "accent": "American"},
    {"id": "am_echo", "label": "Echo", "gender": "male", "accent": "American"},
    {"id": "am_eric", "label": "Eric", "gender": "male", "accent": "American"},
    {"id": "am_fenrir", "label": "Fenrir", "gender": "male", "accent": "American"},
    {"id": "am_liam", "label": "Liam", "gender": "male", "accent": "American"},
    {"id": "am_michael", "label": "Michael", "gender": "male", "accent": "American"},
    {"id": "am_onyx", "label": "Onyx", "gender": "male", "accent": "American"},
    {"id": "am_puck", "label": "Puck", "gender": "male", "accent": "American"},
    {"id": "am_santa", "label": "Santa", "gender": "male", "accent": "American"},
    {"id": "bf_alice", "label": "Alice", "gender": "female", "accent": "British"},
    {"id": "bf_emma", "label": "Emma", "gender": "female", "accent": "British"},
    {"id": "bf_isabella", "label": "Isabella", "gender": "female", "accent": "British"},
    {"id": "bf_lily", "label": "Lily", "gender": "female", "accent": "British"},
    {"id": "bm_daniel", "label": "Daniel", "gender": "male", "accent": "British"},
    {"id": "bm_fable", "label": "Fable", "gender": "male", "accent": "British"},
    {"id": "bm_george", "label": "George", "gender": "male", "accent": "British"},
    {"id": "bm_lewis", "label": "Lewis", "gender": "male", "accent": "British"},
]

KOKORO_VOICE_IDS = {v["id"] for v in KOKORO_VOICE_CATALOG}


def get_voice_meta(voice_id: str) -> dict | None:
    for v in KOKORO_VOICE_CATALOG:
        if v["id"] == voice_id:
            return v
    return None
