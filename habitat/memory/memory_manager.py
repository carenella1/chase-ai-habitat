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

        self.conn.commit()

    # =========================
    # EXISTING SYSTEM (UNCHANGED)
    # =========================
    # Belief tracking used to live here (beliefs / belief_evidence /
    # belief_history). It's been unified into NexMemory.beliefs
    # (structured_memory.py), which has richer evidence/contradiction
    # tracking. The old tables and their ~2,500 rows of history remain in
    # data/memory.db untouched -- they were migrated, not deleted.

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
