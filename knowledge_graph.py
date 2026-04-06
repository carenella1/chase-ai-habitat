"""
knowledge_graph.py  —  Phase 5: Nex's Knowledge Becomes a Living Map

WHAT THIS DOES:
  Turns Nex's flat knowledge into a temporal graph of entities
  and relationships — inspired by Graphiti (open source, 2026).

  Current state: Nex knows things as isolated facts in a list.
  After this: Nex knows HOW things connect, WHEN connections
  formed, and can REASON across chains of relationships.

  Think of it as the difference between a list of facts and
  a genuine world model.

EXAMPLE — What Nex can do with this:
  "What connects AutoAgent to DeepSeek?"
  → AutoAgent [uses] → LLM evaluation
  → LLM evaluation [requires] → Reasoning models
  → Reasoning models [includes] → DeepSeek R1
  → DeepSeek R1 [is_version_of] → DeepSeek
  = Path found: AutoAgent → DeepSeek (via reasoning capability)

  This is multi-hop reasoning. This is how real intelligence
  navigates complex knowledge.

TEMPORAL AWARENESS:
  Every relationship has a validity window.
  "DeepSeek R1 is the best open-source reasoning model"
  → valid_from: Jan 2025, valid_until: Oct 2025 (superseded by R1-0528)
  Nex knows things CHANGE and tracks the history.

DESIGN:
  - Pure SQLite (no external graph DB needed)
  - Compatible with your existing memory.db
  - Semantic search if sentence-transformers available
  - Exports to JSON for visualization in the UI
"""

import json
import os
import sqlite3
import threading
import time
from datetime import datetime
from typing import Optional

GRAPH_DB = "data/knowledge_graph.db"

# Relationship types Nex uses
RELATIONSHIP_TYPES = {
    # Conceptual
    "is_a",  # X is a type of Y
    "part_of",  # X is part of Y
    "related_to",  # X is generally related to Y
    "leads_to",  # X causes or enables Y
    "contradicts",  # X and Y conflict
    "supports",  # X provides evidence for Y
    # Temporal
    "superseded_by",  # X was replaced by Y
    "evolved_from",  # X developed from Y
    # Capability
    "enables",  # X makes Y possible
    "requires",  # X depends on Y
    "uses",  # X employs Y
    "improves",  # X makes Y better
    # Identity
    "created_by",  # X was made by Y
    "is_version_of",  # X is a version of Y
    "applied_to",  # X is used for Y
}


# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────


