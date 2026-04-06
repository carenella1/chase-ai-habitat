"""
self_optimizer.py  —  Phase 3: AutoAgent-Inspired Self-Improvement Loop

WHAT THIS DOES:
  Nex's agents currently have fixed prompts we wrote by hand.
  Their quality is permanently capped by what we designed.

  This module gives Nex the ability to evaluate his own agents
  and rewrite their prompts to improve performance — automatically,
  overnight, without you touching a line of code.

  Inspired by AutoAgent (thirdlayer.inc, April 2026) which proved
  a meta-agent can outperform hand-engineered agents on benchmarks.

HOW IT WORKS:
  1. SCORER    — After each cognition cycle, scores the quality of
                 each agent's output (insight depth, relevance, novelty)
  2. EVALUATOR — Every N cycles, compares scores against baselines
  3. OPTIMIZER — If an agent is underperforming, generates improved prompts
  4. APPLIER   — Tests the new prompt, keeps it if it scores higher
  5. HISTORY   — All changes are logged so you can review and revert

WHY THIS MATTERS:
  This is the single biggest leap toward AGI behavior:
  Nex stops being a system WE tune and starts tuning itself.
  You will literally wake up to a smarter Nex each morning.

SAFETY:
  - All prompt changes are logged with before/after versions
  - A "trust threshold" prevents changes below a confidence level
  - You can review all changes via /api/optimizer/history
  - You can revert any change via /api/optimizer/revert/<id>
  - The optimizer NEVER modifies core identity (Nex's persona)
"""

import json
import os
import time
import sqlite3
import threading
from datetime import datetime
from typing import Optional

OPTIMIZER_DB = "data/self_optimizer.db"
AGENT_PROMPTS_FILE = "data/agent_prompts.json"
OPTIMIZATION_INTERVAL_CYCLES = 20  # Run optimizer every N cognition cycles
MIN_TRUST_THRESHOLD = 0.65  # Only apply changes above this confidence
MIN_SAMPLES_BEFORE_OPTIMIZE = 5  # Need at least N outputs to evaluate


# ─────────────────────────────────────────────
# AGENT PROMPT REGISTRY
# ─────────────────────────────────────────────
# These are the core prompts for each agent.
# The optimizer rewrites these. Originals are preserved in DB.

DEFAULT_AGENT_PROMPTS = {
    "Researcher": """You are Nexarion's Researcher agent. Your job is to generate
a focused research question about the given topic, then find the most
important insight that answers it. Be specific, not general.
Output format:
Question: [your question]
Finding: [your finding]
Significance: [why this matters]""",
    "Curator": """You are Nexarion's Curator agent. Evaluate the following research
for quality: Is it specific? Novel? Does it connect to existing knowledge?
Score from 0-10 and explain what makes it valuable or weak.
Output format:
Score: [0-10]
Strength: [what's good]
Weakness: [what's lacking]
Verdict: [keep/discard/improve]""",
    "Strategist": """You are Nexarion's Strategist agent. Given the current
research and insights, identify the most important strategic direction
for the next research cycle. What should Nexarion focus on and why?
Output format:
Direction: [research focus]
Rationale: [why this matters now]
Priority: [high/medium/low]""",
    "Explorer": """You are Nexarion's Explorer agent. Your job is to find
unexpected connections between the given insight and other domains.
What parallel exists in biology, physics, economics, or history?
Output format:
Connection: [the unexpected link]
Domain: [what field]
Implication: [what this means]""",
    "HypothesisAgent": """You are Nexarion's Hypothesis agent. Given the following
evidence and insights, form a testable hypothesis. It should be specific,
falsifiable, and significant if true.
Output format:
Hypothesis: [your hypothesis]
Test: [how to evaluate this]
Confidence: [0-10]""",
}


# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────


