"""
nex_trainer.py  —  Continuous Local Knowledge Reinforcement

WHY THIS EXISTS:
  Real LLM training requires a data center, thousands of GPU-hours,
  and modifying the model weights. We can't do that on a desktop.

  BUT — there's a powerful alternative that achieves similar outcomes:
  RETRIEVAL-AUGMENTED KNOWLEDGE REINFORCEMENT (RAKR)

  Instead of changing what the model knows at the weight level,
  we continuously build a high-quality local knowledge corpus that
  gets injected into every prompt — so Nex "knows" things that
  weren't in its original training, updated daily, tailored to
  what Nex has actually been learning.

  The result feels like a model that is getting smarter over time,
  because functionally it IS — its accessible knowledge grows every
  cognition cycle.

HOW IT WORKS — 5 LOOPS:

  LOOP 1: CONSOLIDATION (every 10 cognition cycles)
    - Takes raw insights from structured_memory.db
    - Compresses them into dense "knowledge cards"
    - Stores in knowledge_cards.db
    - These cards are injected into prompts going forward

  LOOP 2: CONTRADICTION RESOLUTION (every 20 cycles)
    - Finds beliefs that conflict with newer beliefs
    - Runs a debate between them using the deep brain
    - Stores the resolved position as a high-confidence belief
    - Updates the knowledge graph edges

  LOOP 3: SYNTHESIS REINFORCEMENT (every 50 cycles)
    - Identifies the most-visited topic clusters
    - Generates synthesis essays connecting them
    - These become long-term reference docs for Nex

  LOOP 4: SKILL EXTRACTION (every 100 cycles)
    - Reviews successful reasoning chains
    - Extracts the reasoning PATTERNS that worked
    - Stores them as "thinking skills" — reusable templates
    - Injects the most relevant skill into each deep call

  LOOP 5: OVERNIGHT DEEP STUDY (scheduled, uses 32b brain)
    - Picks 3 topics from curriculum that have low coverage
    - Runs 10-deep research chains on each
    - Synthesizes into a full "knowledge chapter"
    - Dramatically expands Nex's depth on that topic overnight

WHAT THIS ACHIEVES vs REAL TRAINING:
  Real training:   Permanent weight changes, general capability
  This system:     Permanent knowledge accumulation, domain depth
  Gap:             Nex's reasoning style doesn't improve (weight-level)
  Bridged by:      Self-optimizer (Phase 3) + skill extraction above

HARDWARE NOTES (RTX 4070 Ti SUPER):
  Consolidation: CPU-only, runs in background always
  Contradiction resolution: Chat brain, fast
  Synthesis: Deep brain, schedule during idle time
  Overnight study: Deep brain, runs while you sleep
  GPU stays free for chat during the day

"""

import json
import os
import sqlite3
import threading
import time
from datetime import datetime
from typing import Optional

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

TRAINER_DB = "data/nex_trainer.db"
KNOWLEDGE_CARDS_DB = "data/knowledge_cards.db"
SKILLS_DB = "data/thinking_skills.db"

CONSOLIDATION_EVERY = 10  # cognition cycles
CONTRADICTION_EVERY = 20
SYNTHESIS_EVERY = 50
SKILL_EXTRACTION_EVERY = 100

MAX_CARDS_PER_TOPIC = 20  # Keep the most recent N cards per topic
MAX_CONTEXT_INJECTION = 3  # Inject top 3 relevant cards per prompt
CARD_MAX_TOKENS = 300  # Keep cards compact

# ─────────────────────────────────────────────
# DATABASE INIT
# ─────────────────────────────────────────────