class GraphDB:
    def __init__(self, db_path: str = GRAPH_DB):
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

        # Nodes: any concept, entity, person, technology
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            name_lower TEXT UNIQUE NOT NULL,
            node_type TEXT DEFAULT 'concept',  -- concept/person/technology/place/event
            description TEXT,
            first_seen TEXT,
            last_updated TEXT,
            mention_count INTEGER DEFAULT 1,
            importance REAL DEFAULT 0.5,
            embedding BLOB
        )"""
        )

        # Edges: temporal relationships between nodes
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            relationship TEXT NOT NULL,
            weight REAL DEFAULT 0.5,     -- strength of relationship
            valid_from TEXT NOT NULL,
            valid_until TEXT,            -- NULL = still current
            evidence TEXT,               -- what supports this relationship
            confidence REAL DEFAULT 0.7,
            created_by TEXT DEFAULT 'nexarion',
            FOREIGN KEY (source_id) REFERENCES nodes(id),
            FOREIGN KEY (target_id) REFERENCES nodes(id)
        )"""
        )

        # Edge history: when relationships change
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS edge_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            edge_id INTEGER,
            old_weight REAL,
            new_weight REAL,
            reason TEXT,
            changed_at TEXT,
            FOREIGN KEY (edge_id) REFERENCES edges(id)
        )"""
        )

        conn.commit()


# ─────────────────────────────────────────────
# NODE MANAGER
# ─────────────────────────────────────────────


class NodeManager:
    def __init__(self, db: GraphDB):
        self.db = db

    def upsert(
        self, name: str, node_type: str = "concept", description: str = None
    ) -> int:
        """Add or update a node. Returns node ID."""
        conn = self.db._conn()
        name_lower = name.strip().lower()
        now = datetime.utcnow().isoformat()

        existing = conn.execute(
            "SELECT id, mention_count FROM nodes WHERE name_lower = ?", (name_lower,)
        ).fetchone()

        if existing:
            conn.execute(
                """UPDATE nodes SET mention_count = mention_count + 1,
                   last_updated = ?, description = COALESCE(?, description)
                   WHERE id = ?""",
                (now, description, existing["id"]),
            )
            conn.commit()
            return existing["id"]

        cursor = conn.execute(
            """INSERT INTO nodes
               (name, name_lower, node_type, description, first_seen, last_updated)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name.strip(), name_lower, node_type, description, now, now),
        )
        conn.commit()
        return cursor.lastrowid

    def get(self, name: str) -> Optional[dict]:
        conn = self.db._conn()
        row = conn.execute(
            "SELECT * FROM nodes WHERE name_lower = ?", (name.strip().lower(),)
        ).fetchone()
        return dict(row) if row else None

    def get_by_id(self, node_id: int) -> Optional[dict]:
        conn = self.db._conn()
        row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        return dict(row) if row else None

    def get_most_important(self, limit: int = 20) -> list:
        conn = self.db._conn()
        rows = conn.execute(
            """SELECT * FROM nodes ORDER BY mention_count DESC, importance DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str, limit: int = 10) -> list:
        conn = self.db._conn()
        q = f"%{query.lower()}%"
        rows = conn.execute(
            """SELECT * FROM nodes WHERE name_lower LIKE ? OR description LIKE ?
               ORDER BY mention_count DESC LIMIT ?""",
            (q, q, limit),
        ).fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# EDGE MANAGER
# ─────────────────────────────────────────────


class EdgeManager:
    def __init__(self, db: GraphDB):
        self.db = db

    def connect(
        self,
        source_name: str,
        relationship: str,
        target_name: str,
        weight: float = 0.5,
        evidence: str = None,
        confidence: float = 0.7,
        created_by: str = "nexarion",
    ) -> int:
        """
        Create a relationship between two nodes.
        Automatically creates nodes if they don't exist.
        Returns edge ID.
        """
        conn = self.db._conn()
        node_mgr = NodeManager(self.db)

        source_id = node_mgr.upsert(source_name)
        target_id = node_mgr.upsert(target_name)
        now = datetime.utcnow().isoformat()

        # Check if this edge already exists (same source, relationship, target)
        existing = conn.execute(
            """SELECT id, weight FROM edges
               WHERE source_id = ? AND relationship = ? AND target_id = ?
               AND valid_until IS NULL""",
            (source_id, relationship, target_id),
        ).fetchone()

        if existing:
            # Strengthen existing relationship
            new_weight = min(1.0, existing["weight"] + 0.05)
            conn.execute(
                "UPDATE edges SET weight = ?, confidence = ? WHERE id = ?",
                (new_weight, min(1.0, confidence + 0.05), existing["id"]),
            )
            conn.execute(
                """INSERT INTO edge_history (edge_id, old_weight, new_weight, reason, changed_at)
                   VALUES (?, ?, ?, 'reinforced', ?)""",
                (existing["id"], existing["weight"], new_weight, now),
            )
            conn.commit()
            return existing["id"]

        cursor = conn.execute(
            """INSERT INTO edges
               (source_id, target_id, relationship, weight, valid_from,
                evidence, confidence, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_id,
                target_id,
                relationship,
                weight,
                now,
                evidence,
                confidence,
                created_by,
            ),
        )
        conn.commit()
        return cursor.lastrowid

    def deprecate(self, edge_id: int, reason: str = "superseded"):
        """Mark a relationship as no longer current."""
        conn = self.db._conn()
        conn.execute(
            "UPDATE edges SET valid_until = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), edge_id),
        )
        conn.commit()

    def get_connections(
        self, node_name: str, current_only: bool = True, direction: str = "both"
    ) -> list:
        """
        Get all relationships for a node.
        direction: 'outgoing' | 'incoming' | 'both'
        """
        conn = self.db._conn()
        node_mgr = NodeManager(self.db)
        node = node_mgr.get(node_name)
        if not node:
            return []

        node_id = node["id"]
        where_validity = "AND e.valid_until IS NULL" if current_only else ""

        if direction in ("outgoing", "both"):
            out_rows = conn.execute(
                f"""SELECT e.*, n.name as target_name, n.node_type as target_type
                    FROM edges e JOIN nodes n ON e.target_id = n.id
                    WHERE e.source_id = ? {where_validity}
                    ORDER BY e.weight DESC""",
                (node_id,),
            ).fetchall()
        else:
            out_rows = []

        if direction in ("incoming", "both"):
            in_rows = conn.execute(
                f"""SELECT e.*, n.name as source_name, n.node_type as source_type
                    FROM edges e JOIN nodes n ON e.source_id = n.id
                    WHERE e.target_id = ? {where_validity}
                    ORDER BY e.weight DESC""",
                (node_id,),
            ).fetchall()
        else:
            in_rows = []

        results = []
        for r in out_rows:
            d = dict(r)
            d["direction"] = "outgoing"
            results.append(d)
        for r in in_rows:
            d = dict(r)
            d["direction"] = "incoming"
            results.append(d)
        return results


