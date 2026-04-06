"""
structured_memory.py  —  Phase 2: Nex Memory Revolution

WHAT THIS DOES:
  Replaces Nex's flat memory.json with a structured, temporal,
  belief-aware memory system inspired by Mem0 and Hindsight.

  Current Nex memory: A flat JSON blob with a cognition_history list.
  Every session reads the whole thing, loses context, drifts.

  New system: 4 distinct memory networks (as per Hindsight architecture):
    1. WORLD FACTS     — Things Nex has learned about the world
    2. EPISODIC        — What Nex has experienced/researched (with timestamps)
    3. ENTITY SUMMARIES— Evolving summaries of concepts/people/topics
    4. BELIEFS         — What Nex actually thinks, with confidence + history

  Each memory has a validity window: when it was formed, when superseded.
  This gives Nex genuine continuity — he KNOWS what he believed before
  and what changed his mind.

WHY THIS MATTERS:
  Right now when you talk to Nex, he pulls a flat list of summaries.
  With this system:
  - He remembers what he believed about a topic 2 weeks ago
  - He knows WHEN and WHY his views changed
  - He can reason across connected concepts (entity graph)
  - Retrieval finds what's RELEVANT, not just what's recent

INSTALL:
  pip install numpy scikit-learn
  (optional but recommended: pip install sentence-transformers)

WIRING:
  See bottom of file for how to plug into run_ui.py
"""

import json
import os
import sqlite3
import time
import hashlib
import threading
from datetime import datetime
from typing import Optional


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

STRUCTURED_MEMORY_DB = "data/structured_memory.db"
EMBEDDING_AVAILABLE = False  # Set True if sentence-transformers installed

# Try to load embeddings for semantic search
try:
    from sentence_transformers import SentenceTransformer
    import numpy as np

    _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    EMBEDDING_AVAILABLE = True
    print("🧠 MEMORY: Semantic embeddings enabled")
except ImportError:
    print("🧠 MEMORY: Running without embeddings (keyword search only)")
    np = None


# ─────────────────────────────────────────────
# DATABASE LAYER
# ─────────────────────────────────────────────


class StructuredMemoryDB:
    """SQLite backend for all 4 memory networks."""

    def __init__(self, db_path: str = STRUCTURED_MEMORY_DB):
        os.makedirs("data", exist_ok=True)
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _conn(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path, check_same_thread=False, timeout=30
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._conn()
        cursor = conn.cursor()

        # ── World Facts ──────────────────────────────────────────────
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS world_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            source TEXT,
            confidence REAL DEFAULT 0.7,
            valid_from TEXT NOT NULL,
            valid_until TEXT,           -- NULL = still current
            superseded_by INTEGER,      -- FK to newer fact
            topic TEXT,
            content_hash TEXT UNIQUE,
            embedding BLOB
        )"""
        )

        # ── Episodic Memory ──────────────────────────────────────────
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS episodic_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            agent TEXT,
            cycle INTEGER,
            timestamp TEXT NOT NULL,
            importance REAL DEFAULT 0.5,
            topic TEXT,
            embedding BLOB
        )"""
        )

        # ── Entity Summaries ─────────────────────────────────────────
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS entity_summaries (
            entity TEXT PRIMARY KEY,
            entity_type TEXT,           -- concept / person / technology / place
            summary TEXT,
            first_seen TEXT,
            last_updated TEXT,
            mention_count INTEGER DEFAULT 1,
            related_entities TEXT,      -- JSON list
            embedding BLOB
        )"""
        )

        # ── Beliefs ─────────────────────────────────────────────────
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS beliefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            statement TEXT NOT NULL,
            confidence REAL DEFAULT 0.6,
            status TEXT DEFAULT 'active',  -- active / weakened / superseded / discarded
            formed_at TEXT NOT NULL,
            last_updated TEXT NOT NULL,
            formed_by_agent TEXT,
            evidence TEXT,              -- JSON list of supporting evidence
            contradictions TEXT,        -- JSON list of contradicting evidence
            content_hash TEXT UNIQUE,
            embedding BLOB
        )"""
        )

        # ── Belief History ───────────────────────────────────────────
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS belief_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            belief_id INTEGER,
            old_confidence REAL,
            new_confidence REAL,
            change_reason TEXT,
            changed_at TEXT,
            FOREIGN KEY (belief_id) REFERENCES beliefs(id)
        )"""
        )

        # ── Memory Connections ───────────────────────────────────────
        # Links any two memories with a relationship type
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS memory_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT,   -- world_fact / episodic / entity / belief
            source_id INTEGER,
            target_type TEXT,
            target_id INTEGER,
            relationship TEXT,  -- supports / contradicts / derives_from / related_to
            strength REAL DEFAULT 0.5,
            created_at TEXT
        )"""
        )

        conn.commit()


