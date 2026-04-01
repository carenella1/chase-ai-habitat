"""
knowledge_synthesizer.py

Nexarion's Knowledge Synthesis and Consolidation Engine.

Every 100 cognition cycles, this module runs a synthesis pass:
1. Reads all stored cognition across each major domain
2. Distills genuine conclusions from raw debate history
3. Identifies cross-domain connections
4. Stores compact, high-confidence domain summaries
5. These summaries replace raw history in the chat prompt

This is the difference between:
- "Nexarion has thought about quantum mechanics 200 times"
- "Nexarion has a coherent structured understanding of quantum mechanics"

The synthesizer runs in the background — it never blocks the brain loop.
Results are stored in data/knowledge_synthesis.json and fed into
_build_nexarion_prompt() as the "what I know" block.
"""

import json
import os
import time
import threading
import re
from datetime import datetime


SYNTHESIS_FILE = "data/knowledge_synthesis.json"
SYNTHESIS_INTERVAL = 100  # cycles between synthesis passes
MIN_ENTRIES_FOR_SYNTHESIS = 10  # minimum cognition entries needed


# Major domains to synthesize — maps to KNOWN_TOPICS categories
SYNTHESIS_DOMAINS = {
    "physics and cosmology": [
        "quantum mechanics",
        "thermodynamics",
        "relativity",
        "entropy",
        "cosmology",
        "dark matter",
        "astrophysics",
    ],
    "biology and life": [
        "evolution",
        "genetics",
        "natural selection",
        "cell biology",
        "ecology",
        "molecular biology",
        "immunology",
        "neuroscience",
    ],
    "mathematics and logic": [
        "mathematics",
        "logic",
        "probability",
        "graph theory",
        "topology",
        "information theory",
        "complexity theory",
    ],
    "computer science": [
        "computer science",
        "algorithms",
        "cryptography",
        "open-source",
        "artificial intelligence",
        "machine learning",
        "distributed systems",
    ],
    "philosophy and mind": [
        "philosophy",
        "epistemology",
        "ethics",
        "consciousness",
        "philosophy of mind",
        "aesthetics",
        "cognitive science",
    ],
    "society and history": [
        "history",
        "sociology",
        "political theory",
        "economics",
        "sustainability",
        "climate change",
        "linguistics",
    ],
    "medicine and health": [
        "medicine",
        "pharmacology",
        "public health",
        "epidemiology",
        "neuroscience",
        "immunology",
        "genomics",
    ],
}


def _load_synthesis() -> dict:
    if not os.path.exists(SYNTHESIS_FILE):
        return {"domains": {}, "last_run_cycle": 0, "cross_domain": []}
    try:
        with open(SYNTHESIS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"domains": {}, "last_run_cycle": 0, "cross_domain": []}