# ─────────────────────────────────────────────
# PATH FINDER — multi-hop reasoning
# ─────────────────────────────────────────────


class PathFinder:
    """
    Finds connection paths between any two concepts.
    This enables multi-hop reasoning: "How does X relate to Y?"
    Uses BFS to find shortest path through the knowledge graph.
    """

    def __init__(self, db: GraphDB):
        self.db = db

    def find_path(
        self, start_name: str, end_name: str, max_hops: int = 4
    ) -> Optional[list]:
        """
        Find a path between two nodes.
        Returns list of (node, relationship, node) tuples, or None.
        """
        conn = self.db._conn()
        node_mgr = NodeManager(self.db)

        start = node_mgr.get(start_name)
        end = node_mgr.get(end_name)

        if not start or not end:
            return None

        if start["id"] == end["id"]:
            return [{"node": start_name, "relationship": None, "next": None}]

        # BFS
        visited = {start["id"]}
        queue = [[(start["id"], start_name, None)]]

        for _ in range(max_hops):
            next_queue = []
            for path in queue:
                current_id = path[-1][0]

                # Get all neighbors
                rows = conn.execute(
                    """SELECT e.relationship, e.weight,
                       n.id as neighbor_id, n.name as neighbor_name
                       FROM edges e JOIN nodes n ON (
                           CASE WHEN e.source_id = ? THEN e.target_id
                                ELSE e.source_id END = n.id
                       )
                       WHERE (e.source_id = ? OR e.target_id = ?)
                       AND e.valid_until IS NULL
                       ORDER BY e.weight DESC LIMIT 10""",
                    (current_id, current_id, current_id),
                ).fetchall()

                for row in rows:
                    if row["neighbor_id"] in visited:
                        continue
                    visited.add(row["neighbor_id"])

                    new_path = path + [
                        (row["neighbor_id"], row["neighbor_name"], row["relationship"])
                    ]

                    if row["neighbor_id"] == end["id"]:
                        # Found! Format result
                        result = []
                        for i, (nid, nname, rel) in enumerate(new_path):
                            result.append(
                                {
                                    "node": nname,
                                    "relationship": rel,
                                    "step": i,
                                }
                            )
                        return result

                    next_queue.append(new_path)

            queue = next_queue
            if not queue:
                break

        return None  # No path found within max_hops

    def format_path(self, path: list) -> str:
        """Format a path as human-readable text."""
        if not path:
            return "No connection found."
        parts = []
        for i, step in enumerate(path):
            if i == 0:
                parts.append(step["node"])
            else:
                rel = step["relationship"] or "→"
                parts.append(f"--[{rel}]--> {step['node']}")
        return " ".join(parts)