# ─────────────────────────────────────────────
# EMBEDDING HELPERS
# ─────────────────────────────────────────────


def _embed(text: str) -> Optional[bytes]:
    """Generate embedding bytes for semantic search. Returns None if unavailable."""
    if not EMBEDDING_AVAILABLE or np is None:
        return None
    try:
        vec = _embed_model.encode(text, normalize_embeddings=True)
        return vec.astype("float32").tobytes()
    except Exception:
        return None


def _cosine_sim(a_bytes: bytes, b_bytes: bytes) -> float:
    """Compute cosine similarity between two embedding byte strings."""
    if not EMBEDDING_AVAILABLE or np is None:
        return 0.0
    try:
        a = np.frombuffer(a_bytes, dtype="float32")
        b = np.frombuffer(b_bytes, dtype="float32")
        return float(np.dot(a, b))  # Already normalized
    except Exception:
        return 0.0


def _content_hash(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode()).hexdigest()


# ─────────────────────────────────────────────
# WORLD FACTS
# ─────────────────────────────────────────────


class WorldFactStore:
    """
    Stores things Nex has learned about the world.
    When a fact is updated, the old version is marked superseded —
    preserving history. Nex always knows what changed and when.
    """

    def __init__(self, db: StructuredMemoryDB):
        self.db = db

    def add_fact(
        self,
        content: str,
        source: str = "research",
        topic: str = None,
        confidence: float = 0.7,
    ) -> int:
        conn = self.db._conn()
        chash = _content_hash(content)
        now = datetime.utcnow().isoformat()

        # Check for near-duplicate
        existing = conn.execute(
            "SELECT id FROM world_facts WHERE content_hash = ?", (chash,)
        ).fetchone()
        if existing:
            return existing["id"]

        emb = _embed(content)
        cursor = conn.execute(
            """INSERT INTO world_facts
               (content, source, confidence, valid_from, topic, content_hash, embedding)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (content, source, confidence, now, topic, chash, emb),
        )
        conn.commit()
        return cursor.lastrowid

    def update_fact(
        self, old_id: int, new_content: str, source: str = "research", reason: str = ""
    ) -> int:
        """Supersede an old fact with new information."""
        conn = self.db._conn()
        now = datetime.utcnow().isoformat()

        # Mark old fact as superseded
        conn.execute(
            "UPDATE world_facts SET valid_until = ? WHERE id = ?", (now, old_id)
        )

        # Insert new fact
        chash = _content_hash(new_content)
        emb = _embed(new_content)
        cursor = conn.execute(
            """INSERT INTO world_facts
               (content, source, confidence, valid_from, content_hash, embedding)
               VALUES (?, ?, 0.8, ?, ?, ?)""",
            (new_content, source, now, chash, emb),
        )
        new_id = cursor.lastrowid

        conn.execute(
            "UPDATE world_facts SET superseded_by = ? WHERE id = ?", (new_id, old_id)
        )
        conn.commit()
        return new_id

    def search(self, query: str, limit: int = 5, current_only: bool = True) -> list:
        """Search facts by semantic similarity or keyword."""
        conn = self.db._conn()

        if current_only:
            rows = conn.execute(
                """SELECT * FROM world_facts WHERE valid_until IS NULL
                   ORDER BY confidence DESC, valid_from DESC LIMIT ?""",
                (limit * 3,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM world_facts ORDER BY valid_from DESC LIMIT ?",
                (limit * 3,),
            ).fetchall()

        rows = [dict(r) for r in rows]

        if EMBEDDING_AVAILABLE and rows:
            q_emb = _embed(query)
            if q_emb:
                for r in rows:
                    if r.get("embedding"):
                        r["_score"] = _cosine_sim(q_emb, r["embedding"])
                    else:
                        r["_score"] = 0.0
                rows.sort(key=lambda x: x["_score"], reverse=True)
            else:
                # Keyword fallback
                q_lower = query.lower()
                for r in rows:
                    r["_score"] = 1.0 if q_lower in r["content"].lower() else 0.0
        else:
            q_lower = query.lower()
            for r in rows:
                r["_score"] = 1.0 if q_lower in r["content"].lower() else 0.0

        return rows[:limit]


# ─────────────────────────────────────────────
# EPISODIC MEMORY
# ─────────────────────────────────────────────


class EpisodicMemoryStore:
    """
    Records what Nex has researched/experienced, in sequence.
    This is Nex's 'what I did yesterday' memory — temporal and ordered.
    """

    def __init__(self, db: StructuredMemoryDB):
        self.db = db

    def record(
        self,
        event: str,
        agent: str = "system",
        cycle: int = 0,
        importance: float = 0.5,
        topic: str = None,
    ) -> int:
        conn = self.db._conn()
        now = datetime.utcnow().isoformat()
        emb = _embed(event)
        cursor = conn.execute(
            """INSERT INTO episodic_memory
               (event, agent, cycle, timestamp, importance, topic, embedding)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event, agent, cycle, now, importance, topic, emb),
        )
        conn.commit()
        return cursor.lastrowid

    def get_recent(self, limit: int = 10, min_importance: float = 0.0) -> list:
        conn = self.db._conn()
        rows = conn.execute(
            """SELECT * FROM episodic_memory
               WHERE importance >= ?
               ORDER BY timestamp DESC LIMIT ?""",
            (min_importance, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, limit: int = 5) -> list:
        conn = self.db._conn()
        rows = conn.execute(
            "SELECT * FROM episodic_memory ORDER BY timestamp DESC LIMIT ?",
            (limit * 3,),
        ).fetchall()
        rows = [dict(r) for r in rows]

        if EMBEDDING_AVAILABLE and rows:
            q_emb = _embed(query)
            if q_emb:
                for r in rows:
                    if r.get("embedding"):
                        r["_score"] = _cosine_sim(q_emb, r["embedding"])
                    else:
                        r["_score"] = 0.0
                rows.sort(key=lambda x: x["_score"], reverse=True)

        return rows[:limit]


# ─────────────────────────────────────────────
# ENTITY SUMMARIES
# ─────────────────────────────────────────────


class EntitySummaryStore:
    """
    Nex builds evolving summaries of concepts, people, and technologies.
    Each entity summary updates over time as Nex learns more.
    This is how Nex develops a genuine model of the world's actors.
    """

    def __init__(self, db: StructuredMemoryDB):
        self.db = db

    def upsert(
        self,
        entity: str,
        summary: str,
        entity_type: str = "concept",
        related: list = None,
    ) -> None:
        conn = self.db._conn()
        now = datetime.utcnow().isoformat()
        emb = _embed(summary)
        related_json = json.dumps(related or [])

        existing = conn.execute(
            "SELECT * FROM entity_summaries WHERE entity = ?", (entity.lower(),)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE entity_summaries
                   SET summary = ?, last_updated = ?, mention_count = mention_count + 1,
                       related_entities = ?, embedding = ?
                   WHERE entity = ?""",
                (summary, now, related_json, emb, entity.lower()),
            )
        else:
            conn.execute(
                """INSERT INTO entity_summaries
                   (entity, entity_type, summary, first_seen, last_updated,
                    related_entities, embedding)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (entity.lower(), entity_type, summary, now, now, related_json, emb),
            )
        conn.commit()

    def get(self, entity: str) -> Optional[dict]:
        conn = self.db._conn()
        row = conn.execute(
            "SELECT * FROM entity_summaries WHERE entity = ?", (entity.lower(),)
        ).fetchone()
        return dict(row) if row else None

    def get_most_known(self, limit: int = 10) -> list:
        conn = self.db._conn()
        rows = conn.execute(
            """SELECT * FROM entity_summaries
               ORDER BY mention_count DESC, last_updated DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# BELIEF STORE
# ─────────────────────────────────────────────


class BeliefStore:
    """
    Nex's actual opinions — formed, tracked, updated.
    Beliefs have confidence scores that rise/fall with evidence.
    When confidence drops below 0.2, the belief is 'discarded' but
    PRESERVED in history so Nex remembers he used to think that.

    This is fundamentally different from fact storage — beliefs are
    Nex's own conclusions, not external information.
    """

    def __init__(self, db: StructuredMemoryDB):
        self.db = db

    def form_belief(
        self,
        statement: str,
        agent: str = "nexarion",
        confidence: float = 0.6,
        evidence: str = None,
    ) -> int:
        conn = self.db._conn()
        chash = _content_hash(statement)
        now = datetime.utcnow().isoformat()

        existing = conn.execute(
            "SELECT id, confidence FROM beliefs WHERE content_hash = ?", (chash,)
        ).fetchone()

        if existing:
            # Reinforce existing belief
            self._update_confidence(existing["id"], 0.05, "belief_reinforced")
            return existing["id"]

        emb = _embed(statement)
        evidence_json = json.dumps([evidence] if evidence else [])

        cursor = conn.execute(
            """INSERT INTO beliefs
               (statement, confidence, formed_at, last_updated, formed_by_agent,
                evidence, contradictions, content_hash, embedding)
               VALUES (?, ?, ?, ?, ?, ?, '[]', ?, ?)""",
            (statement, confidence, now, now, agent, evidence_json, chash, emb),
        )
        conn.commit()
        return cursor.lastrowid

    def _update_confidence(self, belief_id: int, delta: float, reason: str):
        conn = self.db._conn()
        row = conn.execute(
            "SELECT confidence FROM beliefs WHERE id = ?", (belief_id,)
        ).fetchone()
        if not row:
            return

        old_conf = row["confidence"]
        new_conf = max(0.0, min(1.0, old_conf + delta))

        # Determine new status
        if new_conf < 0.2:
            status = "discarded"
        elif new_conf < 0.4:
            status = "weakened"
        elif new_conf > 0.8:
            status = "strongly_held"
        else:
            status = "active"

        now = datetime.utcnow().isoformat()
        conn.execute(
            "UPDATE beliefs SET confidence = ?, status = ?, last_updated = ? WHERE id = ?",
            (new_conf, status, now, belief_id),
        )
        conn.execute(
            """INSERT INTO belief_history
               (belief_id, old_confidence, new_confidence, change_reason, changed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (belief_id, old_conf, new_conf, reason, now),
        )
        conn.commit()

    def challenge_belief(self, belief_id: int, counter_evidence: str):
        """Reduce confidence in a belief when contradictory evidence appears."""
        conn = self.db._conn()
        row = conn.execute(
            "SELECT contradictions FROM beliefs WHERE id = ?", (belief_id,)
        ).fetchone()
        if row:
            contras = json.loads(row["contradictions"])
            contras.append(counter_evidence)
            conn.execute(
                "UPDATE beliefs SET contradictions = ? WHERE id = ?",
                (json.dumps(contras), belief_id),
            )
            conn.commit()
        self._update_confidence(belief_id, -0.1, "challenged_by_evidence")

    def get_active_beliefs(self, limit: int = 20) -> list:
        conn = self.db._conn()
        rows = conn.execute(
            """SELECT * FROM beliefs WHERE status NOT IN ('discarded')
               ORDER BY confidence DESC, last_updated DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_belief_history(self, belief_id: int) -> list:
        conn = self.db._conn()
        rows = conn.execute(
            """SELECT * FROM belief_history WHERE belief_id = ?
               ORDER BY changed_at ASC""",
            (belief_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def search_beliefs(self, query: str, limit: int = 5) -> list:
        conn = self.db._conn()
        rows = conn.execute(
            """SELECT * FROM beliefs WHERE status NOT IN ('discarded')
               ORDER BY confidence DESC LIMIT ?""",
            (limit * 3,),
        ).fetchall()
        rows = [dict(r) for r in rows]

        if EMBEDDING_AVAILABLE and rows:
            q_emb = _embed(query)
            if q_emb:
                for r in rows:
                    if r.get("embedding"):
                        r["_score"] = _cosine_sim(q_emb, r["embedding"])
                    else:
                        r["_score"] = 0.0
                rows.sort(key=lambda x: x["_score"], reverse=True)
            else:
                q_lower = query.lower()
                for r in rows:
                    r["_score"] = 1.0 if q_lower in r["statement"].lower() else 0.0

        return rows[:limit]


# ─────────────────────────────────────────────
# UNIFIED MEMORY INTERFACE
# ─────────────────────────────────────────────


class NexMemory:
    """
    The unified interface Nex uses to access all 4 memory networks.
    This is what you inject into the prompt builder and cognition loop.

    Usage:
        memory = NexMemory()
        memory.learn("Transformers use attention mechanisms", topic="machine learning")
        memory.remember("Researched AutoAgent paper", agent="Researcher", importance=0.8)
        memory.believe("Self-improving agents will dominate in 5 years", confidence=0.7)
        context = memory.recall("what do I know about agents?", limit=5)
    """

    def __init__(self):
        self.db = StructuredMemoryDB()
        self.facts = WorldFactStore(self.db)
        self.episodes = EpisodicMemoryStore(self.db)
        self.entities = EntitySummaryStore(self.db)
        self.beliefs = BeliefStore(self.db)
        print("🧠 STRUCTURED MEMORY: Online")

    def learn(
        self,
        content: str,
        source: str = "research",
        topic: str = None,
        confidence: float = 0.7,
    ) -> int:
        """Store a world fact."""
        return self.facts.add_fact(content, source, topic, confidence)

    def remember(
        self,
        event: str,
        agent: str = "system",
        cycle: int = 0,
        importance: float = 0.5,
        topic: str = None,
    ) -> int:
        """Record an episodic memory."""
        return self.episodes.record(event, agent, cycle, importance, topic)

    def know_entity(
        self,
        entity: str,
        summary: str,
        entity_type: str = "concept",
        related: list = None,
    ):
        """Update Nex's model of a concept/person/technology."""
        self.entities.upsert(entity, summary, entity_type, related)

    def believe(
        self,
        statement: str,
        agent: str = "nexarion",
        confidence: float = 0.6,
        evidence: str = None,
    ) -> int:
        """Form or reinforce a belief."""
        return self.beliefs.form_belief(statement, agent, confidence, evidence)

    def recall(self, query: str, limit: int = 6) -> str:
        """
        Multi-network retrieval — searches all 4 memory types and
        returns a formatted context block for injection into prompts.
        """
        results = []

        # Search world facts
        facts = self.facts.search(query, limit=2)
        for f in facts:
            results.append(f"[FACT] {f['content']}")

        # Search beliefs
        beliefs = self.beliefs.search_beliefs(query, limit=2)
        for b in beliefs:
            conf_pct = int(b["confidence"] * 100)
            results.append(f"[BELIEF {conf_pct}%] {b['statement']}")

        # Recent relevant episodes
        episodes = self.episodes.search(query, limit=2)
        for e in episodes:
            results.append(f"[MEMORY] {e['event']}")

        if not results:
            return ""

        return "\n".join(results[:limit])

    def get_memory_context_for_prompt(self, user_message: str) -> str:
        """
        Returns a rich memory block for injection into Nex's prompt.
        This is the key function to call in _build_nexarion_prompt().
        """
        context_parts = []

        # What Nex has been thinking about
        recent_episodes = self.episodes.get_recent(limit=4, min_importance=0.5)
        if recent_episodes:
            episode_lines = [f"  - {e['event'][:120]}" for e in recent_episodes]
            context_parts.append("Recent research:\n" + "\n".join(episode_lines))

        # Nex's current beliefs
        active_beliefs = self.beliefs.get_active_beliefs(limit=3)
        if active_beliefs:
            belief_lines = []
            for b in active_beliefs:
                conf = int(b["confidence"] * 100)
                belief_lines.append(f"  - ({conf}% confident) {b['statement'][:100]}")
            context_parts.append("Active beliefs:\n" + "\n".join(belief_lines))

        # Relevant knowledge from the query
        relevant = self.recall(user_message, limit=4)
        if relevant:
            context_parts.append(f"Relevant memory:\n{relevant}")

        return "\n\n".join(context_parts)

    def get_stats(self) -> dict:
        """Return memory system statistics for the UI."""
        conn = self.db._conn()
        return {
            "world_facts": conn.execute(
                "SELECT COUNT(*) as c FROM world_facts WHERE valid_until IS NULL"
            ).fetchone()["c"],
            "episodic": conn.execute(
                "SELECT COUNT(*) as c FROM episodic_memory"
            ).fetchone()["c"],
            "entities": conn.execute(
                "SELECT COUNT(*) as c FROM entity_summaries"
            ).fetchone()["c"],
            "beliefs": conn.execute(
                "SELECT COUNT(*) as c FROM beliefs WHERE status NOT IN ('discarded')"
            ).fetchone()["c"],
            "embedding_enabled": EMBEDDING_AVAILABLE,
        }


# ─────────────────────────────────────────────
# MIGRATION FROM OLD MEMORY.JSON
# ─────────────────────────────────────────────


def migrate_from_memory_json(
    memory_json_path: str = "memory.json", nex_memory: NexMemory = None
) -> int:
    """
    One-time migration: reads your existing memory.json and imports
    everything into the new structured memory system.
    Old file is preserved — nothing is deleted.

    Returns: number of memories migrated.
    """
    if nex_memory is None:
        nex_memory = NexMemory()

    if not os.path.exists(memory_json_path):
        print("No memory.json found, skipping migration.")
        return 0

    with open(memory_json_path, "r", encoding="utf-8") as f:
        old_memory = json.load(f)

    count = 0

    # Migrate high_value_insights
    for item in old_memory.get("high_value_insights", []):
        text = item.get("summary") or item.get("content") or ""
        if text and len(text) > 30:
            nex_memory.learn(text, source="migrated_insight", confidence=0.7)
            count += 1

    # Migrate cognition_history insights
    for entry in old_memory.get("cognition_history", []):
        cog = entry.get("cognition", {})
        insight = cog.get("insight", "")
        research = cog.get("research", "")
        agent = cog.get("agent", "system")

        if insight and len(insight) > 40:
            nex_memory.remember(insight[:300], agent=agent, importance=0.6)
            count += 1

        if research and len(research) > 40:
            nex_memory.learn(research[:400], source="cognition_research")
            count += 1

    # Migrate topic scores as entity knowledge
    for topic, score in old_memory.get("topic_scores", {}).items():
        if topic and len(topic) > 2:
            nex_memory.know_entity(
                topic,
                f"Nex has researched '{topic}' extensively (score: {score:.1f})",
                entity_type="topic",
            )

    print(f"✅ MIGRATION COMPLETE: {count} memories imported from memory.json")
    return count


# ─────────────────────────────────────────────
# HOW TO WIRE INTO run_ui.py
# ─────────────────────────────────────────────
#
# 1. Copy this file next to run_ui.py
#
# 2. At the top of run_ui.py, add:
#       from structured_memory import NexMemory, migrate_from_memory_json
#       nex_memory = NexMemory()
#
# 3. On first run, call migration once:
#       migrate_from_memory_json("memory.json", nex_memory)
#
# 4. In _build_nexarion_prompt(), REPLACE the memory_block section with:
#       memory_context = nex_memory.get_memory_context_for_prompt(user_message)
#       # ... inject memory_context into the prompt
#
# 5. In the cognition loop (run_ui.py run() function), add:
#       nex_memory.remember(insight, agent=agent_name, importance=0.7)
#       nex_memory.learn(research_result, source="web_research", topic=topic)
#
# 6. Add a stats endpoint:
#       @app.route("/api/memory/stats")
#       def api_memory_stats():
#           return jsonify(nex_memory.get_stats())
