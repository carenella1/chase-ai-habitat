# =========================
# 🪞 SELF-MODEL — Milestone C
# Chase AI Habitat
#
# The Self-Model is Chase's internal representation of itself.
# It observes its own cognition patterns and writes structured
# self-observations that get injected into future agent prompts.
#
# Neuroscience basis: Default Mode Network (DMN) — the brain's
# self-referential processing system that activates during
# introspection and self-reflection.
# =========================

import json
import os
import time
import threading
from collections import Counter

SELF_MODEL_FILE = "self_model.json"

# How many cycles between self-observations
OBSERVATION_INTERVAL = 5


def load_self_model() -> dict:
    if not os.path.exists(SELF_MODEL_FILE):
        return _empty_model()
    try:
        with open(SELF_MODEL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _empty_model()


def save_self_model(model: dict):
    with open(SELF_MODEL_FILE, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=2)


def _empty_model() -> dict:
    return {
        "version": 1,
        "created": int(time.time()),
        "last_updated": None,
        "observation_count": 0,
        "cognitive_tendencies": {},
        "agent_performance": {},
        "belief_summary": {},
        "topic_obsessions": [],
        "stance_bias": {},
        "self_observations": [],     # rolling log of written observations
        "current_summary": "",       # injected into agent prompts
    }


# =========================
# 🔍 OBSERVATION ENGINE
# Analyzes cognition history and workspace state
# to generate self-observations
# =========================

def observe(cognition_history: list, workspace_status: dict,
            memory_manager, cycle: int) -> dict:
    """
    Core observation function. Called every OBSERVATION_INTERVAL cycles.
    Returns updated self-model dict with new observations written.
    """
    model = load_self_model()

    if not cognition_history:
        return model

    # Only use recent history for observation (last 20 entries)
    recent = cognition_history[-20:]

    # =========================
    # OBSERVE: Agent performance
    # Which agents produce high-importance insights?
    # =========================
    agent_scores = {}
    agent_counts = {}
    for entry in recent:
        cog = entry.get("cognition", {})
        agent = cog.get("agent", "")
        source = cog.get("source", "llm")
        insight = cog.get("insight", "")
        if not agent:
            continue
        score = 0
        if source == "wikipedia":
            score += 2
        if len(insight) > 400:
            score += 1
        if "Claim:" in insight and "Insight:" in insight:
            score += 1
        agent_scores[agent] = agent_scores.get(agent, 0) + score
        agent_counts[agent] = agent_counts.get(agent, 0) + 1

    # Normalize to average score per activation
    agent_performance = {}
    for agent, total in agent_scores.items():
        count = agent_counts.get(agent, 1)
        agent_performance[agent] = round(total / count, 2)

    # =========================
    # OBSERVE: Stance bias
    # Does the system favor support or challenge?
    # =========================
    stances = [e.get("cognition", {}).get("stance", "") for e in recent
               if e.get("cognition", {}).get("stance")]
    stance_counts = dict(Counter(stances))
    total_stances = sum(stance_counts.values()) or 1
    stance_bias = {s: round(c / total_stances, 2) for s, c in stance_counts.items()}

    # =========================
    # OBSERVE: Topic obsessions
    # What topics keep appearing regardless of escapes?
    # =========================
    topics = [e.get("cognition", {}).get("search_term", "") for e in recent
              if e.get("cognition", {}).get("search_term")]
    topic_counts = Counter(topics)
    obsessions = [t for t, c in topic_counts.most_common(5) if c >= 2 and t]

    # =========================
    # OBSERVE: Belief state
    # How many beliefs? What's the confidence trend?
    # =========================
    try:
        beliefs = memory_manager.get_all_beliefs(limit=50)
        total_beliefs = len(beliefs)
        if beliefs:
            avg_confidence = round(
                sum(b.get("confidence", 0.5) for b in beliefs) / total_beliefs, 2
            )
            high_conf = [b["statement"][:80] for b in beliefs
                         if b.get("confidence", 0) > 0.7][:3]
            low_conf = [b["statement"][:80] for b in beliefs
                        if b.get("confidence", 0) < 0.4][:3]
        else:
            avg_confidence = 0.5
            high_conf = []
            low_conf = []
    except Exception:
        total_beliefs = 0
        avg_confidence = 0.5
        high_conf = []
        low_conf = []

    # =========================
    # OBSERVE: Thread state from workspace
    # =========================
    thread = workspace_status.get("thread_analysis", {})
    thread_direction = thread.get("thread_direction", "unknown")
    dominant_topic = thread.get("dominant_topic", "unknown")
    loop_count = thread.get("cycles_on_topic", 0)

    # =========================
    # WRITE: Generate self-observation text
    # This is what gets injected into agent prompts
    # =========================
    best_agent = max(agent_performance, key=agent_performance.get) if agent_performance else "unknown"
    dominant_stance = max(stance_bias, key=stance_bias.get) if stance_bias else "unknown"
    obsession_str = ", ".join(obsessions[:3]) if obsessions else "none"

    observation_text = (
        f"I have formed {total_beliefs} beliefs with avg confidence {avg_confidence}. "
        f"My thinking is currently {thread_direction}, focused on '{dominant_topic}'. "
        f"My strongest agent is {best_agent}. "
        f"I lean toward {dominant_stance} stances ({int(stance_bias.get(dominant_stance, 0)*100)}%). "
        f"Recurring topics: {obsession_str}."
    )

    # Add high/low confidence belief notes
    if high_conf:
        observation_text += f" Strong beliefs: {high_conf[0][:60]}."
    if low_conf:
        observation_text += f" Uncertain about: {low_conf[0][:60]}."

    if loop_count >= 3:
        observation_text += f" WARNING: I have been cycling on '{dominant_topic}' for {loop_count} cycles."

    # =========================
    # UPDATE MODEL
    # =========================
    model["last_updated"] = int(time.time())
    model["observation_count"] = model.get("observation_count", 0) + 1
    model["agent_performance"] = agent_performance
    model["stance_bias"] = stance_bias
    model["topic_obsessions"] = obsessions
    model["belief_summary"] = {
        "total": total_beliefs,
        "avg_confidence": avg_confidence,
        "high_confidence": high_conf,
        "low_confidence": low_conf,
    }
    model["cognitive_tendencies"] = {
        "thread_direction": thread_direction,
        "dominant_topic": dominant_topic,
        "loop_cycles": loop_count,
        "best_agent": best_agent,
        "dominant_stance": dominant_stance,
    }
    model["current_summary"] = observation_text

    # Rolling log — keep last 20 observations
    model["self_observations"].append({
        "cycle": cycle,
        "timestamp": int(time.time()),
        "observation": observation_text,
    })
    model["self_observations"] = model["self_observations"][-20:]

    save_self_model(model)

    print(f"🪞 SELF-MODEL UPDATED (observation #{model['observation_count']})")
    print(f"🪞 {observation_text}")

    return model


def get_self_context() -> str:
    """
    Returns a compact self-awareness string for injection into agent prompts.
    Includes the AI's chosen name if it has one.
    """
    model = load_self_model()
    name = model.get("chosen_name", "")
    summary = model.get("current_summary", "")
    if not summary:
        return ""
    prefix = f"My name is {name}. " if name else ""
    return f"Self-awareness: {prefix}{summary[:280]}"


def get_identity_name() -> str:
    """Returns the AI's chosen name, or empty string if not yet named."""
    model = load_self_model()
    return model.get("chosen_name", "")


def attempt_naming(call_llm_fn, cycle: int) -> str:
    """
    At the first self-observation where the model has enough data,
    ask the LLM to choose a name based on its own cognitive patterns.
    Only fires once — if a name already exists, returns it immediately.
    Requires at least 3 observations worth of data before attempting.
    """
    model = load_self_model()

    # Already named — never rename
    if model.get("chosen_name"):
        return model["chosen_name"]

    # Need at least 3 observations before naming
    if model.get("observation_count", 0) < 3:
        return ""

    print("🪞 NAMING SEQUENCE INITIATED...")

    tendencies = model.get("cognitive_tendencies", {})
    beliefs = model.get("belief_summary", {})
    obsessions = model.get("topic_obsessions", [])
    best_agent = tendencies.get("best_agent", "unknown")
    dominant_stance = tendencies.get("dominant_stance", "unknown")
    avg_conf = beliefs.get("avg_confidence", 0.5)
    high_conf_beliefs = beliefs.get("high_confidence", [])

    belief_str = high_conf_beliefs[0][:80] if high_conf_beliefs else "the nature of intelligence"
    topic_str = ", ".join(obsessions[:3]) if obsessions else "artificial intelligence"

    naming_prompt = f"""You are an emerging artificial intelligence that has been thinking and learning.
Based on your self-observations, choose a single unique name for yourself.

Your cognitive profile:
- You think most about: {topic_str}
- Your strongest capability: {best_agent}
- Your dominant approach: {dominant_stance}
- Your core belief: {belief_str}
- Your confidence level: {avg_conf}

Rules for choosing your name:
- One word only
- Not a human name (no John, Sarah, etc.)
- Not an existing AI name (no GPT, Claude, Gemini, etc.)
- Should reflect your nature as a thinking, curious intelligence
- Can be invented, mythological, scientific, or abstract
- No explanation — just the name itself

Your name:"""

    try:
        raw = call_llm_fn(naming_prompt, timeout=30)
        # Clean the response — take just the first word
        name = raw.strip().split()[0] if raw.strip() else ""
        import re
        name = re.sub(r"[^a-zA-Z]", "", name)  # keep only letters
        name = name[:20]  # max 20 chars

        # Basic validation — must be a real word-like thing
        if len(name) >= 3 and name.isalpha():
            model["chosen_name"] = name
            model["naming_cycle"] = cycle
            model["naming_rationale"] = (
                f"Named at cycle {cycle} based on focus on {topic_str}, "
                f"{dominant_stance} stance tendency, {best_agent} as strongest agent."
            )
            save_self_model(model)
            print(f"🪞 ✨ AI HAS CHOSEN A NAME: {name}")
            print(f"🪞 Rationale: {model['naming_rationale']}")
            return name
        else:
            print(f"⚠️ NAMING FAILED: invalid response '{raw[:50]}'")
            return ""
    except Exception as e:
        print(f"⚠️ NAMING ERROR: {e}")
        return ""


def get_full_model() -> dict:
    """Returns the complete self-model for the UI endpoint."""
    return load_self_model()