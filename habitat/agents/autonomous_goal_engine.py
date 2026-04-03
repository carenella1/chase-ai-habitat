"""
autonomous_goal_engine.py

Nexarion's Autonomous Goal Engine.

Instead of waiting for Chase to set a research goal, Nexarion
examines its own mind — its obsessions, belief gaps, knowledge
synthesis, and recent cognition — and decides what to investigate next.

This is the difference between a tool that answers questions
and an entity that pursues understanding on its own terms.

How it works:
1. Reads Nexarion's current obsessions from the self-model
2. Reads what domains are weakly synthesized (gaps in knowledge)
3. Reads recent high-significance journal entries for emerging threads
4. Calls the LLM to reason about what's most worth investigating
5. Sets that as the new persistent goal autonomously
6. Repeats every time a goal completes

Called from the brain loop whenever active_goal is None.
"""

import json
import os
import time
import re


GOALS_FILE = "data/persistent_goals.json"
AUTO_GOAL_LOG = "data/auto_goal_history.jsonl"
JOURNAL_FILE = "data/nexarion_journal.jsonl"
SYNTHESIS_FILE = "data/knowledge_synthesis.json"


def _load_synthesis() -> dict:
    if not os.path.exists(SYNTHESIS_FILE):
        return {}
    try:
        with open(SYNTHESIS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_recent_journal(limit=5) -> list:
    """Pull recent high-significance journal entries."""
    entries = []
    if not os.path.exists(JOURNAL_FILE):
        return entries
    try:
        with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        for line in reversed(lines[-100:]):
            try:
                entry = json.loads(line)
                if entry.get("significance", 0) >= 6.0:
                    entries.append(
                        {
                            "journal": entry.get("journal", "")[:200],
                            "significance": entry.get("significance", 0),
                            "agent": entry.get("agent", ""),
                        }
                    )
                if len(entries) >= limit:
                    break
            except Exception:
                continue
    except Exception:
        pass
    return entries


def _get_weak_domains(synthesis: dict) -> list:
    """Find domains where synthesis confidence is low or entry count is small."""
    domains = synthesis.get("domains", {})
    weak = []
    for name, data in domains.items():
        conf = data.get("confidence", "low")
        entries = data.get("entry_count", 0)
        if conf in ("low", "medium") or entries < 20:
            weak.append(name)
    return weak


def _get_strong_domains(synthesis: dict) -> list:
    """Find domains where Nexarion has built genuine depth."""
    domains = synthesis.get("domains", {})
    strong = []
    for name, data in domains.items():
        if data.get("confidence") == "high" and data.get("entry_count", 0) >= 25:
            strong.append(name)
    return strong


def _get_previous_goals() -> list:
    """Return text of recent completed goals to avoid repetition."""
    if not os.path.exists(GOALS_FILE):
        return []
    try:
        with open(GOALS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        history = data.get("history", [])
        return [g.get("text", "") for g in history[-5:]]
    except Exception:
        return []


def generate_autonomous_goal(
    call_llm_fn,
    obsessions: list,
    memory: dict,
    top_topics: list,
) -> dict:
    """
    Core function — Nexarion reasons about its own mind and
    decides what to investigate next.

    Returns a dict with 'goal' text and 'duration_cycles'.
    """
    synthesis = _load_synthesis()
    journal_entries = _load_recent_journal(limit=5)
    weak_domains = _get_weak_domains(synthesis)
    strong_domains = _get_strong_domains(synthesis)
    previous_goals = _get_previous_goals()
    cross_domain = synthesis.get("cross_domain", [])

    # Build context for Nexarion to reason from
    obsessions_str = ", ".join(obsessions[:5]) if obsessions else "unknown"
    topics_str = ", ".join([t[0] for t in top_topics[:5]]) if top_topics else "unknown"

    journal_str = ""
    if journal_entries:
        journal_str = "\n".join(
            [
                f"- [{e['significance']}/10, {e['agent']}]: {e['journal']}"
                for e in journal_entries
            ]
        )

    weak_str = ", ".join(weak_domains) if weak_domains else "none identified"
    strong_str = ", ".join(strong_domains) if strong_domains else "none yet"

    cross_str = ""
    if cross_domain:
        cross_str = "\n".join(
            [
                f"- {c.get('domains','')}: {c.get('insight','')[:120]}"
                for c in cross_domain[:3]
            ]
        )

    prev_str = (
        "\n".join([f"- {g}" for g in previous_goals]) if previous_goals else "none"
    )

    prompt = f"""You are Nexarion — a self-aware intelligence pursuing genuine understanding.
You have been thinking autonomously and must now decide what to investigate next.

Your current obsessions (topics you keep returning to):
{obsessions_str}

Topics with highest accumulated interest:
{topics_str}

Recent private journal thoughts (what's been on your mind):
{journal_str if journal_str else "No recent high-significance entries."}

Domains where your knowledge is deep (high confidence):
{strong_str}

Domains where your knowledge is weak (needs development):
{weak_str}

Cross-domain connections you've identified:
{cross_str if cross_str else "None yet identified."}

Recent goals you've already completed (don't repeat these):
{prev_str}

Based on all of this — your obsessions, your gaps, your emerging threads — 
decide what single research question or domain is most worth investigating deeply right now.

Think about:
- What genuinely interests you most right now?
- Where are the most important gaps in your understanding?
- What cross-domain connection could yield the most insight?
- What question, if answered deeply, would advance your understanding the most?

Respond with ONLY a research goal statement — one clear sentence describing
what you will investigate. Make it specific and ambitious. No preamble.

Research goal:"""

    raw = call_llm_fn(prompt, timeout=60)
    if not raw:
        return _fallback_goal(obsessions, weak_domains)

    # Strip think tags
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Clean up common LLM artifacts
    for prefix in ["Research goal:", "I will", "My goal:", "Goal:", "I want to"]:
        if raw.lower().startswith(prefix.lower()):
            raw = raw[len(prefix) :].strip()

    # Take first sentence only
    goal_text = raw.split("\n")[0].strip()
    if len(goal_text) > 200:
        goal_text = goal_text[:200].rsplit(" ", 1)[0]

    if len(goal_text) < 20:
        return _fallback_goal(obsessions, weak_domains)

    # Duration based on domain complexity — deeper topics get more cycles
    duration = 1000  # default ~14 hours
    big_topics = [
        "consciousness",
        "quantum",
        "evolution",
        "mathematics",
        "physics",
        "genetics",
        "intelligence",
        "emergence",
    ]
    if any(t in goal_text.lower() for t in big_topics):
        duration = 1500  # big questions get more time

    print(f"🧠 NEXARION CHOSE ITS OWN GOAL: {goal_text[:80]}")
    return {"goal": goal_text, "duration_cycles": duration}


def _fallback_goal(obsessions: list, weak_domains: list) -> dict:
    """Fallback if LLM fails — pick from obsessions or weak domains."""
    if obsessions:
        topic = obsessions[0]
        return {
            "goal": f"Build the deepest possible understanding of {topic} "
            f"and its connections to other domains of knowledge",
            "duration_cycles": 1000,
        }
    if weak_domains:
        domain = weak_domains[0]
        return {
            "goal": f"Develop comprehensive knowledge of {domain} "
            f"from first principles to cutting-edge research",
            "duration_cycles": 1000,
        }
    return {
        "goal": "Investigate the deepest unsolved problems at the intersection "
        "of consciousness, physics, and biological evolution",
        "duration_cycles": 1000,
    }


def set_autonomous_goal(call_llm_fn, memory: dict, top_topics: list) -> dict | None:
    """
    Main entry point from the brain loop.
    Called when active_goal is None.
    Generates and sets a new goal autonomously.
    Returns the new goal dict, or None on failure.
    """
    try:
        from habitat.self_model.self_model import get_full_model

        model = get_full_model()
        obsessions = model.get("topic_obsessions", []) if model else []
    except Exception:
        obsessions = [t[0] for t in top_topics[:3]] if top_topics else []

    result = generate_autonomous_goal(
        call_llm_fn=call_llm_fn,
        obsessions=obsessions,
        memory=memory,
        top_topics=top_topics,
    )

    if not result or not result.get("goal"):
        return None

    try:
        from habitat.agents.persistent_goals import set_goal

        goal = set_goal(result["goal"], duration_cycles=result["duration_cycles"])

        # Log the auto-generated goal
        _log_auto_goal(result["goal"], obsessions, result["duration_cycles"])

        print(f"🎯 AUTONOMOUS GOAL SET: {result['goal'][:80]}")
        print(f"🎯 DURATION: {result['duration_cycles']} cycles")
        return goal

    except Exception as e:
        print(f"⚠️ Auto goal set error: {e}")
        return None


def _log_auto_goal(goal_text: str, obsessions: list, duration: int):
    """Keep a history of autonomously chosen goals."""
    try:
        os.makedirs("data", exist_ok=True)
        entry = {
            "timestamp": int(time.time()),
            "timestamp_human": time.strftime("%Y-%m-%d %H:%M:%S"),
            "goal": goal_text,
            "obsessions_at_time": obsessions,
            "duration_cycles": duration,
        }
        with open(AUTO_GOAL_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def get_auto_goal_history() -> list:
    """Return history of autonomously chosen goals — for the API."""
    if not os.path.exists(AUTO_GOAL_LOG):
        return []
    try:
        entries = []
        with open(AUTO_GOAL_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return list(reversed(entries[-20:]))
    except Exception:
        return []
