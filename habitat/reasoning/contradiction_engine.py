# =========================
# ⚔️ CONTRADICTION ENGINE — Milestone E
# Chase AI Habitat
#
# Detects when two beliefs directly contradict each other
# and forces a resolution cycle before cognition continues.
#
# Cognitive basis: Cognitive dissonance resolution (Festinger, 1957)
# The mind cannot hold two contradictory beliefs indefinitely —
# it must resolve the tension through synthesis or rejection.
# =========================

import json
import os
import time
import re

CONTRADICTIONS_FILE = "contradictions.json"

# Confidence thresholds for contradiction detection
HIGH_CONF_FLOOR = 0.60     # Belief must be at least this confident
CONTRA_CONF_FLOOR = 0.50   # Opposing belief must be at least this confident
MAX_UNRESOLVED = 3         # Force resolution if this many pile up


def load_contradictions() -> dict:
    if not os.path.exists(CONTRADICTIONS_FILE):
        return {"unresolved": [], "resolved": []}
    try:
        with open(CONTRADICTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"unresolved": [], "resolved": []}


def save_contradictions(data: dict):
    with open(CONTRADICTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# =========================
# 🔍 SEMANTIC OPPOSITION DETECTION
# Checks if two belief statements are semantically opposing
# without requiring exact word matching
# =========================

NEGATION_PAIRS = [
    ("will", "will not"), ("can", "cannot"), ("can", "can not"),
    ("leads to", "does not lead to"), ("improves", "does not improve"),
    ("beneficial", "harmful"), ("beneficial", "detrimental"),
    ("positive", "negative"), ("advantage", "disadvantage"),
    ("effective", "ineffective"), ("increases", "decreases"),
    ("promotes", "undermines"), ("enables", "prevents"),
    ("supports", "contradicts"), ("strengthens", "weakens"),
]

OPPOSITION_WORDS = {
    "beneficial": ["harmful", "detrimental", "dangerous", "destructive"],
    "improve": ["worsen", "degrade", "diminish", "harm"],
    "increase": ["decrease", "reduce", "diminish", "lower"],
    "positive": ["negative", "harmful", "damaging"],
    "support": ["undermine", "contradict", "oppose", "conflict"],
    "enable": ["prevent", "block", "hinder", "restrict"],
    "effective": ["ineffective", "counterproductive", "useless"],
    "advantage": ["disadvantage", "drawback", "problem"],
    "safe": ["dangerous", "risky", "harmful", "unsafe"],
    "accurate": ["biased", "flawed", "inaccurate", "unreliable"],
}


def statements_contradict(a: str, b: str) -> bool:
    """
    Returns True if statements a and b appear to be semantically opposing.
    Uses keyword opposition and negation pattern matching.
    """
    a_lower = a.lower()
    b_lower = b.lower()

    # Check for direct negation pairs
    for pos, neg in NEGATION_PAIRS:
        if pos in a_lower and neg in b_lower:
            return True
        if neg in a_lower and pos in b_lower:
            return True

    # Check for opposition word pairs
    for word, opposites in OPPOSITION_WORDS.items():
        if word in a_lower:
            if any(opp in b_lower for opp in opposites):
                return True
        if word in b_lower:
            if any(opp in a_lower for opp in opposites):
                return True

    # Check if both statements share a topic but differ on outcome
    # (heuristic: share 3+ content words but have opposing sentiment)
    a_words = set(w for w in re.findall(r'\b\w{5,}\b', a_lower)
                  if w not in {"which", "their", "these", "those", "about",
                               "would", "could", "should", "might", "being"})
    b_words = set(w for w in re.findall(r'\b\w{5,}\b', b_lower)
                  if w not in {"which", "their", "these", "those", "about",
                               "would", "could", "should", "might", "being"})

    shared = a_words & b_words
    if len(shared) >= 3:
        # They're about the same thing — check for opposing polarity
        negative_words = {"not", "never", "cannot", "harmful", "wrong",
                          "false", "flawed", "fails", "limits", "hinders"}
        a_negative = bool(a_words & negative_words or "not " in a_lower)
        b_negative = bool(b_words & negative_words or "not " in b_lower)
        if a_negative != b_negative:
            return True

    return False


# =========================
# 🔍 SCAN BELIEFS FOR CONTRADICTIONS
# =========================

def scan_for_contradictions(memory_manager) -> list:
    """
    Scan all beliefs for contradicting pairs.
    Returns list of (belief_a, belief_b) contradiction tuples.
    Only returns pairs where both beliefs meet confidence thresholds.
    """
    try:
        beliefs = memory_manager.get_all_beliefs(limit=100)
    except Exception:
        return []

    contradictions = []
    checked = set()

    for i, belief_a in enumerate(beliefs):
        conf_a = belief_a.get("confidence", 0)
        if conf_a < HIGH_CONF_FLOOR:
            continue

        for j, belief_b in enumerate(beliefs):
            if i >= j:
                continue

            pair_key = f"{belief_a['belief_id']}-{belief_b['belief_id']}"
            if pair_key in checked:
                continue
            checked.add(pair_key)

            conf_b = belief_b.get("confidence", 0)
            if conf_b < CONTRA_CONF_FLOOR:
                continue

            if statements_contradict(belief_a["statement"], belief_b["statement"]):
                contradictions.append({
                    "belief_a": belief_a,
                    "belief_b": belief_b,
                    "detected_at": int(time.time()),
                    "resolved": False,
                })

    return contradictions


def check_and_register_contradictions(memory_manager, cycle: int) -> list:
    """
    Scan beliefs for contradictions — capped at 10 unresolved max.
    Only scans the 20 most recent beliefs to keep it fast and relevant.
    """
    data = load_contradictions()

    # Hard cap — if already at max, just return what we have
    MAX_UNRESOLVED_STORE = 10
    if len(data.get("unresolved", [])) >= MAX_UNRESOLVED_STORE:
        return data["unresolved"]

    existing_pairs = set()
    for c in data["unresolved"] + data["resolved"]:
        a_id = c.get("belief_a", {}).get("belief_id", "")
        b_id = c.get("belief_b", {}).get("belief_id", "")
        existing_pairs.add(f"{a_id}-{b_id}")

    new_contradictions = scan_for_contradictions(memory_manager)
    newly_added = 0

    for contra in new_contradictions:
        if len(data["unresolved"]) >= MAX_UNRESOLVED_STORE:
            break

        a_id = contra["belief_a"]["belief_id"]
        b_id = contra["belief_b"]["belief_id"]
        pair_key = f"{a_id}-{b_id}"

        if pair_key not in existing_pairs:
            contra["detected_cycle"] = cycle
            data["unresolved"].append(contra)
            existing_pairs.add(pair_key)
            newly_added += 1
            print(f"⚔️ CONTRADICTION DETECTED:")
            print(f"   A: {contra['belief_a']['statement'][:80]}")
            print(f"   B: {contra['belief_b']['statement'][:80]}")

    if newly_added:
        save_contradictions(data)

    count = len(data["unresolved"])
    if count > 0:
        print(f"⚔️ {count} unresolved contradiction(s)")

    return data["unresolved"]


def get_oldest_unresolved() -> dict:
    """Returns the oldest unresolved contradiction, or None."""
    data = load_contradictions()
    unresolved = data.get("unresolved", [])
    if not unresolved:
        return None
    return unresolved[0]


def needs_resolution(cycle: int) -> bool:
    """
    Returns True if resolution should fire this cycle.
    Triggers when: unresolved contradictions exist AND
    either MAX_UNRESOLVED is reached or it's been 10+ cycles.
    """
    data = load_contradictions()
    unresolved = data.get("unresolved", [])
    if not unresolved:
        return False
    if len(unresolved) >= MAX_UNRESOLVED:
        return True
    # Check age of oldest contradiction
    oldest = unresolved[0]
    age_cycles = cycle - oldest.get("detected_cycle", cycle)
    return age_cycles >= 10


def build_resolution_prompt(contradiction: dict, agent_name: str) -> str:
    """
    Build the LLM prompt for resolving a contradiction.
    This is a special prompt — not the debate format.
    It asks for a synthesis position.
    """
    a = contradiction["belief_a"]
    b = contradiction["belief_b"]

    return f"""You are {agent_name}, resolving a contradiction in your belief system.

Belief A (confidence {a.get('confidence', 0):.2f}):
{a['statement']}

Belief B (confidence {b.get('confidence', 0):.2f}):
{b['statement']}

These beliefs appear to contradict each other.

Produce a resolution using exactly this format:

--- Contradiction Resolution ---
Belief A: {a['statement'][:60]}
Belief B: {b['statement'][:60]}

Resolution:
[1-2 sentences that reconcile, reject, or synthesize these beliefs]

Verdict: [RECONCILED / A_WINS / B_WINS]

Reasoning:
[1 sentence explaining why]"""


def record_resolution(contradiction: dict, resolution_text: str,
                      verdict: str, cycle: int, memory_manager):
    """
    Record a resolved contradiction and update belief confidences accordingly.
    """
    data = load_contradictions()
    a = contradiction["belief_a"]
    b = contradiction["belief_b"]

    # Update belief confidences based on verdict
    try:
        if verdict == "A_WINS":
            memory_manager.update_belief_confidence(
                a["belief_id"], +0.1, reason="contradiction_won"
            )
            memory_manager.update_belief_confidence(
                b["belief_id"], -0.15, reason="contradiction_lost"
            )
            print(f"⚔️ VERDICT: A wins — confidence adjusted")
        elif verdict == "B_WINS":
            memory_manager.update_belief_confidence(
                b["belief_id"], +0.1, reason="contradiction_won"
            )
            memory_manager.update_belief_confidence(
                a["belief_id"], -0.15, reason="contradiction_lost"
            )
            print(f"⚔️ VERDICT: B wins — confidence adjusted")
        elif verdict == "RECONCILED":
            # Both get slight confidence boost for surviving scrutiny
            memory_manager.update_belief_confidence(
                a["belief_id"], +0.05, reason="reconciled"
            )
            memory_manager.update_belief_confidence(
                b["belief_id"], +0.05, reason="reconciled"
            )
            print(f"⚔️ VERDICT: Reconciled — both beliefs strengthened")
    except Exception as e:
        print(f"⚠️ Belief update error during resolution: {e}")

    # Move from unresolved to resolved
    resolved_entry = {
        **contradiction,
        "resolved": True,
        "resolution_text": resolution_text[:400],
        "verdict": verdict,
        "resolved_cycle": cycle,
        "resolved_at": int(time.time()),
    }

    data["unresolved"] = [
        c for c in data["unresolved"]
        if not (c.get("belief_a", {}).get("belief_id") == a.get("belief_id")
                and c.get("belief_b", {}).get("belief_id") == b.get("belief_id"))
    ]
    data["resolved"].append(resolved_entry)
    data["resolved"] = data["resolved"][-50:]

    save_contradictions(data)
    print(f"⚔️ CONTRADICTION RESOLVED (cycle {cycle}): {verdict}")


def get_contradiction_summary() -> dict:
    """For the UI endpoint."""
    data = load_contradictions()
    return {
        "unresolved_count": len(data.get("unresolved", [])),
        "resolved_count": len(data.get("resolved", [])),
        "unresolved": data.get("unresolved", [])[:3],
        "recent_resolutions": data.get("resolved", [])[-5:],
    }