import sqlite3
import os
from datetime import datetime

DB_PATH = "data/memory.db"
MAX_MEMORY_ENTRIES = 50000


class MemoryManager:

    def __init__(self):
        os.makedirs("data", exist_ok=True)

        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row

        self._ensure_tables()

        # runtime hypothesis storage
        self.hypotheses = []

    # =========================
    # DATABASE TABLES
    # =========================

    def _ensure_tables(self):
        cursor = self.conn.cursor()

        # =========================
        # EXISTING TABLES
        # =========================

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            content TEXT,
            summary TEXT,
            source TEXT,
            tier TEXT,
            importance INTEGER DEFAULT 0
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS research_threads (
            topic TEXT PRIMARY KEY,
            priority INTEGER,
            status TEXT,
            updates INTEGER,
            last_update TEXT,
            last_result TEXT
        )
        """
        )

        # =========================
        # 🧠 BELIEF TABLES (NEW)
        # =========================

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS beliefs (
            belief_id INTEGER PRIMARY KEY AUTOINCREMENT,
            statement TEXT UNIQUE,
            confidence REAL,
            created_by_agent TEXT,
            status TEXT,
            created_at TEXT,
            last_updated TEXT
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS belief_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            belief_id INTEGER,
            type TEXT, -- supporting / contradicting
            evidence TEXT,
            timestamp TEXT
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS belief_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            belief_id INTEGER,
            change_type TEXT,
            old_confidence REAL,
            new_confidence REAL,
            reason TEXT,
            timestamp TEXT
        )
        """
        )

        self.conn.commit()

    # =========================
    # 🧠 BELIEF SYSTEM
    # =========================

    def create_belief(self, statement, agent, confidence=0.6):
        cursor = self.conn.cursor()

        try:
            cursor.execute(
                """
            INSERT INTO beliefs
            (statement, confidence, created_by_agent, status, created_at, last_updated)
            VALUES (?, ?, ?, 'active', ?, ?)
            """,
                (
                    statement,
                    confidence,
                    agent,
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                ),
            )

            self.conn.commit()
            print(f"🧠 NEW BELIEF CREATED: {statement[:80]}")
            return cursor.lastrowid

        except sqlite3.IntegrityError:
            # belief already exists
            return self.get_belief_by_statement(statement)

    def get_belief_by_statement(self, statement):
        cursor = self.conn.cursor()

        cursor.execute("SELECT * FROM beliefs WHERE statement = ?", (statement,))
        result = cursor.fetchone()

        return dict(result) if result else None

    def get_all_beliefs(self, limit=50):
        cursor = self.conn.cursor()

        cursor.execute(
            """
        SELECT * FROM beliefs
        WHERE status != 'discarded'
        ORDER BY confidence DESC, last_updated DESC
        LIMIT ?
        """,
            (limit,),
        )

        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def add_evidence(self, belief_id, evidence, evidence_type="supporting"):
        cursor = self.conn.cursor()

        cursor.execute(
            """
        INSERT INTO belief_evidence
        (belief_id, type, evidence, timestamp)
        VALUES (?, ?, ?, ?)
        """,
            (
                belief_id,
                evidence_type,
                evidence,
                datetime.utcnow().isoformat(),
            ),
        )

        self.conn.commit()

    def update_belief_confidence(self, belief_id, delta, reason="interaction"):
        cursor = self.conn.cursor()

        cursor.execute(
            "SELECT confidence FROM beliefs WHERE belief_id = ?",
            (belief_id,),
        )
        row = cursor.fetchone()

        if not row:
            return

        old_conf = row["confidence"]
        new_conf = max(0.0, min(1.0, old_conf + delta))

        status = "active"
        if new_conf < 0.2:
            status = "discarded"
        elif new_conf < 0.4:
            status = "weakened"

        cursor.execute(
            """
        UPDATE beliefs
        SET confidence = ?, status = ?, last_updated = ?
        WHERE belief_id = ?
        """,
            (
                new_conf,
                status,
                datetime.utcnow().isoformat(),
                belief_id,
            ),
        )

        cursor.execute(
            """
        INSERT INTO belief_history
        (belief_id, change_type, old_confidence, new_confidence, reason, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                belief_id,
                "confidence_update",
                old_conf,
                new_conf,
                reason,
                datetime.utcnow().isoformat(),
            ),
        )

        self.conn.commit()

        print(f"🧠 BELIEF UPDATED: {old_conf:.2f} → {new_conf:.2f}")

    def get_belief_evidence(self, belief_id):
        cursor = self.conn.cursor()

        cursor.execute(
            """
        SELECT * FROM belief_evidence
        WHERE belief_id = ?
        """,
            (belief_id,),
        )

        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def decay_beliefs(self, decay_rate=0.01):
        cursor = self.conn.cursor()

        cursor.execute("SELECT belief_id, confidence FROM beliefs")

        for row in cursor.fetchall():
            new_conf = row["confidence"] - decay_rate

            cursor.execute(
                """
            UPDATE beliefs
            SET confidence = ?, last_updated = ?
            WHERE belief_id = ?
            """,
                (
                    max(new_conf, 0),
                    datetime.utcnow().isoformat(),
                    row["belief_id"],
                ),
            )

        self.conn.commit()
        print("🧠 BELIEF DECAY APPLIED")

    # =========================
    # EXISTING SYSTEM (UNCHANGED)
    # =========================

    def store_memory(
        self, content, summary=None, source="system", tier="ephemeral", importance=0
    ):
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) as c FROM memories")
        count = cursor.fetchone()["c"]

        if count >= MAX_MEMORY_ENTRIES:
            print("Memory limit reached. Skipping new memory.")
            return False

        cursor.execute(
            """
        INSERT INTO memories
        (timestamp, content, summary, source, tier, importance)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
            (datetime.utcnow().isoformat(), content, summary, source, tier, importance),
        )

        self.conn.commit()

        print(f"Memory stored in tier: {tier} | importance: {importance}")

        return True

    def get_recent_memories(self, limit=25):
        cursor = self.conn.cursor()

        cursor.execute("SELECT * FROM memories ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()

        return [dict(r) for r in rows]

    def get_recent_memory_entries(self, limit=25):
        return self.get_recent_memories(limit)

    def get_high_value_memories(self, limit=5):
        cursor = self.conn.cursor()

        cursor.execute(
            """
        SELECT * FROM memories
        WHERE tier = 'high_value'
        ORDER BY importance DESC, id DESC
        LIMIT ?
        """,
            (limit,),
        )

        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def count_by_tier(self):
        cursor = self.conn.cursor()

        cursor.execute(
            """
        SELECT tier, COUNT(*) as c
        FROM memories
        GROUP BY tier
        """
        )

        rows = cursor.fetchall()
        return {r["tier"]: r["c"] for r in rows}
