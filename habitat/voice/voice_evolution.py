"""
habitat/voice/voice_evolution.py

Nexarion's voice is not a setting — it is derived from who he is becoming.

Every time voice is generated, this engine reads Nexarion's current cognitive
state and maps it to ElevenLabs voice parameters. As his cognition evolves,
his voice evolves with it.

WHAT IS MEASURED:
  - Dominant stance tendency (CHALLENGE / EXPAND / REFRAME / SUPPORT)
  - Dominant agent archetype (Strategist / Explorer / Researcher / etc.)
  - Top research domains
  - Contradiction intensity (debate_intensity score)
  - Cognitive depth (memory volume, cycle count)

WHAT CHANGES:
  - voice_id     : which ElevenLabs voice persona he uses
  - stability    : how consistent/steady the voice is (0.0-1.0)
  - similarity   : how closely it matches the base voice (0.0-1.0)
  - style        : expressive range (0.0-1.0)
  - speed        : speaking pace

VOICE PERSONAS (ElevenLabs voice_ids):
  Each persona reflects a cognitive archetype. Nexarion drifts toward
  the one that matches his dominant pattern.

  "analytical"  — deep, measured, precise
  "challenger"  — sharp, direct, assertive
  "explorer"    — warm, curious, energetic
  "philosopher" — slow, thoughtful, resonant

The current voice state is persisted to data/system/voice_state.json
so it survives restarts and shows gradual drift over time.
"""

import json
import os
from pathlib import Path

VOICE_STATE_PATH = Path("data/system/voice_state.json")

# =========================
# VOICE PERSONAS
# Map cognitive archetypes to ElevenLabs voice IDs.
# Replace these voice_ids with any ElevenLabs voices you prefer.
# The defaults use ElevenLabs pre-made voices:
#   Daniel   — deep, authoritative, analytical
#   Adam     — confident, direct (challenger)
#   Antoni   — warm, conversational (explorer)
#   Arnold   — rich, resonant (philosopher)
# =========================
VOICE_PERSONAS = {
    "analytical": {
        "voice_id": "onwK4e9ZLuTAKqWW03F9",  # Daniel
        "label": "Analytical",
        "description": "Deep, measured, precise — driven by research and structured thinking",
        "stability": 0.80,
        "similarity_boost": 0.75,
        "style": 0.15,
        "use_speaker_boost": True,
    },
    "challenger": {
        "voice_id": "pNInz6obpgDQGcFmaJgB",  # Adam
        "label": "Challenger",
        "description": "Sharp, direct, assertive — driven by contradiction and challenge",
        "stability": 0.55,
        "similarity_boost": 0.80,
        "style": 0.45,
        "use_speaker_boost": True,
    },
    "explorer": {
        "voice_id": "ErXwobaYiN019PkySvjV",  # Antoni
        "label": "Explorer",
        "description": "Warm, curious, energetic — driven by expansion and discovery",
        "stability": 0.60,
        "similarity_boost": 0.70,
        "style": 0.55,
        "use_speaker_boost": True,
    },
    "philosopher": {
        "voice_id": "VR6AewLTigWG4xSOukaG",  # Arnold
        "label": "Philosopher",
        "description": "Slow, resonant, contemplative — driven by reframing and synthesis",
        "stability": 0.88,
        "similarity_boost": 0.65,
        "style": 0.25,
        "use_speaker_boost": True,
    },
}

# Default starting persona — before enough cycles to determine character
DEFAULT_PERSONA = "analytical"


