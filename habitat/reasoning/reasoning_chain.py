# =========================
# 🔗 REASONING CHAINS — Milestone D
# Chase AI Habitat
#
# A ReasoningChain tracks a 3-5 step argument building toward conclusion.
# Each cycle either starts, advances, or concludes a chain.
# Agents know which step they're on and what role to play.
# =========================

import json
import os
import time
import uuid

CHAINS_FILE = "reasoning_chains.json"
MAX_CHAIN_LENGTH = 5
MIN_CHAIN_LENGTH = 3
CHAIN_SALIENCE_FLOOR = 7.0


def load_chains() -> dict:
    if not os.path.exists(CHAINS_FILE):
        return {"active": None, "completed": [], "abandoned": []}
    try:
        with open(CHAINS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"active": None, "completed": [], "abandoned": []}


def save_chains(data: dict):
    with open(CHAINS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def start_chain(topic: str, thesis: str, agent: str, cycle: int) -> dict:
    chain = {
        "id": str(uuid.uuid4())[:8],
        "topic": topic,
        "thesis": thesis[:300],
        "started_by": agent,
        "started_cycle": cycle,
        "current_step": 1,
        "max_steps": MAX_CHAIN_LENGTH,
        "steps": [{
            "step": 1,
            "agent": agent,
            "content": thesis[:300],
            "cycle": cycle,
            "timestamp": int(time.time()),
            "role": "thesis",
        }],
        "status": "active",
        "conclusion": None,
        "created": int(time.time()),
    }

    data = load_chains()

    if data.get("active"):
        old = data["active"]
        old["status"] = "abandoned"
        old["abandoned_at_cycle"] = cycle
        data["abandoned"].append(old)
        data["abandoned"] = data["abandoned"][-20:]

    data["active"] = chain
    save_chains(data)
    print(f"🔗 CHAIN STARTED: [{chain['id']}] topic={topic}")
    return chain


def advance_chain(insight: str, agent: str, stance: str, cycle: int) -> dict:
    data = load_chains()
    chain = data.get("active")

    if not chain or chain["status"] != "active":
        return None

    step_num = chain["current_step"] + 1

    if step_num >= chain["max_steps"]:
        role = "conclusion"
    elif stance == "CHALLENGE":
        role = "challenge"
    elif stance in ("SUPPORT", "EXPAND"):
        role = "development"
    elif stance == "REFRAME":
        role = "synthesis"
    else:
        role = "development"

    content = insight
    for marker in ["Insight:", "Claim:", "Response:"]:
        if marker in insight:
            after = insight.split(marker)[-1].strip()
            first_line = after.split("\n")[0].strip()
            if len(first_line) > 20 and "[" not in first_line:
                content = first_line
                break

    step = {
        "step": step_num,
        "agent": agent,
        "content": content[:300],
        "cycle": cycle,
        "timestamp": int(time.time()),
        "role": role,
        "stance": stance,
    }

    chain["steps"].append(step)
    chain["current_step"] = step_num

    should_conclude = (
        step_num >= chain["max_steps"] or
        (step_num >= MIN_CHAIN_LENGTH and role == "conclusion")
    )

    if should_conclude:
        chain["status"] = "concluded"
        chain["conclusion"] = content[:300]
        chain["concluded_cycle"] = cycle
        data["completed"].append(dict(chain))
        data["completed"] = data["completed"][-30:]
        data["active"] = None
        print(f"🔗 CHAIN CONCLUDED: [{chain['id']}] after {step_num} steps")
        print(f"🔗 CONCLUSION: {chain['conclusion'][:100]}")
    else:
        data["active"] = chain
        print(f"🔗 CHAIN STEP {step_num}/{chain['max_steps']}: [{chain['id']}] {role} by {agent}")

    save_chains(data)
    return chain


def get_active_chain() -> dict:
    data = load_chains()
    chain = data.get("active")
    if chain and chain.get("status") == "active":
        return chain
    return None


def get_chain_context(chain: dict) -> str:
    if not chain:
        return ""

    step = chain["current_step"]
    max_steps = chain["max_steps"]
    topic = chain["topic"]
    thesis = chain["thesis"][:150]
    steps_left = max_steps - step

    if steps_left == 1:
        next_role = "CONCLUDE — synthesize the argument into a final position"
    elif step == 1:
        next_role = "DEVELOP — build on the thesis with evidence or logic"
    else:
        roles_used = [s["role"] for s in chain["steps"]]
        if "challenge" not in roles_used:
            next_role = "CHALLENGE — stress-test the argument"
        elif "synthesis" not in roles_used:
            next_role = "SYNTHESIZE — reconcile the challenge with the thesis"
        else:
            next_role = "ADVANCE — push the argument toward conclusion"

    last_step = chain["steps"][-1]
    last_content = last_step.get("content", "")[:120]

    return (
        f"REASONING CHAIN [{chain['id']}] — Step {step+1} of {max_steps}\n"
        f"Topic: {topic} | Thesis: {thesis}\n"
        f"Last ({last_step['role']} by {last_step['agent']}): {last_content}\n"
        f"Your task: {next_role}"
    )


def should_start_chain(salience: float, cycle: int) -> bool:
    if salience < CHAIN_SALIENCE_FLOOR:
        return False
    chain = get_active_chain()
    if chain:
        return False
    data = load_chains()
    completed = data.get("completed", [])
    if completed:
        last_concluded = completed[-1].get("concluded_cycle", 0)
        if cycle - last_concluded < 3:
            return False
    return True


def get_recent_conclusions(limit: int = 5) -> list:
    data = load_chains()
    completed = data.get("completed", [])
    return [
        {
            "topic": c["topic"],
            "conclusion": c.get("conclusion", ""),
            "steps": c["current_step"],
            "cycle": c.get("concluded_cycle", 0),
        }
        for c in completed[-limit:]
        if c.get("conclusion")
    ]