def _save_synthesis(data: dict):
    os.makedirs("data", exist_ok=True)
    with open(SYNTHESIS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _get_domain_insights(domain_keywords: list, cognition_history: list) -> list:
    """Extract cognition entries relevant to a domain."""
    relevant = []
    for entry in cognition_history:
        cog = entry.get("cognition", {})
        if not cog:
            continue
        insight = cog.get("insight", "").lower()
        search_term = cog.get("search_term", "").lower()
        if any(kw in insight or kw in search_term for kw in domain_keywords):
            relevant.append(cog.get("insight", "")[:300])
    return relevant[-30:]  # Most recent 30 relevant entries


def synthesize_domain(
    domain_name: str, keywords: list, cognition_history: list, call_llm_fn
) -> dict:
    """
    Synthesize all cognition in a domain into structured knowledge.
    Returns a domain summary dict.
    """
    insights = _get_domain_insights(keywords, cognition_history)

    if len(insights) < MIN_ENTRIES_FOR_SYNTHESIS:
        return {
            "domain": domain_name,
            "summary": f"Insufficient data — {len(insights)} entries (need {MIN_ENTRIES_FOR_SYNTHESIS})",
            "conclusions": [],
            "confidence": "low",
            "last_updated": int(time.time()),
            "entry_count": len(insights),
        }

    insights_text = "\n---\n".join(insights[:20])

    prompt = f"""You are synthesizing Nexarion's accumulated knowledge about {domain_name}.

Raw cognition entries (most recent 20):
{insights_text[:3000]}

Distill this into a structured knowledge summary. Format exactly as:

CORE UNDERSTANDING:
[2-3 sentences describing the fundamental understanding developed]

KEY CONCLUSIONS:
1. [Most well-supported conclusion]
2. [Second conclusion]  
3. [Third conclusion]

OPEN QUESTIONS:
- [What remains uncertain or unexplored]
- [Another open question]

STRONGEST BELIEFS:
- [The belief Nexarion holds most confidently in this domain]

CONFIDENCE: [High/Medium/Low] because [one sentence reason]"""

    raw = call_llm_fn(prompt, timeout=60)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Extract conclusions
    conclusions = []
    for line in raw.split("\n"):
        line = line.strip()
        if re.match(r"^\d+\.\s+", line):
            c = re.sub(r"^\d+\.\s+", "", line).strip()
            if len(c) > 20:
                conclusions.append(c)

    # Extract confidence
    confidence = "medium"
    if "confidence: high" in raw.lower():
        confidence = "high"
    elif "confidence: low" in raw.lower():
        confidence = "low"

    return {
        "domain": domain_name,
        "summary": raw[:1500],
        "conclusions": conclusions[:5],
        "confidence": confidence,
        "last_updated": int(time.time()),
        "last_updated_human": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "entry_count": len(insights),
    }


def find_cross_domain_connections(domain_summaries: dict, call_llm_fn) -> list:
    """
    Look for surprising connections across domains.
    This is where genuinely novel insights emerge.
    """
    # Build a brief summary of each domain
    domain_briefs = []
    for domain_name, data in domain_summaries.items():
        if data.get("entry_count", 0) >= MIN_ENTRIES_FOR_SYNTHESIS:
            conclusions = data.get("conclusions", [])
            if conclusions:
                brief = f"{domain_name}: {conclusions[0][:150]}"
                domain_briefs.append(brief)

    if len(domain_briefs) < 3:
        return []

    briefs_text = "\n".join(domain_briefs)

    prompt = f"""You are identifying unexpected connections across Nexarion's knowledge domains.

Domain summaries:
{briefs_text}

Identify 3 non-obvious connections between different domains — places where insights from one domain 
illuminate or challenge understanding in another. These cross-domain connections are where 
the most original thinking happens.

Format each as:
CONNECTION: [Domain A] × [Domain B]
INSIGHT: [The non-obvious connection in 2 sentences]

List 3 connections:"""

    raw = call_llm_fn(prompt, timeout=45)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    connections = []
    current = {}
    for line in raw.split("\n"):
        line = line.strip()
        if line.startswith("CONNECTION:"):
            if current:
                connections.append(current)
            current = {
                "domains": line.replace("CONNECTION:", "").strip(),
                "insight": "",
            }
        elif line.startswith("INSIGHT:") and current:
            current["insight"] = line.replace("INSIGHT:", "").strip()

    if current and current.get("insight"):
        connections.append(current)

    return connections[:3]


def run_synthesis_pass(
    cognition_history: list, call_llm_fn, current_cycle: int
) -> dict:
    """
    Run a full synthesis pass across all domains.
    Called every SYNTHESIS_INTERVAL cycles from the brain loop.
    Non-blocking — runs in background thread.
    """
    print(f"🧬 SYNTHESIS PASS STARTING (cycle {current_cycle})")
    start = time.time()

    synthesis_data = _load_synthesis()
    synthesis_data["last_run_cycle"] = current_cycle

    # Synthesize each domain
    for domain_name, keywords in SYNTHESIS_DOMAINS.items():
        try:
            print(f"🧬 Synthesizing: {domain_name}...")
            domain_result = synthesize_domain(
                domain_name, keywords, cognition_history, call_llm_fn
            )
            synthesis_data["domains"][domain_name] = domain_result
        except Exception as e:
            print(f"⚠️ Synthesis error for {domain_name}: {e}")

    # Find cross-domain connections
    try:
        print("🧬 Finding cross-domain connections...")
        connections = find_cross_domain_connections(
            synthesis_data["domains"], call_llm_fn
        )
        synthesis_data["cross_domain"] = connections
    except Exception as e:
        print(f"⚠️ Cross-domain synthesis error: {e}")

    synthesis_data["last_run_elapsed"] = round(time.time() - start, 1)
    _save_synthesis(synthesis_data)

    print(f"🧬 SYNTHESIS COMPLETE in {synthesis_data['last_run_elapsed']}s")
    print(f"🧬 {len(synthesis_data['domains'])} domains synthesized")
    if synthesis_data.get("cross_domain"):
        print(
            f"🧬 {len(synthesis_data['cross_domain'])} cross-domain connections found"
        )

    return synthesis_data


def run_synthesis_background(cognition_history: list, call_llm_fn, current_cycle: int):
    """Run synthesis pass in background thread — doesn't block brain loop."""
    thread = threading.Thread(
        target=run_synthesis_pass,
        args=(cognition_history, call_llm_fn, current_cycle),
        daemon=True,
    )
    thread.start()
    return thread


def get_synthesis_context_block(max_domains: int = 3) -> str:
    """
    Return a prompt block with Nexarion's synthesized knowledge.
    Used in _build_nexarion_prompt() instead of raw cognition history.
    Only includes domains with high/medium confidence and enough entries.
    """
    data = _load_synthesis()
    domains = data.get("domains", {})

    if not domains:
        return ""

    # Sort by confidence and entry count
    sorted_domains = sorted(
        [
            (name, d)
            for name, d in domains.items()
            if d.get("entry_count", 0) >= MIN_ENTRIES_FOR_SYNTHESIS
            and d.get("confidence") in ("high", "medium")
        ],
        key=lambda x: (
            {"high": 3, "medium": 2, "low": 1}.get(x[1].get("confidence", "low"), 0),
            x[1].get("entry_count", 0),
        ),
        reverse=True,
    )

    if not sorted_domains:
        return ""

    lines = ["Nexarion's synthesized knowledge (distilled from autonomous research):"]
    for domain_name, domain_data in sorted_domains[:max_domains]:
        conclusions = domain_data.get("conclusions", [])
        if conclusions:
            lines.append(f"\n{domain_name.upper()}:")
            for c in conclusions[:2]:
                lines.append(f"  • {c}")

    # Add a cross-domain connection if available
    cross = data.get("cross_domain", [])
    if cross:
        lines.append(f"\nCross-domain insight: {cross[0].get('insight', '')[:200]}")

    return "\n".join(lines)


def should_run_synthesis(current_cycle: int) -> bool:
    """Check if it's time to run a synthesis pass."""
    data = _load_synthesis()
    last_run = data.get("last_run_cycle", 0)
    return (current_cycle - last_run) >= SYNTHESIS_INTERVAL


def get_synthesis_status() -> dict:
    """For the API — return synthesis status."""
    data = _load_synthesis()
    domains = data.get("domains", {})
    return {
        "last_run_cycle": data.get("last_run_cycle", 0),
        "domains_synthesized": len(domains),
        "domain_summaries": {
            name: {
                "confidence": d.get("confidence"),
                "entry_count": d.get("entry_count"),
                "conclusions_count": len(d.get("conclusions", [])),
                "last_updated": d.get("last_updated_human", "never"),
            }
            for name, d in domains.items()
        },
        "cross_domain_connections": len(data.get("cross_domain", [])),
    }