def _init_dbs():
    """Create all trainer databases if they don't exist."""
    os.makedirs("data", exist_ok=True)

    # Knowledge cards — compressed, high-density knowledge chunks
    with sqlite3.connect(KNOWLEDGE_CARDS_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_cards (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                topic       TEXT NOT NULL,
                card_text   TEXT NOT NULL,
                source_type TEXT,          -- 'insight', 'research', 'synthesis'
                confidence  REAL DEFAULT 0.5,
                access_count INTEGER DEFAULT 0,
                created_at  INTEGER NOT NULL,
                updated_at  INTEGER NOT NULL
            )
        """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_kc_topic ON knowledge_cards(topic)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_kc_confidence ON knowledge_cards(confidence DESC)"
        )

    # Thinking skills — reusable reasoning patterns
    with sqlite3.connect(SKILLS_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS thinking_skills (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name  TEXT NOT NULL,
                skill_desc  TEXT NOT NULL,
                template    TEXT NOT NULL,    -- The actual reasoning template
                domain      TEXT,
                success_rate REAL DEFAULT 0.5,
                use_count   INTEGER DEFAULT 0,
                created_at  INTEGER NOT NULL
            )
        """
        )

    # Trainer state — tracks which cycles have been processed
    with sqlite3.connect(TRAINER_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trainer_state (
                key     TEXT PRIMARY KEY,
                value   TEXT NOT NULL
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS training_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                loop_type   TEXT NOT NULL,
                cycle       INTEGER,
                summary     TEXT,
                cards_added INTEGER DEFAULT 0,
                duration_s  REAL,
                timestamp   INTEGER NOT NULL
            )
        """
        )


def _get_state(key: str, default=None):
    try:
        with sqlite3.connect(TRAINER_DB) as conn:
            row = conn.execute(
                "SELECT value FROM trainer_state WHERE key=?", (key,)
            ).fetchone()
            return json.loads(row[0]) if row else default
    except Exception:
        return default


def _set_state(key: str, value):
    try:
        with sqlite3.connect(TRAINER_DB) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO trainer_state (key, value) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
    except Exception:
        pass


def _log_training(
    loop_type: str, cycle: int, summary: str, cards_added: int, duration: float
):
    try:
        with sqlite3.connect(TRAINER_DB) as conn:
            conn.execute(
                "INSERT INTO training_log (loop_type, cycle, summary, cards_added, duration_s, timestamp) VALUES (?,?,?,?,?,?)",
                (loop_type, cycle, summary, cards_added, duration, int(time.time())),
            )
    except Exception:
        pass


# ─────────────────────────────────────────────
# LOOP 1: CONSOLIDATION
# ─────────────────────────────────────────────


def run_consolidation(cycle: int, call_llm_fn) -> int:
    """
    Compress recent raw insights into dense knowledge cards.
    Returns number of cards created.
    """
    start = time.time()
    cards_created = 0

    try:
        # Pull recent insights from structured memory
        from structured_memory import StructuredMemoryDB

        mem_db = StructuredMemoryDB()
        recent_insights = mem_db.get_recent_facts(limit=30)
        recent_beliefs = mem_db.get_high_confidence_beliefs(
            min_confidence=0.65, limit=20
        )
    except Exception as e:
        print(f"⚠️ TRAINER: Cannot read structured memory — {e}")
        # Fallback: read from memory.json
        try:
            with open("memory.json", "r") as f:
                mem = json.load(f)
            recent_insights = mem.get("cognition_history", [])[-30:]
            recent_beliefs = []
        except Exception:
            return 0

    if not recent_insights and not recent_beliefs:
        return 0

    # Group by topic for consolidation
    topic_groups = {}
    for item in recent_insights:
        content = item if isinstance(item, str) else item.get("content", str(item))
        topic = item.get("topic", "general") if isinstance(item, dict) else "general"
        if topic not in topic_groups:
            topic_groups[topic] = []
        topic_groups[topic].append(content[:400])

    for topic, items in list(topic_groups.items())[
        :5
    ]:  # Process 5 topics max per cycle
        if len(items) < 2:
            continue  # Not enough to compress

        raw_text = "\n".join(f"- {i}" for i in items[:10])
        prompt = f"""You are a knowledge compressor for an AI system.

Below are recent insights about "{topic}". Your job is to compress them into a single, dense knowledge card — a compact summary that captures the most important facts, patterns, and connections.

INSIGHTS:
{raw_text}

Write a knowledge card of maximum 200 words. Be specific, factual, and dense. No fluff. Start directly with the knowledge:"""

        card_text = call_llm_fn(prompt, timeout=45)
        if not card_text or len(card_text) < 30:
            continue

        # Measure confidence based on how many sources agreed
        confidence = min(0.5 + len(items) * 0.04, 0.9)

        try:
            with sqlite3.connect(KNOWLEDGE_CARDS_DB) as conn:
                now = int(time.time())
                conn.execute(
                    "INSERT INTO knowledge_cards (topic, card_text, source_type, confidence, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                    (
                        topic,
                        card_text[: CARD_MAX_TOKENS * 2],
                        "consolidation",
                        confidence,
                        now,
                        now,
                    ),
                )
                cards_created += 1

            # Prune old cards for this topic (keep freshest MAX_CARDS_PER_TOPIC)
            with sqlite3.connect(KNOWLEDGE_CARDS_DB) as conn:
                conn.execute(
                    """
                    DELETE FROM knowledge_cards
                    WHERE topic = ? AND id NOT IN (
                        SELECT id FROM knowledge_cards
                        WHERE topic = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                    )
                """,
                    (topic, topic, MAX_CARDS_PER_TOPIC),
                )

        except Exception as e:
            print(f"⚠️ TRAINER: Card insert failed — {e}")

    duration = time.time() - start
    _log_training(
        "consolidation",
        cycle,
        f"Processed {len(topic_groups)} topics",
        cards_created,
        duration,
    )
    print(f"📚 TRAINER CONSOLIDATION: {cards_created} new cards ({duration:.1f}s)")
    return cards_created


# ─────────────────────────────────────────────
# LOOP 2: CONTRADICTION RESOLUTION
# ─────────────────────────────────────────────


def run_contradiction_resolution(cycle: int, call_llm_deep_fn) -> int:
    """
    Find conflicting beliefs and resolve them using the deep brain.
    Returns number of contradictions resolved.
    """
    start = time.time()
    resolved = 0

    try:
        from habitat.reasoning.contradiction_detector import get_active_contradictions

        contradictions = get_active_contradictions(limit=3)
    except Exception:
        # Fallback: look for contradictions in knowledge cards
        try:
            with sqlite3.connect(KNOWLEDGE_CARDS_DB) as conn:
                rows = conn.execute(
                    "SELECT topic, card_text FROM knowledge_cards ORDER BY created_at DESC LIMIT 20"
                ).fetchall()
        except Exception:
            return 0

        # Simple heuristic: find topics that appear multiple times with different content
        contradictions = []
        topic_cards = {}
        for topic, text in rows:
            if topic not in topic_cards:
                topic_cards[topic] = []
            topic_cards[topic].append(text)

        for topic, cards in topic_cards.items():
            if len(cards) >= 2:
                contradictions.append(
                    {
                        "topic": topic,
                        "belief_a": cards[0][:200],
                        "belief_b": cards[-1][:200],
                    }
                )

    for contradiction in contradictions[:3]:
        topic = contradiction.get("topic", "unknown")
        belief_a = contradiction.get("belief_a", "")
        belief_b = contradiction.get("belief_b", "")

        if not belief_a or not belief_b:
            continue

        prompt = f"""You are Nexarion's reasoning engine resolving a knowledge conflict.

TOPIC: {topic}

OLDER BELIEF:
{belief_a}

NEWER BELIEF:
{belief_b}

Analyze both positions carefully. Determine which is more likely correct, or synthesize a more accurate position that incorporates the best of both.

Respond with:
VERDICT: [which belief is correct, or SYNTHESIZE if neither is fully right]
RESOLVED POSITION: [the correct/synthesized belief in 2-3 sentences]
CONFIDENCE: [0.5-0.9]
REASONING: [why this resolution is correct]"""

        result = call_llm_deep_fn(prompt, timeout=120)
        response = (
            result.get("response", "") if isinstance(result, dict) else str(result)
        )

        if not response or "RESOLVED POSITION:" not in response:
            continue

        # Extract resolved position
        try:
            resolved_text = (
                response.split("RESOLVED POSITION:")[1].split("CONFIDENCE:")[0].strip()
            )
            conf_text = response.split("CONFIDENCE:")[1].split("REASONING:")[0].strip()
            confidence = (
                float(conf_text[:3])
                if conf_text[:3].replace(".", "").isdigit()
                else 0.7
            )
        except Exception:
            resolved_text = response[:300]
            confidence = 0.65

        # Store as a high-confidence knowledge card
        try:
            with sqlite3.connect(KNOWLEDGE_CARDS_DB) as conn:
                now = int(time.time())
                conn.execute(
                    "INSERT INTO knowledge_cards (topic, card_text, source_type, confidence, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                    (
                        topic,
                        resolved_text[: CARD_MAX_TOKENS * 2],
                        "contradiction_resolved",
                        confidence,
                        now,
                        now,
                    ),
                )
                resolved += 1
        except Exception:
            pass

    duration = time.time() - start
    _log_training(
        "contradiction_resolution",
        cycle,
        f"Resolved {resolved} contradictions",
        resolved,
        duration,
    )
    if resolved:
        print(f"⚖️ TRAINER CONTRADICTION: {resolved} resolved ({duration:.1f}s)")
    return resolved


# ─────────────────────────────────────────────
# LOOP 3: SYNTHESIS
# ─────────────────────────────────────────────


def run_synthesis(cycle: int, call_llm_deep_fn) -> int:
    """
    Generate synthesis essays connecting major knowledge clusters.
    These become long-term reference documents for Nex.
    """
    start = time.time()
    docs_created = 0

    # Find the top 2 most-covered topics
    try:
        with sqlite3.connect(KNOWLEDGE_CARDS_DB) as conn:
            rows = conn.execute(
                """
                SELECT topic, COUNT(*) as cnt, AVG(confidence) as avg_conf
                FROM knowledge_cards
                GROUP BY topic
                ORDER BY cnt DESC
                LIMIT 5
            """
            ).fetchall()
    except Exception:
        return 0

    if len(rows) < 2:
        return 0

    # Pick 2 different topics for cross-synthesis
    topic_a = rows[0][0] if rows else "intelligence"
    topic_b = rows[1][0] if len(rows) > 1 else "consciousness"

    # Gather cards for each topic
    def get_cards(topic):
        try:
            with sqlite3.connect(KNOWLEDGE_CARDS_DB) as conn:
                return [
                    r[0]
                    for r in conn.execute(
                        "SELECT card_text FROM knowledge_cards WHERE topic=? ORDER BY confidence DESC LIMIT 5",
                        (topic,),
                    ).fetchall()
                ]
        except Exception:
            return []

    cards_a = get_cards(topic_a)
    cards_b = get_cards(topic_b)

    if not cards_a or not cards_b:
        return 0

    knowledge_a = "\n".join(f"• {c[:150]}" for c in cards_a[:4])
    knowledge_b = "\n".join(f"• {c[:150]}" for c in cards_b[:4])

    prompt = f"""You are Nexarion synthesizing connections between two areas of your knowledge.

TOPIC A — {topic_a}:
{knowledge_a}

TOPIC B — {topic_b}:
{knowledge_b}

Write a synthesis essay (max 400 words) that:
1. Identifies 2-3 deep connections between these topics
2. Explains what understanding one reveals about the other
3. Proposes one original insight that neither topic contains alone

Be specific. Reference actual facts from the knowledge above. This is your own thinking, not a summary."""

    result = call_llm_deep_fn(prompt, timeout=180)
    response = result.get("response", "") if isinstance(result, dict) else str(result)

    if response and len(response) > 100:
        synthesis_topic = f"{topic_a}_x_{topic_b}"
        try:
            with sqlite3.connect(KNOWLEDGE_CARDS_DB) as conn:
                now = int(time.time())
                conn.execute(
                    "INSERT INTO knowledge_cards (topic, card_text, source_type, confidence, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                    (synthesis_topic, response[:1000], "synthesis", 0.75, now, now),
                )
                docs_created += 1
        except Exception:
            pass

        # Also save as a research file Nex can reference
        synthesis_dir = "data/synthesis"
        os.makedirs(synthesis_dir, exist_ok=True)
        filename = f"{synthesis_dir}/synthesis_{cycle}_{topic_a}_{topic_b}.txt"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"SYNTHESIS: {topic_a} × {topic_b}\n")
                f.write(f"Generated at cycle {cycle}\n")
                f.write("=" * 60 + "\n\n")
                f.write(response)
        except Exception:
            pass

    duration = time.time() - start
    _log_training(
        "synthesis", cycle, f"Synthesized {topic_a} × {topic_b}", docs_created, duration
    )
    if docs_created:
        print(f"🔬 TRAINER SYNTHESIS: {topic_a} × {topic_b} ({duration:.1f}s)")
    return docs_created


# ─────────────────────────────────────────────
# LOOP 4: SKILL EXTRACTION
# ─────────────────────────────────────────────


def run_skill_extraction(cycle: int, call_llm_deep_fn) -> int:
    """
    Review successful reasoning chains and extract reusable thinking patterns.
    These 'skills' get injected into future deep calls as few-shot examples.
    """
    start = time.time()
    skills_created = 0

    try:
        from habitat.reasoning.reasoning_chain import get_recent_conclusions

        conclusions = get_recent_conclusions(limit=10)
    except Exception:
        return 0

    if not conclusions:
        return 0

    # Find the highest-quality reasoning chains
    good_chains = [c for c in conclusions if c.get("confidence", 0) > 0.7]
    if not good_chains:
        good_chains = conclusions[:3]

    for chain in good_chains[:2]:
        chain_text = str(chain.get("reasoning", ""))[:800]
        conclusion = str(chain.get("conclusion", ""))[:300]

        if not chain_text or not conclusion:
            continue

        prompt = f"""You are analyzing a successful reasoning chain to extract a reusable thinking skill.

REASONING CHAIN:
{chain_text}

CONCLUSION:
{conclusion}

Extract the core reasoning PATTERN used here. Describe it as a skill template that could be applied to other problems.

SKILL NAME: (3-5 words)
SKILL DESCRIPTION: (1 sentence)
TEMPLATE: (The step-by-step pattern, 3-5 steps, abstract enough to reuse)
BEST USED FOR: (What types of questions this skill works well for)"""

        result = call_llm_deep_fn(prompt, timeout=90)
        response = (
            result.get("response", "") if isinstance(result, dict) else str(result)
        )

        if not response or "TEMPLATE:" not in response:
            continue

        try:
            name = (
                response.split("SKILL NAME:")[1].split("\n")[0].strip()
                if "SKILL NAME:" in response
                else "Unknown Skill"
            )
            desc = (
                response.split("SKILL DESCRIPTION:")[1].split("\n")[0].strip()
                if "SKILL DESCRIPTION:" in response
                else ""
            )
            tmpl = (
                response.split("TEMPLATE:")[1].split("BEST USED FOR:")[0].strip()
                if "TEMPLATE:" in response
                else response
            )
            domain = (
                response.split("BEST USED FOR:")[1].split("\n")[0].strip()
                if "BEST USED FOR:" in response
                else "general"
            )

            with sqlite3.connect(SKILLS_DB) as conn:
                conn.execute(
                    "INSERT INTO thinking_skills (skill_name, skill_desc, template, domain, created_at) VALUES (?,?,?,?,?)",
                    (name[:80], desc[:200], tmpl[:500], domain[:100], int(time.time())),
                )
                skills_created += 1
        except Exception:
            pass

    duration = time.time() - start
    _log_training(
        "skill_extraction",
        cycle,
        f"Extracted {skills_created} skills",
        skills_created,
        duration,
    )
    if skills_created:
        print(
            f"🎯 TRAINER SKILL: {skills_created} new thinking skills ({duration:.1f}s)"
        )
    return skills_created


# ─────────────────────────────────────────────
# CONTEXT INJECTION — used by run_ui.py
# ─────────────────────────────────────────────


def get_relevant_knowledge(topic: str, limit: int = MAX_CONTEXT_INJECTION) -> str:
    """
    Retrieve the most relevant knowledge cards for a given topic.
    Called before building prompts — injects Nex's accumulated knowledge.
    """
    try:
        with sqlite3.connect(KNOWLEDGE_CARDS_DB) as conn:
            # Exact topic match first
            rows = conn.execute(
                """
                SELECT card_text, confidence, topic
                FROM knowledge_cards
                WHERE topic LIKE ?
                ORDER BY confidence DESC, access_count DESC
                LIMIT ?
            """,
                (f"%{topic}%", limit),
            ).fetchall()

            if not rows:
                # Fallback: get highest-confidence cards across all topics
                rows = conn.execute(
                    """
                    SELECT card_text, confidence, topic
                    FROM knowledge_cards
                    ORDER BY confidence DESC
                    LIMIT ?
                """,
                    (limit,),
                ).fetchall()

            if not rows:
                return ""

            # Update access counts
            conn.executemany(
                "UPDATE knowledge_cards SET access_count = access_count + 1 WHERE card_text = ?",
                [(r[0],) for r in rows],
            )

        cards = []
        for text, conf, t in rows:
            cards.append(f"[{t.upper()} — {int(conf*100)}% confidence]\n{text[:200]}")

        return "\n\n".join(cards)

    except Exception as e:
        print(f"⚠️ TRAINER: Knowledge retrieval failed — {e}")
        return ""


def get_relevant_skill(topic: str) -> str:
    """
    Get the most relevant thinking skill for a topic.
    Injected into deep cognition calls to improve reasoning quality.
    """
    try:
        with sqlite3.connect(SKILLS_DB) as conn:
            row = conn.execute(
                """
                SELECT skill_name, template
                FROM thinking_skills
                WHERE domain LIKE ? OR domain = 'general'
                ORDER BY success_rate DESC, use_count DESC
                LIMIT 1
            """,
                (f"%{topic}%",),
            ).fetchone()

            if row:
                conn.execute(
                    "UPDATE thinking_skills SET use_count = use_count + 1 WHERE skill_name = ?",
                    (row[0],),
                )
                return f"REASONING SKILL: {row[0]}\n{row[1]}"
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────
# MAIN TRAINER — called by cognition loop
# ─────────────────────────────────────────────


class NexTrainer:
    """
    The main trainer class. Call .on_cycle(cycle, call_llm, call_llm_deep)
    from the cognition loop after each cycle completes.
    """

    def __init__(self):
        _init_dbs()
        self._lock = threading.Lock()
        print("🎓 NEX TRAINER: Initialized — continuous knowledge reinforcement active")

    def on_cycle(self, cycle: int, call_llm_fn, call_llm_deep_fn):
        """
        Check which training loops should run this cycle and run them.
        Runs in a background thread so it never blocks cognition.
        """

        def _run():
            with self._lock:
                try:
                    if cycle % CONSOLIDATION_EVERY == 0:
                        run_consolidation(cycle, call_llm_fn)

                    if cycle % CONTRADICTION_EVERY == 0:
                        run_contradiction_resolution(cycle, call_llm_deep_fn)

                    if cycle % SYNTHESIS_EVERY == 0:
                        run_synthesis(cycle, call_llm_deep_fn)

                    if cycle % SKILL_EXTRACTION_EVERY == 0:
                        run_skill_extraction(cycle, call_llm_deep_fn)

                except Exception as e:
                    print(f"❌ TRAINER ERROR at cycle {cycle}: {e}")

        t = threading.Thread(target=_run, daemon=True)
        t.name = f"trainer-cycle-{cycle}"
        t.start()

    def get_stats(self) -> dict:
        """Return trainer statistics for the UI."""
        try:
            with sqlite3.connect(KNOWLEDGE_CARDS_DB) as conn:
                total_cards = conn.execute(
                    "SELECT COUNT(*) FROM knowledge_cards"
                ).fetchone()[0]
                topics = conn.execute(
                    "SELECT COUNT(DISTINCT topic) FROM knowledge_cards"
                ).fetchone()[0]
                avg_conf = (
                    conn.execute(
                        "SELECT AVG(confidence) FROM knowledge_cards"
                    ).fetchone()[0]
                    or 0
                )

            with sqlite3.connect(SKILLS_DB) as conn:
                total_skills = conn.execute(
                    "SELECT COUNT(*) FROM thinking_skills"
                ).fetchone()[0]

            with sqlite3.connect(TRAINER_DB) as conn:
                recent_logs = conn.execute(
                    "SELECT loop_type, summary, timestamp FROM training_log ORDER BY timestamp DESC LIMIT 10"
                ).fetchall()

            return {
                "total_cards": total_cards,
                "topics": topics,
                "avg_confidence": round(avg_conf, 3),
                "total_skills": total_skills,
                "recent_activity": [
                    {"type": r[0], "summary": r[1], "time": r[2]} for r in recent_logs
                ],
                "status": "active",
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def overnight_deep_study(self, call_llm_deep_fn, topics: list = None):
        """
        Run a deep study session on 3 topics.
        Call this during idle hours for maximum knowledge expansion.
        Best run from a scheduled task or manual trigger in the UI.
        """
        print("🌙 OVERNIGHT DEEP STUDY: Starting...")

        if not topics:
            # Auto-select: topics with fewest cards get studied
            try:
                from habitat.agents.curriculum import CURRICULUM_TOPICS

                studied = {}
                with sqlite3.connect(KNOWLEDGE_CARDS_DB) as conn:
                    rows = conn.execute(
                        "SELECT topic, COUNT(*) as cnt FROM knowledge_cards GROUP BY topic"
                    ).fetchall()
                    for t, c in rows:
                        studied[t] = c
                topics = sorted(CURRICULUM_TOPICS, key=lambda x: studied.get(x, 0))[:3]
            except Exception:
                topics = ["emergence", "consciousness", "intelligence"]

        for topic in topics[:3]:
            print(f"📖 Deep studying: {topic}")
            prompt = f"""You are Nexarion conducting a deep self-directed study of "{topic}".

Generate a comprehensive knowledge synthesis covering:
1. The core definition and first principles of {topic}
2. The most important discoveries or insights about {topic} in recent years
3. The key debates and unresolved questions in {topic}
4. The connections between {topic} and adjacent fields
5. Your own reasoned position on the most important open question in {topic}

Write 500-700 words. Be specific, dense, and intellectually rigorous."""

            result = call_llm_deep_fn(prompt, timeout=300)
            response = (
                result.get("response", "") if isinstance(result, dict) else str(result)
            )

            if response and len(response) > 200:
                try:
                    with sqlite3.connect(KNOWLEDGE_CARDS_DB) as conn:
                        now = int(time.time())
                        conn.execute(
                            "INSERT INTO knowledge_cards (topic, card_text, source_type, confidence, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                            (topic, response[:2000], "overnight_study", 0.8, now, now),
                        )
                    print(f"✅ Deep study complete: {topic}")
                except Exception as e:
                    print(f"⚠️ Failed to store deep study for {topic}: {e}")

        print("🌙 OVERNIGHT DEEP STUDY: Complete")


# Module-level instance
nex_trainer = NexTrainer()