# ─────────────────────────────────────────────
# GRAPH EXTRACTOR — builds graph from text
# ─────────────────────────────────────────────


class GraphExtractor:
    """
    Automatically extracts entities and relationships from
    Nex's research text and builds the knowledge graph.
    Uses pattern matching — no additional LLM calls needed.
    """

    # Simple relationship patterns
    PATTERNS = [
        # "X is a field of study in Y" / "X is a Y"
        (
            r"([A-Z][a-zA-Z\s]{2,30}) is (?:a field of study in|a branch of|a subfield of|part of|a type of|an? ) ([a-zA-Z\s]{3,30})",
            "is_a",
        ),
        # "X is concerned with Y" / "X focuses on Y"
        (
            r"([A-Z][a-zA-Z\s]{2,30}) (?:is concerned with|focuses on|studies|examines|addresses) ([a-zA-Z\s]{3,40})",
            "related_to",
        ),
        # "X enables Y" / "X allows Y"
        (
            r"([A-Z][a-zA-Z\s]{2,30}) (?:enables?|allows?|supports?|improves?) ([a-zA-Z\s]{3,30})",
            "enables",
        ),
        # "X requires Y" / "X depends on Y"
        (
            r"([A-Z][a-zA-Z\s]{2,30}) (?:requires?|depends? on|relies? on|uses?) ([a-zA-Z\s]{3,30})",
            "requires",
        ),
        # "X leads to Y" / "X results in Y"
        (
            r"([A-Z][a-zA-Z\s]{2,30}) (?:leads? to|results? in|produces?|creates?) ([a-zA-Z\s]{3,30})",
            "leads_to",
        ),
        # "X has applications in Y"
        (
            r"([A-Z][a-zA-Z\s]{2,30}) has applications? in ([a-zA-Z\s]{3,30})",
            "applied_to",
        ),
        # "X is used in Y" / "X is applied to Y"
        (
            r"([A-Z][a-zA-Z\s]{2,30}) is (?:used in|applied (?:to|in)|employed in) ([a-zA-Z\s]{3,30})",
            "applied_to",
        ),
    ]

    def __init__(self, db: GraphDB):
        self.db = db
        import re

        self.re = re
        self._compiled = [
            (self.re.compile(p, self.re.IGNORECASE), rel) for p, rel in self.PATTERNS
        ]

    def extract_from_text(
        self, text: str, source: str = "research", min_entity_length: int = 3
    ) -> list:
        """
        Extract entity-relationship-entity triples from text.
        Returns list of (source, relationship, target) tuples found.
        """
        edge_mgr = EdgeManager(self.db)
        found = []

        for pattern, relationship in self._compiled:
            matches = pattern.findall(text)
            for match in matches:
                if isinstance(match, tuple) and len(match) == 2:
                    src, tgt = match[0].strip(), match[1].strip()
                    # Filter noise
                    if (
                        len(src) >= min_entity_length
                        and len(tgt) >= min_entity_length
                        and len(src) <= 60
                        and len(tgt) <= 60
                    ):

                        edge_mgr.connect(
                            src,
                            relationship,
                            tgt,
                            weight=0.5,
                            evidence=text[:200],
                            created_by=source,
                        )
                        found.append((src, relationship, tgt))

        return found


# ─────────────────────────────────────────────
# UNIFIED INTERFACE
# ─────────────────────────────────────────────


