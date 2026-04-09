"""
deep_research_trigger.py  —  High-Significance Deep Research Engine

WHAT THIS DOES:
  Monitors every cognition cycle's insight significance score.
  When a cycle produces a high-significance insight (score >= threshold),
  this module triggers the full 5-stage deep research pipeline on that topic
  in a background thread — so it never blocks the cognition loop.

  Results are stored in three places:
    1. data/deep_research_results.jsonl  — full reports on disk
    2. nex_trainer knowledge_cards.db    — compressed cards for prompt injection
    3. memory via structured_memory      — high-confidence facts and beliefs

  This means the NEXT time Nex thinks about that topic, it has genuine
  multi-source, multi-angle knowledge instead of a single Wikipedia paragraph.

SIGNIFICANCE THRESHOLDS:
  >= 7.0  → Full deep research (all 5 stages, web + wiki + news)
  >= 5.5  → Quick deep research (3 sub-questions, web only)
  < 5.5   → Standard single-source fetch (existing behavior, unchanged)

COOLDOWN:
  Deep research is expensive (~2-5 minutes). A per-topic cooldown of
  500 cycles prevents the same topic being deep-researched repeatedly.

STREAM PAGE INDICATOR:
  Sets a flag in data/system/deep_research_status.json that the Stream
  page polls to show a live "DEEP RESEARCH ACTIVE" indicator.

HOW TO WIRE INTO run_ui.py:
  1. Add near the top of run_ui.py (with other imports):
       from deep_research_trigger import DeepResearchTrigger
       deep_research_trigger = DeepResearchTrigger(call_llm, call_llm_deep)

  2. In the cognition loop, after significance is calculated and
     BEFORE the time.sleep(30) at the end of a successful cycle:
       deep_research_trigger.maybe_trigger(
           insight=insight,
           topic=search_term,
           significance=score,
           cycle=current_cycle,
           source=source,
       )

  That's it. Everything else is automatic.
"""

import json
import os
import threading
import time
from datetime import datetime
from typing import Callable, Optional


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

DEEP_THRESHOLD = 7.0  # Full 5-stage deep research
QUICK_THRESHOLD = 5.5  # Quick 3-question research

TOPIC_COOLDOWN_CYCLES = 500  # Don't deep-research same topic within N cycles
MAX_CONCURRENT = 1  # Only one deep research at a time (VRAM constraint)

RESULTS_FILE = "data/deep_research_results.jsonl"
STATUS_FILE = "data/system/deep_research_status.json"
COOLDOWN_FILE = "data/system/deep_research_cooldowns.json"


# ─────────────────────────────────────────────
# STATUS HELPERS  (read by Stream page UI)
# ─────────────────────────────────────────────


def _set_status(active: bool, topic: str = "", stage: str = "", cycle: int = 0):
    os.makedirs("data/system", exist_ok=True)
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(
                {
                    "active": active,
                    "topic": topic,
                    "stage": stage,
                    "cycle": cycle,
                    "timestamp": int(time.time()),
                },
                f,
            )
    except Exception:
        pass


def get_deep_research_status() -> dict:
    """Called by the /api/deep-research/status endpoint."""
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE) as f:
                data = json.load(f)
            # Auto-expire if older than 10 minutes (something crashed)
            if time.time() - data.get("timestamp", 0) > 600:
                data["active"] = False
            return data
    except Exception:
        pass
    return {"active": False, "topic": "", "stage": "", "cycle": 0}


# ─────────────────────────────────────────────
# COOLDOWN TRACKER
# ─────────────────────────────────────────────