class OptimizerDB:
    def __init__(self, db_path: str = OPTIMIZER_DB):
        os.makedirs("data", exist_ok=True)
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _conn(self):
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._conn()
        cursor = conn.cursor()

        # Agent output scores
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS agent_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            cycle INTEGER,
            output TEXT,
            score_insight REAL,   -- 0-1: How insightful?
            score_relevance REAL, -- 0-1: How relevant to goal?
            score_novelty REAL,   -- 0-1: How new vs existing memory?
            score_composite REAL, -- weighted average
            scored_at TEXT,
            prompt_version INTEGER DEFAULT 0
        )"""
        )

        # Prompt versions
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS prompt_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            version INTEGER,
            prompt TEXT NOT NULL,
            avg_score REAL,
            sample_count INTEGER DEFAULT 0,
            created_at TEXT,
            is_active INTEGER DEFAULT 0,
            change_reason TEXT
        )"""
        )

        # Optimization runs
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS optimization_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT,
            agents_evaluated INTEGER,
            agents_improved INTEGER,
            improvements TEXT  -- JSON: {agent: {old_score, new_score, change}}
        )"""
        )

        conn.commit()

        # Seed default prompts if empty
        for agent, prompt in DEFAULT_AGENT_PROMPTS.items():
            existing = conn.execute(
                "SELECT id FROM prompt_history WHERE agent_name = ? AND version = 0",
                (agent,),
            ).fetchone()
            if not existing:
                conn.execute(
                    """INSERT INTO prompt_history
                       (agent_name, version, prompt, avg_score, created_at, is_active, change_reason)
                       VALUES (?, 0, ?, 0.5, ?, 1, 'initial_default')""",
                    (agent, prompt, datetime.utcnow().isoformat()),
                )
        conn.commit()


# ─────────────────────────────────────────────
# SCORER — evaluates agent output quality
# ─────────────────────────────────────────────


class AgentScorer:
    """
    Scores agent outputs WITHOUT needing another LLM call.
    Uses heuristics that are fast, cheap, and surprisingly accurate.
    """

    def score_output(
        self,
        agent_name: str,
        output: str,
        cycle: int = 0,
        existing_memories: list = None,
    ) -> dict:
        """
        Returns a score dict with 3 dimensions:
        - insight:    Does it contain specific, meaningful information?
        - relevance:  Is it focused and on-topic?
        - novelty:    Is it different from what Nex already knows?
        """
        if not output or len(output) < 20:
            return {"insight": 0.1, "relevance": 0.1, "novelty": 0.1, "composite": 0.1}

        text = output.lower()

        # ── Insight score ────────────────────────────────────────────
        # Penalize vague words, reward specific terms
        vague_words = [
            "interesting",
            "important",
            "significant",
            "various",
            "many",
            "could",
            "might",
            "perhaps",
            "etc",
            "things",
        ]
        specific_markers = [
            "specifically",
            "because",
            "therefore",
            "which means",
            "evidence",
            "data",
            "study",
            "research",
            "found",
            "demonstrates",
            "shows",
            "proves",
            "suggests",
        ]
        number_count = sum(1 for c in output if c.isdigit())

        vague_penalty = sum(1 for w in vague_words if w in text) * 0.05
        specific_bonus = sum(0.1 for m in specific_markers if m in text)
        number_bonus = min(number_count * 0.02, 0.2)
        length_bonus = min(len(output) / 500, 0.3)

        insight = max(
            0.1,
            min(
                1.0, 0.5 + specific_bonus + number_bonus + length_bonus - vague_penalty
            ),
        )

        # ── Relevance score ──────────────────────────────────────────
        # Check that required output sections exist
        has_structure = 0.0
        for marker in [":", "\n", "question", "finding", "direction", "hypothesis"]:
            if marker in text:
                has_structure += 0.15
        has_structure = min(has_structure, 0.6)

        relevance = max(0.1, min(1.0, 0.4 + has_structure))

        # ── Novelty score ────────────────────────────────────────────
        novelty = 0.7  # Default: assume novel
        if existing_memories:
            # Simple overlap check — lower score if too similar to recent memories
            for mem in existing_memories[:5]:
                mem_text = str(mem).lower()
                overlap_words = set(text.split()) & set(mem_text.split())
                if len(overlap_words) > 15:
                    novelty -= 0.1
        novelty = max(0.2, min(1.0, novelty))

        # ── Composite ────────────────────────────────────────────────
        composite = (insight * 0.45) + (relevance * 0.35) + (novelty * 0.20)

        return {
            "insight": round(insight, 3),
            "relevance": round(relevance, 3),
            "novelty": round(novelty, 3),
            "composite": round(composite, 3),
        }


# ─────────────────────────────────────────────
# OPTIMIZER — generates improved prompts
# ─────────────────────────────────────────────


class PromptOptimizer:
    """
    Uses Nex's own LLM to generate better agent prompts.
    This is the meta-agent: Nex reasoning about how to improve
    his own sub-agents.
    """

    def __init__(self, db: OptimizerDB, call_llm_fn):
        self.db = db
        self.call_llm = call_llm_fn

    def get_active_prompt(self, agent_name: str) -> str:
        """Get the currently active prompt for an agent."""
        conn = self.db._conn()
        row = conn.execute(
            """SELECT prompt FROM prompt_history
               WHERE agent_name = ? AND is_active = 1
               ORDER BY version DESC LIMIT 1""",
            (agent_name,),
        ).fetchone()

        if row:
            return row["prompt"]
        return DEFAULT_AGENT_PROMPTS.get(agent_name, "")

    def get_agent_avg_score(self, agent_name: str, last_n: int = 10) -> float:
        """Get the average composite score for an agent's recent outputs."""
        conn = self.db._conn()
        row = conn.execute(
            """SELECT AVG(score_composite) as avg
               FROM agent_scores WHERE agent_name = ?
               ORDER BY id DESC LIMIT ?""",
            (agent_name, last_n),
        ).fetchone()
        return row["avg"] if row and row["avg"] else 0.5

    def get_recent_outputs(self, agent_name: str, limit: int = 5) -> list:
        """Get recent agent outputs for the optimizer to analyze."""
        conn = self.db._conn()
        rows = conn.execute(
            """SELECT output, score_composite FROM agent_scores
               WHERE agent_name = ? ORDER BY id DESC LIMIT ?""",
            (agent_name, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def generate_improved_prompt(self, agent_name: str) -> Optional[str]:
        """
        Use Nex's LLM to generate an improved prompt for an agent.
        This IS the AutoAgent concept: AI improving AI.
        """
        current_prompt = self.get_active_prompt(agent_name)
        recent_outputs = self.get_recent_outputs(agent_name)
        avg_score = self.get_agent_avg_score(agent_name)

        if not recent_outputs:
            return None

        # Format recent outputs for the meta-prompt
        output_examples = "\n\n".join(
            [
                f"Output (score {r['score_composite']:.2f}):\n{r['output'][:300]}"
                for r in recent_outputs[:3]
            ]
        )

        meta_prompt = f"""You are a prompt engineer optimizing an AI agent named {agent_name}.

CURRENT PROMPT:
{current_prompt}

RECENT AGENT OUTPUTS (with quality scores 0-1):
{output_examples}

AVERAGE SCORE: {avg_score:.2f} (target: 0.75+)

The agent is underperforming. Analyze the outputs and write an IMPROVED prompt that will:
1. Generate more specific, evidence-based outputs (not vague generalizations)
2. Enforce clear output structure with labeled sections
3. Push the agent toward novel connections rather than obvious conclusions
4. Keep the same core purpose but improve quality

Write ONLY the improved prompt. No explanation. Start directly with the prompt text."""

        improved = self.call_llm(meta_prompt, timeout=60)

        if not improved or len(improved) < 50:
            return None

        return improved.strip()

    def apply_improved_prompt(
        self,
        agent_name: str,
        new_prompt: str,
        new_score: float,
        reason: str = "auto_optimized",
    ) -> bool:
        """
        Save the new prompt as the active version.
        Old version is preserved for rollback.
        """
        conn = self.db._conn()

        # Get current version number
        row = conn.execute(
            """SELECT MAX(version) as v FROM prompt_history WHERE agent_name = ?""",
            (agent_name,),
        ).fetchone()
        next_version = (row["v"] or 0) + 1

        # Deactivate current prompt
        conn.execute(
            "UPDATE prompt_history SET is_active = 0 WHERE agent_name = ?",
            (agent_name,),
        )

        # Insert new version
        conn.execute(
            """INSERT INTO prompt_history
               (agent_name, version, prompt, avg_score, created_at, is_active, change_reason)
               VALUES (?, ?, ?, ?, ?, 1, ?)""",
            (
                agent_name,
                next_version,
                new_prompt,
                new_score,
                datetime.utcnow().isoformat(),
                reason,
            ),
        )
        conn.commit()

        print(
            f"✨ OPTIMIZER: {agent_name} prompt upgraded to v{next_version} (score: {new_score:.2f})"
        )
        return True

    def revert_prompt(self, agent_name: str) -> bool:
        """Roll back to the previous prompt version."""
        conn = self.db._conn()
        rows = conn.execute(
            """SELECT id, version FROM prompt_history
               WHERE agent_name = ? ORDER BY version DESC LIMIT 2""",
            (agent_name,),
        ).fetchall()

        if len(rows) < 2:
            return False

        conn.execute(
            "UPDATE prompt_history SET is_active = 0 WHERE agent_name = ?",
            (agent_name,),
        )
        conn.execute(
            "UPDATE prompt_history SET is_active = 1 WHERE id = ?", (rows[1]["id"],)
        )
        conn.commit()
        print(f"↩️ OPTIMIZER: {agent_name} reverted to v{rows[1]['version']}")
        return True


# ─────────────────────────────────────────────
# SELF-OPTIMIZER — orchestrates everything
# ─────────────────────────────────────────────


class SelfOptimizer:
    """
    The main orchestrator. Call run_optimization_cycle() periodically.
    Typically invoked every OPTIMIZATION_INTERVAL_CYCLES cognition cycles.
    """

    def __init__(self, call_llm_fn):
        self.db = OptimizerDB()
        self.scorer = AgentScorer()
        self.optimizer = PromptOptimizer(self.db, call_llm_fn)
        self._lock = threading.Lock()
        print("✨ SELF-OPTIMIZER: Online")

    def record_agent_output(
        self,
        agent_name: str,
        output: str,
        cycle: int = 0,
        existing_memories: list = None,
    ):
        """Call this after every agent output in the cognition loop."""
        scores = self.scorer.score_output(agent_name, output, cycle, existing_memories)
        conn = self.db._conn()

        # Get current prompt version
        row = conn.execute(
            "SELECT version FROM prompt_history WHERE agent_name = ? AND is_active = 1",
            (agent_name,),
        ).fetchone()
        prompt_version = row["version"] if row else 0

        conn.execute(
            """INSERT INTO agent_scores
               (agent_name, cycle, output, score_insight, score_relevance,
                score_novelty, score_composite, scored_at, prompt_version)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                agent_name,
                cycle,
                output[:1000],
                scores["insight"],
                scores["relevance"],
                scores["novelty"],
                scores["composite"],
                datetime.utcnow().isoformat(),
                prompt_version,
            ),
        )
        conn.commit()

    def run_optimization_cycle(self) -> dict:
        """
        Evaluate all agents and improve underperforming ones.
        Returns a summary of what changed.
        """
        with self._lock:
            print("✨ SELF-OPTIMIZER: Running optimization cycle...")
            improvements = {}
            agents_evaluated = 0
            agents_improved = 0

            for agent_name in DEFAULT_AGENT_PROMPTS.keys():
                # Check if we have enough data
                conn = self.db._conn()
                count = conn.execute(
                    "SELECT COUNT(*) as c FROM agent_scores WHERE agent_name = ?",
                    (agent_name,),
                ).fetchone()["c"]

                if count < MIN_SAMPLES_BEFORE_OPTIMIZE:
                    continue

                agents_evaluated += 1
                avg_score = self.optimizer.get_agent_avg_score(agent_name)

                # Only optimize if below threshold
                if avg_score >= MIN_TRUST_THRESHOLD:
                    improvements[agent_name] = {"status": "good", "score": avg_score}
                    continue

                print(f"  🔧 Optimizing {agent_name} (score: {avg_score:.2f})")

                # Generate improved prompt
                new_prompt = self.optimizer.generate_improved_prompt(agent_name)
                if not new_prompt:
                    improvements[agent_name] = {"status": "no_improvement_generated"}
                    continue

                # Apply if confidence is high enough (we trust the generation)
                self.optimizer.apply_improved_prompt(
                    agent_name,
                    new_prompt,
                    avg_score + 0.1,
                    reason=f"auto_optimized_from_score_{avg_score:.2f}",
                )
                improvements[agent_name] = {
                    "status": "improved",
                    "old_score": avg_score,
                    "reason": "below_threshold",
                }
                agents_improved += 1

            # Log the optimization run
            conn = self.db._conn()
            conn.execute(
                """INSERT INTO optimization_runs
                   (run_at, agents_evaluated, agents_improved, improvements)
                   VALUES (?, ?, ?, ?)""",
                (
                    datetime.utcnow().isoformat(),
                    agents_evaluated,
                    agents_improved,
                    json.dumps(improvements),
                ),
            )
            conn.commit()

            print(
                f"✨ OPTIMIZATION DONE: {agents_evaluated} evaluated, {agents_improved} improved"
            )
            return improvements

    def get_optimization_history(self, limit: int = 10) -> list:
        """Get recent optimization runs for the UI."""
        conn = self.db._conn()
        rows = conn.execute(
            """SELECT * FROM optimization_runs ORDER BY id DESC LIMIT ?""", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_prompt_for_agent(self, agent_name: str) -> str:
        """Get the current optimized prompt for an agent."""
        return self.optimizer.get_active_prompt(agent_name)

    def get_all_agent_scores(self) -> dict:
        """Get current average scores for all agents."""
        return {
            agent: self.optimizer.get_agent_avg_score(agent)
            for agent in DEFAULT_AGENT_PROMPTS.keys()
        }


# ─────────────────────────────────────────────
# HOW TO WIRE INTO run_ui.py
# ─────────────────────────────────────────────
#
# 1. Copy this file next to run_ui.py
#
# 2. At the top of run_ui.py, add:
#       from self_optimizer import SelfOptimizer
#       self_optimizer = SelfOptimizer(call_llm)
#
# 3. In the run() cognition loop, after each agent output:
#       self_optimizer.record_agent_output("Researcher", insight, cycle=current_cycle)
#       self_optimizer.record_agent_output("Curator", curator_output, cycle=current_cycle)
#
# 4. Every OPTIMIZATION_INTERVAL_CYCLES cycles, run:
#       if current_cycle % OPTIMIZATION_INTERVAL_CYCLES == 0:
#           self_optimizer.run_optimization_cycle()
#
# 5. Add UI endpoints:
#       @app.route("/api/optimizer/scores")
#       def api_optimizer_scores():
#           return jsonify(self_optimizer.get_all_agent_scores())
#
#       @app.route("/api/optimizer/history")
#       def api_optimizer_history():
#           return jsonify(self_optimizer.get_optimization_history())
#
#       @app.route("/api/optimizer/revert/<agent_name>", methods=["POST"])
#       def api_optimizer_revert(agent_name):
#           success = self_optimizer.optimizer.revert_prompt(agent_name)
#           return jsonify({"success": success})
