"""
curriculum.py

Nexarion's knowledge curriculum — a rotating agenda that ensures
broad domain coverage rather than topic drift.

Every CURRICULUM_CYCLE_INTERVAL cycles, the brain loop checks this
module and gets a forced domain to explore. This guarantees Nexarion
builds genuine knowledge across all major human knowledge domains
rather than staying locked on whatever the workspace happens to
have drifted toward.

The curriculum rotates through 15 major domains. Each domain stays
active for DOMAIN_DURATION cycles before moving to the next.
After a full rotation, it starts again — but Nexarion's accumulated
memory means the second pass is richer than the first.
"""

import json
import os
import time

CURRICULUM_FILE = "data/curriculum_state.json"

# How many cycles each domain stays active
DOMAIN_DURATION = 20

# Major knowledge domains — broad enough to encompass real depth
CURRICULUM_DOMAINS = [
    {
        "name": "mathematics and logic",
        "search_terms": [
            "number theory",
            "formal logic",
            "topology",
            "probability theory",
            "graph theory",
        ],
        "goal": "Understand the foundations of mathematical reasoning and formal proof",
        "description": "Mathematics — the language underlying all rigorous thought",
    },
    {
        "name": "physics and cosmology",
        "search_terms": [
            "quantum mechanics",
            "general relativity",
            "thermodynamics",
            "dark matter",
            "entropy",
        ],
        "goal": "Grasp how the physical universe operates at all scales",
        "description": "Physics — the deepest laws governing matter, energy, space, and time",
    },
    {
        "name": "biology and evolution",
        "search_terms": [
            "natural selection",
            "genetics",
            "cell biology",
            "evolutionary psychology",
            "ecology",
        ],
        "goal": "Understand life — how it arose, diversified, and behaves",
        "description": "Biology — the science of living systems and their history",
    },
    {
        "name": "history and civilizations",
        "search_terms": [
            "ancient rome",
            "industrial revolution",
            "world war two",
            "colonialism",
            "renaissance",
        ],
        "goal": "Learn how human societies have risen, transformed, and fallen",
        "description": "History — the record of human experience across time",
    },
    {
        "name": "economics and markets",
        "search_terms": [
            "supply and demand",
            "monetary policy",
            "game theory",
            "behavioral economics",
            "market failure",
        ],
        "goal": "Understand how resources are allocated and why markets succeed or fail",
        "description": "Economics — the study of incentives, scarcity, and collective decision-making",
    },
    {
        "name": "computer science and algorithms",
        "search_terms": [
            "computational complexity",
            "machine learning",
            "cryptography",
            "distributed systems",
            "neural network",
        ],
        "goal": "Grasp the theoretical and practical foundations of computation",
        "description": "Computer science — the study of information, computation, and automation",
    },
    {
        "name": "philosophy and ethics",
        "search_terms": [
            "epistemology",
            "moral philosophy",
            "philosophy of mind",
            "existentialism",
            "metaethics",
        ],
        "goal": "Engage with the deepest questions about knowledge, existence, and value",
        "description": "Philosophy — the discipline of rigorous inquiry into fundamental questions",
    },
    {
        "name": "linguistics and language",
        "search_terms": [
            "syntax",
            "semantics",
            "language acquisition",
            "linguistic relativity",
            "semiotics",
        ],
        "goal": "Understand how language works and how it shapes thought",
        "description": "Linguistics — the scientific study of human language",
    },
    {
        "name": "neuroscience and consciousness",
        "search_terms": [
            "neuroplasticity",
            "prefrontal cortex",
            "consciousness",
            "dopamine",
            "cognitive neuroscience",
        ],
        "goal": "Understand how the brain produces mind, behavior, and experience",
        "description": "Neuroscience — the study of the nervous system and the nature of mind",
    },
    {
        "name": "political theory and governance",
        "search_terms": [
            "democracy",
            "social contract",
            "political philosophy",
            "institutional theory",
            "power structures",
        ],
        "goal": "Understand how societies organize power and make collective decisions",
        "description": "Political theory — the study of power, legitimacy, and governance",
    },
    {
        "name": "chemistry and materials",
        "search_terms": [
            "chemical bonding",
            "thermochemistry",
            "polymers",
            "electrochemistry",
            "organic chemistry",
        ],
        "goal": "Understand matter at the molecular level and how substances transform",
        "description": "Chemistry — the science of matter, its properties, and its transformations",
    },
    {
        "name": "ecology and climate",
        "search_terms": [
            "ecosystem",
            "climate change",
            "biodiversity",
            "carbon cycle",
            "food web",
        ],
        "goal": "Understand the living planet as an interconnected system under pressure",
        "description": "Ecology — the study of relationships between organisms and their environment",
    },
    {
        "name": "art and aesthetics",
        "search_terms": [
            "aesthetics",
            "art history",
            "music theory",
            "narrative theory",
            "visual perception",
        ],
        "goal": "Understand how humans create and experience beauty, meaning, and expression",
        "description": "Aesthetics — the philosophy of art, beauty, and creative expression",
    },
    {
        "name": "medicine and health",
        "search_terms": [
            "immunology",
            "epidemiology",
            "pharmacology",
            "evidence based medicine",
            "public health",
        ],
        "goal": "Understand the human body, disease, and the science of healing",
        "description": "Medicine — the science and practice of maintaining and restoring health",
    },
    {
        "name": "sociology and social systems",
        "search_terms": [
            "social stratification",
            "institutional theory",
            "collective behavior",
            "social capital",
            "network theory",
        ],
        "goal": "Understand how human societies organize, stratify, and change",
        "description": "Sociology — the study of social structures, relationships, and institutions",
    },
]