def _load_cooldowns() -> dict:
    try:
        if os.path.exists(COOLDOWN_FILE):
            with open(COOLDOWN_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_cooldowns(cooldowns: dict):
    os.makedirs("data/system", exist_ok=True)
    try:
        with open(COOLDOWN_FILE, "w") as f:
            json.dump(cooldowns, f)
    except Exception:
        pass


def _is_on_cooldown(topic: str, current_cycle: int) -> bool:
    cooldowns = _load_cooldowns()
    last_cycle = cooldowns.get(topic, 0)
    return (current_cycle - last_cycle) < TOPIC_COOLDOWN_CYCLES


def _set_cooldown(topic: str, current_cycle: int):
    cooldowns = _load_cooldowns()
    cooldowns[topic] = current_cycle
    # Keep only last 200 topics
    if len(cooldowns) > 200:
        oldest = sorted(cooldowns.items(), key=lambda x: x[1])[:50]
        for k, _ in oldest:
            del cooldowns[k]
    _save_cooldowns(cooldowns)


# ─────────────────────────────────────────────
# RESULT STORAGE
# ─────────────────────────────────────────────


def _store_result(report: dict, cycle: int):
    """
    Store deep research result in three places:
    1. Full report on disk
    2. Compressed knowledge card in trainer DB
    3. High-confidence facts in structured memory
    """

    # 1. Full report to disk
    os.makedirs("data", exist_ok=True)
    try:
        entry = {
            "timestamp": int(time.time()),
            "cycle": cycle,
            "question": report.get("question", ""),
            "synthesis": report.get("synthesis", "")[:2000],
            "critique": report.get("critique", {}).get("critique", "")[:500],
            "sources": report.get("sources_consulted", 0),
            "elapsed": report.get("elapsed_seconds", 0),
            "depth": report.get("depth", "standard"),
        }
        with open(RESULTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"💾 DEEP RESEARCH: Full report saved to disk")
    except Exception as e:
        print(f"⚠️ Deep research disk save error: {e}")

    # 2. Knowledge card in trainer DB
    synthesis = report.get("synthesis", "")
    topic = report.get("question", "unknown")[:80]
    if synthesis and len(synthesis) > 100:
        try:
            import sqlite3

            db_path = "data/knowledge_cards.db"
            if os.path.exists(db_path):
                now = int(time.time())
                with sqlite3.connect(db_path) as conn:
                    conn.execute(
                        """INSERT INTO knowledge_cards
                           (topic, card_text, source_type, confidence, created_at, updated_at)
                           VALUES (?,?,?,?,?,?)""",
                        (topic, synthesis[:1500], "deep_research", 0.85, now, now),
                    )
                print(f"📚 DEEP RESEARCH: Knowledge card stored (confidence=0.85)")
        except Exception as e:
            print(f"⚠️ Deep research card store error: {e}")

    # 3. Key conclusions into structured memory
    critique = report.get("critique", {}).get("critique", "")
    if critique:
        conclusions = [
            line.strip()
            for line in critique.split("\n")
            if line.strip().startswith("✓")
        ]
        if conclusions:
            try:
                from structured_memory import NexMemory

                mem = NexMemory()
                for conclusion in conclusions[:3]:
                    clean = conclusion.lstrip("✓ ").strip()
                    if len(clean) > 20:
                        mem.learn(
                            clean,
                            source="deep_research",
                            topic=topic,
                            confidence=0.8,
                        )
                print(
                    f"🧠 DEEP RESEARCH: {len(conclusions[:3])} conclusions → structured memory"
                )
            except Exception as e:
                print(f"⚠️ Deep research memory store error: {e}")


# ─────────────────────────────────────────────
# MAIN TRIGGER CLASS
# ─────────────────────────────────────────────


class DeepResearchTrigger:
    """
    Drop-in trigger for the cognition loop.
    Call maybe_trigger() after each cycle — it handles everything else.
    """

    def __init__(self, call_llm_fn: Callable, call_llm_deep_fn: Callable):
        self._call_llm = call_llm_fn
        self._call_llm_deep = call_llm_deep_fn
        self._active = threading.Event()  # Set when deep research is running
        self._lock = threading.Lock()
        self._sessions = 0
        print("🔬 DEEP RESEARCH TRIGGER: Online")

    def maybe_trigger(
        self,
        insight: str,
        topic: str,
        significance: float,
        cycle: int,
        source: str = "llm",
    ):
        """
        Called after each cognition cycle.
        Decides whether to trigger deep research and if so, fires it
        in a background thread.
        """

        # Below quick threshold — skip entirely
        if significance < QUICK_THRESHOLD:
            return

        # Already running one — skip (VRAM constraint)
        if self._active.is_set():
            print(f"🔬 DEEP RESEARCH: Skipping (already active)")
            return
        status = get_deep_research_status()
        if status.get("active"):
            return

        # Topic on cooldown
        if not topic or _is_on_cooldown(topic, cycle):
            return

        # Determine depth
        depth = "standard" if significance >= DEEP_THRESHOLD else "quick"

        print(
            f"🔬 DEEP RESEARCH TRIGGERED: topic='{topic}' sig={significance:.1f} depth={depth} cycle={cycle}"
        )

        # Fire in background
        t = threading.Thread(
            target=self._run,
            args=(insight, topic, depth, cycle),
            daemon=True,
        )
        t.name = f"deep-research-{cycle}"
        t.start()

    def _run(self, insight: str, topic: str, depth: str, cycle: int):
        """The actual deep research pipeline — runs in background thread."""

        self._active.set()
        _set_status(active=True, topic=topic, stage="starting", cycle=cycle)
        _set_cooldown(topic, cycle)

        try:
            from habitat.agents.deep_research import DeepResearcher

            # Build a rich research question from the insight + topic
            question = self._build_question(insight, topic)
            print(f"🔬 DEEP RESEARCH QUESTION: {question}")

            _set_status(active=True, topic=topic, stage="decomposing", cycle=cycle)

            # Use call_llm for the research stages (faster, good enough for sub-questions)
            researcher = DeepResearcher(self._call_llm)
            report = researcher.investigate(question, depth=depth)

            _set_status(active=True, topic=topic, stage="storing", cycle=cycle)

            # Store results
            _store_result(report, cycle)
            self._sessions += 1

            elapsed = report.get("elapsed_seconds", 0)
            sources = report.get("sources_consulted", 0)
            print(
                f"🔬 DEEP RESEARCH COMPLETE: {sources} sources, {elapsed}s, session #{self._sessions}"
            )

        except Exception as e:
            print(f"❌ DEEP RESEARCH ERROR: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
        finally:
            self._active.clear()
            _set_status(active=False, topic=topic, stage="idle", cycle=cycle)

    def _build_question(self, insight: str, topic: str) -> str:
        """
        Turn a raw insight + topic into a well-formed research question.
        Uses a quick LLM call to make it specific and researchable.
        """
        # Extract the core claim from the insight
        core = insight
        for marker in ["Insight:", "Claim:", "Response:"]:
            if marker in core:
                core = core.split(marker)[-1].strip()
        core = core[:300]

        prompt = f"""Convert this into a single, focused research question suitable for deep investigation.

Topic: {topic}
Core insight: {core}

Write ONE specific research question (not a yes/no question, but one that requires investigation).
Question:"""

        question = self._call_llm(prompt, timeout=20)

        # Clean up
        import re

        question = re.sub(r"<think>.*?</think>", "", question, flags=re.DOTALL).strip()
        question = question.split("\n")[0].strip()

        # Fallback if LLM fails
        if not question or len(question) < 15:
            question = f"What are the most significant recent developments and implications of {topic}?"

        return question[:200]

    def get_status(self) -> dict:
        status = get_deep_research_status()
        status["sessions_this_run"] = self._sessions
        return status


# ─────────────────────────────────────────────
# RECENT RESULTS — for UI display
# ─────────────────────────────────────────────


def get_recent_deep_research(limit: int = 5) -> list:
    """Return the most recent deep research sessions for the Stream page."""
    results = []
    try:
        if not os.path.exists(RESULTS_FILE):
            return []
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines[-50:]):
            try:
                results.append(json.loads(line.strip()))
                if len(results) >= limit:
                    break
            except Exception:
                continue
    except Exception:
        pass
    return results