class NexKnowledgeGraph:
    """The main interface for Nex's knowledge graph."""

    def __init__(self):
        self.db = GraphDB()
        self.nodes = NodeManager(self.db)
        self.edges = EdgeManager(self.db)
        self.pathfinder = PathFinder(self.db)
        self.extractor = GraphExtractor(self.db)
        print("🕸️ KNOWLEDGE GRAPH: Online")

    def learn_from_text(self, text: str, source: str = "research") -> int:
        """Extract knowledge from text and add to graph. Returns # edges added."""
        triples = self.extractor.extract_from_text(text, source)
        return len(triples)

    def connect(
        self,
        entity_a: str,
        relationship: str,
        entity_b: str,
        evidence: str = None,
        confidence: float = 0.7,
    ) -> int:
        """Manually add a relationship."""
        return self.edges.connect(
            entity_a, relationship, entity_b, evidence=evidence, confidence=confidence
        )

    def how_are_related(self, entity_a: str, entity_b: str) -> str:
        """Find and describe the connection between two concepts."""
        path = self.pathfinder.find_path(entity_a, entity_b)
        if path:
            return self.pathfinder.format_path(path)
        return f"No direct connection found between '{entity_a}' and '{entity_b}' within 4 hops."

    def what_connects_to(self, entity: str) -> list:
        """Get everything connected to an entity."""
        return self.edges.get_connections(entity, current_only=True)

    def get_graph_context_for_prompt(self, topic: str) -> str:
        """
        Returns connected knowledge about a topic for prompt injection.
        Adds relational context Nex wouldn't otherwise have.
        """
        connections = self.what_connects_to(topic)
        if not connections:
            return ""

        lines = [f"Knowledge graph — connections for '{topic}':"]
        for c in connections[:8]:
            if c.get("direction") == "outgoing":
                lines.append(
                    f"  {topic} --[{c['relationship']}]--> {c.get('target_name', '?')}"
                )
            else:
                lines.append(
                    f"  {c.get('source_name', '?')} --[{c['relationship']}]--> {topic}"
                )

        return "\n".join(lines)

    def export_for_visualization(self, limit: int = 100) -> dict:
        """Export graph as nodes+edges JSON for UI visualization."""
        conn = self.db._conn()
        nodes = conn.execute(
            "SELECT id, name, node_type, mention_count FROM nodes ORDER BY mention_count DESC LIMIT ?",
            (limit,),
        ).fetchall()
        edges = conn.execute(
            """SELECT e.id, n1.name as source, n2.name as target, e.relationship, e.weight
               FROM edges e
               JOIN nodes n1 ON e.source_id = n1.id
               JOIN nodes n2 ON e.target_id = n2.id
               WHERE e.valid_until IS NULL LIMIT ?""",
            (limit * 3,),
        ).fetchall()

        return {
            "nodes": [dict(n) for n in nodes],
            "edges": [dict(e) for e in edges],
        }

    def get_stats(self) -> dict:
        conn = self.db._conn()
        return {
            "total_nodes": conn.execute("SELECT COUNT(*) as c FROM nodes").fetchone()[
                "c"
            ],
            "total_edges": conn.execute(
                "SELECT COUNT(*) as c FROM edges WHERE valid_until IS NULL"
            ).fetchone()["c"],
            "top_entities": [
                {"name": r["name"], "mentions": r["mention_count"]}
                for r in conn.execute(
                    "SELECT name, mention_count FROM nodes ORDER BY mention_count DESC LIMIT 5"
                ).fetchall()
            ],
        }


# ─────────────────────────────────────────────
# HOW TO WIRE INTO run_ui.py
# ─────────────────────────────────────────────
#
# 1. Copy this file next to run_ui.py
#
# 2. At the top of run_ui.py:
#       from knowledge_graph import NexKnowledgeGraph
#       knowledge_graph = NexKnowledgeGraph()
#
# 3. In the cognition loop, after research:
#       knowledge_graph.learn_from_text(research_result, source="Researcher")
#
# 4. In _build_nexarion_prompt(), add:
#       graph_context = knowledge_graph.get_graph_context_for_prompt(topics_str)
#       # inject graph_context into prompt
#
# 5. Add UI endpoints:
#       @app.route("/api/graph/stats")
#       def api_graph_stats():
#           return jsonify(knowledge_graph.get_stats())
#
#       @app.route("/api/graph/visualize")
#       def api_graph_visualize():
#           return jsonify(knowledge_graph.export_for_visualization())
#
#       @app.route("/api/graph/path")
#       def api_graph_path():
#           a = request.args.get("from", "")
#           b = request.args.get("to", "")
#           return jsonify({"path": knowledge_graph.how_are_related(a, b)})
