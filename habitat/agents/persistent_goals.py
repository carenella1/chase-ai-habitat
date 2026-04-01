"""
persistent_goals.py

Nexarion's Persistent Goal System.

Allows Chase to set a research agenda that Nexarion pursues
autonomously across every cognition cycle — not just for 10 cycles
but for days, until explicitly changed.

When a persistent goal is active:
- Every brain cycle contributes evidence toward it
- The goal context feeds into every cognition prompt
- Progress is tracked and journaled
- Nexarion initiates conversations about breakthroughs

Usage from chat:
    "I want you to spend the next week building the deepest
     possible understanding of cancer immunotherapy"
    → Nexarion sets this as its persistent goal and pursues it

Usage in brain loop:
    from habitat.agents.persistent_goals import get_active_goal, record_progress
    goal = get_active_goal()
    if goal:
        # Include goal context in cognition prompt
        record_progress(goal_id, insight, relevance_score)
"""

import json
import os
import time
from datetime import datetime


GOALS_FILE = "data/persistent_goals.json"


def _load_goals() -> dict:
    if not os.path.exists(GOALS_FILE):
        return {"active": None, "history": []}
    try:
        with open(GOALS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"active": None, "history": []}


def _save_goals(data: dict):
    os.makedirs("data", exist_ok=True)
    with open(GOALS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def set_goal(goal_text: str, duration_cycles: int = 500) -> dict:
    """
    Set a new persistent research goal.
    duration_cycles: how many brain cycles to pursue it (default 500 = ~7 hours)
    """
    data = _load_goals()

    # Archive current goal if exists
    if data.get("active"):
        data["active"]["archived_at"] = int(time.time())
        data["history"].append(data["active"])
        data["history"] = data["history"][-20:]

    goal_id = f"goal_{int(time.time())}"
    new_goal = {
        "id": goal_id,
        "text": goal_text,
        "created_at": int(time.time()),
        "created_at_human": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "duration_cycles": duration_cycles,
        "cycles_completed": 0,
        "progress_entries": [],
        "key_findings": [],
        "status": "active",
    }

    data["active"] = new_goal
    _save_goals(data)
    print(f"🎯 PERSISTENT GOAL SET: {goal_text[:80]}")
    return new_goal


def get_active_goal() -> dict | None:
    """Return the currently active persistent goal, or None."""
    data = _load_goals()
    goal = data.get("active")
    if not goal:
        return None
    if goal.get("status") != "active":
        return None
    # Check if goal has expired
    if goal["cycles_completed"] >= goal["duration_cycles"]:
        complete_goal(goal["id"])
        return None
    return goal


def record_progress(goal_id: str, insight: str, relevance_score: float):
    """
    Record a cognition cycle's contribution to the active goal.
    relevance_score: 0.0-1.0, how relevant this insight is to the goal
    """
    data = _load_goals()
    goal = data.get("active")
    if not goal or goal.get("id") != goal_id:
        return

    goal["cycles_completed"] = goal.get("cycles_completed", 0) + 1

    if relevance_score >= 0.3:
        entry = {
            "timestamp": int(time.time()),
            "cycle": goal["cycles_completed"],
            "insight_preview": insight[:200],
            "relevance": relevance_score,
        }
        goal["progress_entries"] = goal.get("progress_entries", [])
        goal["progress_entries"].append(entry)
        goal["progress_entries"] = goal["progress_entries"][-100:]

        # Elevate to key finding if highly relevant
        if relevance_score >= 0.7:
            goal["key_findings"] = goal.get("key_findings", [])
            goal["key_findings"].append(insight[:300])
            goal["key_findings"] = goal["key_findings"][-20:]
            print(f"🎯 KEY FINDING RECORDED (relevance={relevance_score:.2f})")

    _save_goals(data)


def complete_goal(goal_id: str):
    """Mark a goal as complete and archive it."""
    data = _load_goals()
    goal = data.get("active")
    if goal and goal.get("id") == goal_id:
        goal["status"] = "completed"
        goal["completed_at"] = int(time.time())
        data["history"].append(goal)
        data["history"] = data["history"][-20:]
        data["active"] = None
        _save_goals(data)
        print(f"🎯 GOAL COMPLETED: {goal['text'][:60]}")


def clear_goal():
    """Clear the active goal without completing it."""
    data = _load_goals()
    if data.get("active"):
        data["active"]["status"] = "cleared"
        data["history"].append(data["active"])
        data["history"] = data["history"][-20:]
        data["active"] = None
        _save_goals(data)
        print("🎯 GOAL CLEARED")


def get_goal_context_block() -> str:
    """
    Return a prompt block describing the active goal and key findings.
    Injected into every cognition cycle prompt when a goal is active.
    """
    goal = get_active_goal()
    if not goal:
        return ""

    progress_pct = min(
        100, int(goal["cycles_completed"] / goal["duration_cycles"] * 100)
    )
    lines = [
        f"PERSISTENT RESEARCH GOAL ({progress_pct}% complete, "
        f"{goal['cycles_completed']}/{goal['duration_cycles']} cycles):",
        f"→ {goal['text']}",
    ]

    if goal.get("key_findings"):
        lines.append(f"\nKey findings so far ({len(goal['key_findings'])}):")
        for finding in goal["key_findings"][-3:]:
            lines.append(f"- {finding[:150]}")

    lines.append(
        "\nEvery cognition cycle should contribute to this goal. "
        "Prioritize topics, tools, and stances that advance this investigation."
    )

    return "\n".join(lines)


def score_relevance(insight: str, goal_text: str) -> float:
    """
    Simple relevance scoring — how much does this insight contribute to the goal?
    Returns 0.0-1.0 without requiring an LLM call.
    """
    if not insight or not goal_text:
        return 0.0

    insight_lower = insight.lower()
    goal_words = set(
        w.lower()
        for w in goal_text.split()
        if len(w) > 4
        and w.lower()
        not in {
            "what",
            "most",
            "that",
            "this",
            "with",
            "from",
            "have",
            "been",
            "will",
            "your",
            "their",
            "about",
        }
    )

    if not goal_words:
        return 0.0

    hits = sum(1 for word in goal_words if word in insight_lower)
    return min(1.0, hits / max(len(goal_words) * 0.3, 1))


def get_goals_status() -> dict:
    """For the API — return goal status for display."""
    data = _load_goals()
    active = data.get("active")
    return {
        "active": active,
        "has_goal": active is not None,
        "recent_history": data.get("history", [])[-3:],
    }