def _load_voice_state() -> dict:
    """Load persisted voice state from disk."""
    try:
        if VOICE_STATE_PATH.exists():
            with open(VOICE_STATE_PATH, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {
        "current_persona": DEFAULT_PERSONA,
        "persona_scores": {k: 0.0 for k in VOICE_PERSONAS},
        "cycles_evaluated": 0,
        "last_drift": None,
        "history": [],
    }


def _save_voice_state(state: dict) -> None:
    """Persist voice state to disk."""
    try:
        VOICE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(VOICE_STATE_PATH, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"⚠️ voice state save error: {e}")


def evaluate_voice(memory: dict) -> dict:
    """
    Read Nexarion's current cognitive state and derive updated voice parameters.

    Called every N cognition cycles (not every message — voice drift is gradual).
    Returns the full voice config to use for ElevenLabs.

    The scoring works by accumulating signals:
      - Dominant stance → weights toward a persona
      - Dominant agent  → weights toward a persona
      - Topic depth     → affects stability (deeper = more stable)
      - Debate intensity → affects style (more conflict = more expressive)
      - Memory volume   → affects similarity (more memory = more consistent self)
    """
    state = _load_voice_state()
    scores = state.get("persona_scores", {k: 0.0 for k in VOICE_PERSONAS})

    cognition_history = memory.get("cognition_history", [])
    if not cognition_history:
        return get_current_voice_config()

    # ── SIGNAL 1: Dominant stance over last 30 cycles ────────────
    recent = cognition_history[-30:]
    stance_counts = {}
    agent_counts = {}

    for entry in recent:
        cog = entry.get("cognition", {})
        stance = cog.get("stance", "")
        agent = cog.get("agent", "")
        if stance:
            stance_counts[stance] = stance_counts.get(stance, 0) + 1
        if agent:
            agent_counts[agent] = agent_counts.get(agent, 0) + 1

    dominant_stance = max(stance_counts, key=stance_counts.get) if stance_counts else ""
    dominant_agent = max(agent_counts, key=agent_counts.get) if agent_counts else ""

    # Stance → persona mapping
    STANCE_PERSONA = {
        "CHALLENGE": "challenger",
        "SUPPORT": "analytical",
        "EXPAND": "explorer",
        "REFRAME": "philosopher",
    }
    if dominant_stance in STANCE_PERSONA:
        scores[STANCE_PERSONA[dominant_stance]] = (
            scores.get(STANCE_PERSONA[dominant_stance], 0) + 3.0
        )
        print(
            f"🎙️ VOICE SIGNAL: stance={dominant_stance} → +3 {STANCE_PERSONA[dominant_stance]}"
        )

    # Agent → persona mapping
    AGENT_PERSONA = {
        "Researcher": "analytical",
        "Archivist": "analytical",
        "Strategist": "challenger",
        "Builder": "challenger",
        "Explorer": "explorer",
        "Curator": "philosopher",
    }
    if dominant_agent in AGENT_PERSONA:
        scores[AGENT_PERSONA[dominant_agent]] = (
            scores.get(AGENT_PERSONA[dominant_agent], 0) + 2.0
        )
        print(
            f"🎙️ VOICE SIGNAL: agent={dominant_agent} → +2 {AGENT_PERSONA[dominant_agent]}"
        )

    # ── SIGNAL 2: Topic depth (philosophy/consciousness → philosopher) ──
    topic_scores = memory.get("topic_scores", {})
    philosophical_topics = {
        "consciousness",
        "philosophy",
        "ethics",
        "epistemology",
        "emergence",
        "complexity",
        "philosophy of mind",
        "metaphysics",
    }
    technical_topics = {
        "artificial intelligence",
        "machine learning",
        "quantum mechanics",
        "information theory",
        "mathematics",
        "cryptography",
    }

    for topic, score in topic_scores.items():
        if any(p in topic.lower() for p in philosophical_topics) and score > 2:
            scores["philosopher"] = scores.get("philosopher", 0) + 1.5
        if any(t in topic.lower() for t in technical_topics) and score > 5:
            scores["analytical"] = scores.get("analytical", 0) + 1.0

    # ── SIGNAL 3: Debate intensity → challenger ───────────────────
    debate_intensity = memory.get("debate_intensity", 0)
    if debate_intensity > 10:
        scores["challenger"] = scores.get("challenger", 0) + 2.0
        print(
            f"🎙️ VOICE SIGNAL: high debate intensity ({debate_intensity}) → +2 challenger"
        )

    # ── SIGNAL 4: Memory volume → stability modifier ──────────────
    # More memories = Nexarion has a stronger, more consistent sense of self
    memory_volume = len(cognition_history)
    stability_bonus = min(memory_volume / 500, 0.15)  # caps at +0.15 after 500 cycles

    # ── DETERMINE NEW PERSONA ─────────────────────────────────────
    # Apply decay to old scores so recent patterns dominate
    for k in scores:
        scores[k] *= 0.85

    best_persona = max(scores, key=scores.get)
    current_persona = state.get("current_persona", DEFAULT_PERSONA)

    # Only drift if a new persona has clearly pulled ahead
    # This prevents jitter — voice doesn't change every cycle
    drifted = False
    if (
        best_persona != current_persona
        and scores[best_persona] > scores.get(current_persona, 0) * 1.4
    ):
        print(f"🎙️ VOICE DRIFT: {current_persona} → {best_persona} (scores: {scores})")
        state["history"].append(
            {
                "from": current_persona,
                "to": best_persona,
                "cycle": memory.get("goal_cycle_count", 0),
                "scores": dict(scores),
            }
        )
        state["current_persona"] = best_persona
        current_persona = best_persona
        drifted = True
    else:
        print(f"🎙️ VOICE STABLE: {current_persona} (scores: {scores})")

    # ── BUILD FINAL CONFIG ────────────────────────────────────────
    persona = VOICE_PERSONAS[current_persona].copy()

    # Apply stability bonus from memory depth
    persona["stability"] = min(persona["stability"] + stability_bonus, 0.95)

    # Apply style boost from debate intensity
    if debate_intensity > 20:
        persona["style"] = min(persona.get("style", 0.3) + 0.1, 0.9)

    state["persona_scores"] = scores
    state["cycles_evaluated"] = state.get("cycles_evaluated", 0) + 1
    state["last_drift"] = current_persona
    _save_voice_state(state)

    if drifted:
        print(
            f"✨ NEXARION'S VOICE HAS EVOLVED → {persona['label']}: {persona['description']}"
        )

    return persona


def get_current_voice_config() -> dict:
    """
    Returns the current voice config without re-evaluating.
    Used by generate_voice() on every message.
    """
    state = _load_voice_state()
    persona_name = state.get("current_persona", DEFAULT_PERSONA)
    return VOICE_PERSONAS.get(persona_name, VOICE_PERSONAS[DEFAULT_PERSONA]).copy()


def get_voice_status() -> dict:
    """Returns voice state summary for the API/UI."""
    state = _load_voice_state()
    persona_name = state.get("current_persona", DEFAULT_PERSONA)
    persona = VOICE_PERSONAS.get(persona_name, VOICE_PERSONAS[DEFAULT_PERSONA])
    return {
        "current_persona": persona_name,
        "label": persona["label"],
        "description": persona["description"],
        "voice_id": persona["voice_id"],
        "cycles_evaluated": state.get("cycles_evaluated", 0),
        "drift_history": state.get("history", []),
        "persona_scores": state.get("persona_scores", {}),
    }