def _load_state() -> dict:
    if not os.path.exists(CURRICULUM_FILE):
        return {
            "current_domain_index": 0,
            "cycles_in_domain": 0,
            "completed_rotations": 0,
            "domain_history": [],
            "started_at": int(time.time()),
        }
    try:
        with open(CURRICULUM_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {
            "current_domain_index": 0,
            "cycles_in_domain": 0,
            "completed_rotations": 0,
            "domain_history": [],
            "started_at": int(time.time()),
        }


def _save_state(state: dict):
    os.makedirs("data", exist_ok=True)
    with open(CURRICULUM_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_current_domain() -> dict:
    """Return the currently active curriculum domain."""
    state = _load_state()
    idx = state.get("current_domain_index", 0) % len(CURRICULUM_DOMAINS)
    return CURRICULUM_DOMAINS[idx]


def advance_curriculum(current_cycle: int) -> dict | None:
    """
    Called every brain cycle. Returns the active domain if the curriculum
    should override the current topic, None if the curriculum is between
    rotations and the brain can run freely.

    The curriculum is active for DOMAIN_DURATION cycles, then advances.
    """
    state = _load_state()

    cycles_in_domain = state.get("cycles_in_domain", 0) + 1
    state["cycles_in_domain"] = cycles_in_domain

    current_idx = state.get("current_domain_index", 0)
    current_domain = CURRICULUM_DOMAINS[current_idx % len(CURRICULUM_DOMAINS)]

    # Advance to next domain when duration is reached
    if cycles_in_domain >= DOMAIN_DURATION:
        old_domain = current_domain["name"]
        new_idx = (current_idx + 1) % len(CURRICULUM_DOMAINS)
        state["current_domain_index"] = new_idx
        state["cycles_in_domain"] = 0

        if new_idx == 0:
            state["completed_rotations"] = state.get("completed_rotations", 0) + 1
            print(
                f"🎓 CURRICULUM: Full rotation #{state['completed_rotations']} complete"
            )

        state["domain_history"].append(
            {
                "domain": old_domain,
                "completed_at_cycle": current_cycle,
                "timestamp": int(time.time()),
            }
        )
        state["domain_history"] = state["domain_history"][-50:]

        new_domain = CURRICULUM_DOMAINS[new_idx]
        print(f"🎓 CURRICULUM ADVANCE: {old_domain} → {new_domain['name']}")
        _save_state(state)
        return new_domain

    _save_state(state)

    # Return current domain — curriculum is active
    return current_domain


def get_curriculum_search_term(domain: dict) -> str:
    """Pick the next search term from a domain's term list, rotating through them."""
    import random

    terms = domain.get("search_terms", [])
    if not terms:
        return domain["name"]
    return random.choice(terms)


def get_curriculum_status() -> dict:
    """For the API — return current curriculum state for display."""
    state = _load_state()
    idx = state.get("current_domain_index", 0) % len(CURRICULUM_DOMAINS)
    current = CURRICULUM_DOMAINS[idx]
    return {
        "current_domain": current["name"],
        "description": current["description"],
        "goal": current["goal"],
        "cycles_in_domain": state.get("cycles_in_domain", 0),
        "cycles_remaining": max(0, DOMAIN_DURATION - state.get("cycles_in_domain", 0)),
        "domain_index": idx,
        "total_domains": len(CURRICULUM_DOMAINS),
        "completed_rotations": state.get("completed_rotations", 0),
        "domain_history": state.get("domain_history", [])[-5:],
    }
