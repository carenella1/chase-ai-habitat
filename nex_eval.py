"""
nex_eval.py — Fixed Evaluation Harness

WHAT THIS DOES:
  Runs a fixed suite of 24 tasks across 3 categories (memory recall, tool
  selection, reasoning) and produces a single comparable score. Every run
  is tagged with the current git commit, so "did that upgrade actually
  help?" has a real before/after number instead of eyeballed behavior.

WHY DETERMINISTIC CHECKS, NOT AN LLM JUDGE:
  An LLM-judged score adds another model call whose own reliability would
  need verifying — the same "trust the model's self-report" problem that
  nex_verifier.py exists to fix for memory writes. Every task here has a
  single, unambiguous correct answer checked with plain code (substring or
  regex), so a score is fully auditable: read the task list and know
  exactly what "84%" means. Trade-off: it can't score open-ended answer
  quality, only fixed-answer tasks. That's an accepted v1 boundary.

CATEGORIES:
  memory     (8 tasks) — no LLM calls, instant. Seeds a throwaway
             NexMemory(db_path=":memory:") instance (never touches real
             data) and checks storage/retrieval across facts, episodes,
             beliefs, and entity summaries.
  tools      (8 tasks) — no LLM calls, instant. Calls
             habitat/agents/tool_selector.py directly with fixed prompts
             and checks the expected tool (or no tool) fires.
  reasoning  (8 tasks) — uses call_llm, ~1-2 minutes total. Short word
             problems / logic puzzles with one unambiguous answer, checked
             with a word-boundary regex.

USAGE:
    from nex_eval import run_eval_suite
    result = run_eval_suite(call_llm)

  Or, for the background-thread + status-polling pattern used by the
  /api/eval/* routes in run_ui.py:
    from nex_eval import start_eval_run_async, get_eval_status
    start_eval_run_async(call_llm)
"""

import json
import os
import re
import sqlite3
import subprocess
import threading
import time
from datetime import datetime

EVAL_DB = "data/eval_results.db"
STATUS_FILE = "data/system/eval_status.json"
LLM_TASK_TIMEOUT = 60  # short prompts elsewhere in the codebase (deep_research.py's
# _decompose/_critique) use 45s; 60s gives headroom for a cold model without
# letting one hung call blow up the whole suite's runtime
TASK_COUNT = 24

_eval_active = threading.Event()


# ─────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────


def _conn():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(EVAL_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS eval_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT,
            git_commit TEXT,
            label TEXT,
            overall_score REAL,
            category_scores TEXT,
            task_results TEXT,
            elapsed_seconds REAL
        )"""
    )
    conn.commit()
    return conn


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()


def _check(task_id: str, category: str, description: str, passed: bool) -> dict:
    return {
        "id": task_id,
        "category": category,
        "description": description,
        "passed": bool(passed),
    }


# ─────────────────────────────────────────────
# MEMORY RECALL TASKS — no LLM calls, isolated in-memory DB
# ─────────────────────────────────────────────


def _run_memory_tasks() -> list:
    from structured_memory import NexMemory

    mem = NexMemory(db_path=":memory:")
    results = []

    mem.learn(
        "Nexarion's local model router is called llm_router and talks to "
        "Ollama on port 11434.",
        topic="architecture",
    )
    r = mem.recall("llm_router")
    results.append(
        _check(
            "memory_fact_recall",
            "memory",
            "a world fact stored via learn() is retrievable via recall()",
            "llm_router" in r.lower(),
        )
    )

    mem.remember(
        "Investigated the causes of the 2026 global chip shortage",
        agent="Researcher",
        importance=0.9,
    )
    r = mem.recall("chip shortage")
    results.append(
        _check(
            "memory_episodic_recall",
            "memory",
            "an episodic memory stored via remember() is retrievable via recall()",
            "chip shortage" in r.lower(),
        )
    )

    mem.believe("Local LLMs will match GPT-4 class quality by 2027", confidence=0.6)
    r = mem.recall("Local LLMs will match GPT-4")
    results.append(
        _check(
            "memory_belief_recall",
            "memory",
            "a belief formed via believe() is retrievable via recall() with its confidence",
            "[belief" in r.lower() and "60%" in r,
        )
    )

    # Restating the exact same belief should reinforce (raise) its confidence.
    mem.believe("Local LLMs will match GPT-4 class quality by 2027", confidence=0.6)
    active = mem.beliefs.get_active_beliefs(limit=20)
    reinforced = next(
        (b for b in active if b["statement"].startswith("Local LLMs will match")),
        None,
    )
    results.append(
        _check(
            "memory_belief_reinforcement",
            "memory",
            "restating an existing belief raises its confidence rather than duplicating it",
            bool(reinforced) and reinforced["confidence"] > 0.6,
        )
    )

    mem.know_entity(
        "Nexarion",
        "NEX's internal codename for the overall cognition system.",
        entity_type="concept",
    )
    e = mem.entities.get("Nexarion")
    results.append(
        _check(
            "memory_entity_recall",
            "memory",
            "an entity summary stored via know_entity() is retrievable",
            bool(e) and "codename" in e.get("summary", "").lower(),
        )
    )

    # A fresh, empty memory should return nothing for any query, rather than
    # "the closest thing it has" -- a real risk once semantic embeddings are
    # enabled, since facts/beliefs/episodes search doesn't threshold on
    # similarity score (it always returns the top-N rows that exist, however
    # unrelated). Uses a separate empty instance rather than querying `mem`
    # with a nonsense token, since that check would pass trivially whether
    # or not real hallucination protection exists.
    empty_mem = NexMemory(db_path=":memory:")
    r = empty_mem.recall("what happened with the chip shortage")
    results.append(
        _check(
            "memory_no_hallucinated_recall",
            "memory",
            "an empty memory returns nothing rather than fabricating a match",
            r.strip() == "",
        )
    )

    mem.remember(
        "Synthesized a cross-topic essay on entropy and information theory",
        agent="Archivist",
        importance=0.95,
    )
    ctx = mem.get_memory_context_for_prompt("what have you been thinking about?")
    results.append(
        _check(
            "memory_context_injection_episode",
            "memory",
            "a high-importance episode appears in get_memory_context_for_prompt() "
            "regardless of query wording",
            "entropy and information theory" in ctx,
        )
    )

    mem.believe(
        "Structured memory beats flat JSON logs for long-term continuity",
        confidence=0.75,
    )
    ctx = mem.get_memory_context_for_prompt("anything at all")
    results.append(
        _check(
            "memory_context_injection_belief",
            "memory",
            "an active belief appears in get_memory_context_for_prompt() regardless "
            "of query wording",
            "structured memory beats flat json" in ctx.lower(),
        )
    )

    return results


# ─────────────────────────────────────────────
# TOOL SELECTION TASKS — no LLM calls, pure regex selector
# ─────────────────────────────────────────────


def _run_tool_tasks() -> list:
    from habitat.agents.tool_selector import select_tools_for_message

    cases = [
        (
            "tool_market_data",
            "market_data",
            "What's the current price of gold right now?",
        ),
        ("tool_calculator", "calculator", "Calculate 45 * 12 + 8"),
        (
            "tool_news_search",
            "news_search",
            "What's the latest news about the Federal Reserve?",
        ),
        (
            "tool_wiki_deep",
            "wiki_deep",
            "Give me a deep dive on quantum entanglement",
        ),
        (
            "tool_web_fetch",
            "web_fetch",
            "Fetch https://example.com and summarize it",
        ),
        (
            "tool_python_exec",
            "python_exec",
            "Run this code: ```python\nprint(2+2)\n```",
        ),
        (
            "tool_web_search",
            "web_search",
            "Who is the current president of France?",
        ),
        (
            "tool_no_tool_for_chitchat",
            None,
            "I really enjoyed our conversation yesterday, thank you for "
            "explaining that so clearly.",
        ),
    ]

    results = []
    for task_id, expected_tool, message in cases:
        selected = select_tools_for_message(message)
        actual_tool = selected[0][0] if selected else None
        desc = f"\"{message[:55]}\" should select {expected_tool or 'no tool'}"
        results.append(_check(task_id, "tools", desc, actual_tool == expected_tool))
    return results


# ─────────────────────────────────────────────
# REASONING CHAIN TASKS — uses call_llm
# ─────────────────────────────────────────────


def _run_reasoning_tasks(call_llm_fn) -> list:
    cases = [
        (
            "reasoning_word_problem_distance",
            "If a train travels at 60 mph for 2.5 hours, how far does it "
            "travel? Reply with only the number of miles, nothing else.",
            r"\b150\b",
        ),
        (
            "reasoning_ordering",
            "Alice is older than Bob. Bob is older than Carol. Who is the "
            "youngest of the three? Reply with only their name.",
            r"\bcarol\b",
        ),
        (
            "reasoning_order_of_operations",
            "What is 7 + 3 * 2? Reply with only the number.",
            r"\b13\b",
        ),
        (
            "reasoning_syllogism",
            "All cats are mammals. Whiskers is a cat. Is Whiskers a mammal? "
            "Reply with only yes or no.",
            r"\byes\b",
        ),
        (
            "reasoning_sequence",
            "What comes next in this sequence: 2, 4, 8, 16, ...? Reply with "
            "only the number.",
            r"\b32\b",
        ),
        (
            "reasoning_two_step_word_problem",
            "Sarah has 3 times as many apples as Tom. Tom has 4 apples. How "
            "many apples do they have together? Reply with only the number.",
            r"\b16\b",
        ),
        (
            "reasoning_conditional_negation",
            "Sam brings an umbrella only if it is raining. It is not raining "
            "today. Does Sam bring an umbrella? Reply with only yes or no.",
            r"\bno\b",
        ),
        (
            "reasoning_code_trace",
            "What does this Python code print?\nx = 5\ny = x * 2 + 1\n"
            "print(y)\nReply with only the number.",
            r"\b11\b",
        ),
    ]

    results = []
    for task_id, prompt, expected_pattern in cases:
        try:
            raw = call_llm_fn(prompt, timeout=LLM_TASK_TIMEOUT)
            if isinstance(raw, tuple):  # defensive: log_thinking=True shape
                raw = raw[0]
        except Exception as e:
            raw = f"[call_llm error: {e}]"
        answer = _strip_think(raw)
        passed = bool(re.search(expected_pattern, answer, re.IGNORECASE))
        desc = f"expects an answer matching {expected_pattern}"
        results.append(
            {
                "id": task_id,
                "category": "reasoning",
                "description": desc,
                "passed": passed,
                "raw_answer": answer[:200],
            }
        )
    return results


# ─────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────


def run_eval_suite(call_llm_fn, label: str = None, on_progress=None) -> dict:
    """
    Runs all 24 tasks and persists the result. Safe to call directly and
    synchronously (memory+tools finish instantly; reasoning takes ~1-2 min).
    `on_progress(str)`, if given, is called with short status updates.
    """
    start = time.time()

    if on_progress:
        on_progress("running memory recall tasks")
    all_results = _run_memory_tasks()

    if on_progress:
        on_progress("running tool selection tasks")
    all_results += _run_tool_tasks()

    if on_progress:
        on_progress("running reasoning tasks (this is the slow part — uses the local model)")
    all_results += _run_reasoning_tasks(call_llm_fn)

    categories = {}
    for r in all_results:
        c = categories.setdefault(r["category"], {"passed": 0, "total": 0})
        c["total"] += 1
        if r["passed"]:
            c["passed"] += 1
    category_scores = {
        cat: round(v["passed"] / v["total"], 3) if v["total"] else 0.0
        for cat, v in categories.items()
    }

    total_passed = sum(1 for r in all_results if r["passed"])
    overall_score = round(total_passed / len(all_results), 3) if all_results else 0.0
    elapsed = round(time.time() - start, 1)

    run = {
        "run_at": datetime.utcnow().isoformat(),
        "git_commit": _git_commit(),
        "label": label or "",
        "overall_score": overall_score,
        "category_scores": category_scores,
        "task_results": all_results,
        "elapsed_seconds": elapsed,
    }
    _save_run(run)
    print(
        f"📊 EVAL: {total_passed}/{len(all_results)} passed "
        f"({overall_score:.0%}) in {elapsed}s [{run['git_commit']}]"
    )
    return run


def _save_run(run: dict):
    conn = _conn()
    conn.execute(
        """INSERT INTO eval_runs
           (run_at, git_commit, label, overall_score, category_scores,
            task_results, elapsed_seconds)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            run["run_at"],
            run["git_commit"],
            run["label"],
            run["overall_score"],
            json.dumps(run["category_scores"]),
            json.dumps(run["task_results"]),
            run["elapsed_seconds"],
        ),
    )
    conn.commit()
    conn.close()


def get_eval_history(limit: int = 20) -> list:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM eval_runs ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    out = []
    for row in rows:
        d = dict(row)
        d["category_scores"] = json.loads(d["category_scores"] or "{}")
        d["task_results"] = json.loads(d["task_results"] or "[]")
        out.append(d)
    return out


def get_latest_eval() -> dict:
    hist = get_eval_history(limit=1)
    return hist[0] if hist else {}


# ─────────────────────────────────────────────
# BACKGROUND-THREAD RUNNER — mirrors deep_research_trigger.py's
# status-file pattern so the UI can poll progress without blocking
# a Flask request thread for the ~1-2 minutes a run takes.
# ─────────────────────────────────────────────


def _set_status(active: bool, message: str = ""):
    os.makedirs("data/system", exist_ok=True)
    try:
        with open(STATUS_FILE, "w") as f:
            json.dump(
                {"active": active, "message": message, "timestamp": int(time.time())},
                f,
            )
    except Exception:
        pass


def get_eval_status() -> dict:
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE) as f:
                data = json.load(f)
            # Auto-expire if something crashed mid-run
            if time.time() - data.get("timestamp", 0) > 600:
                data["active"] = False
            return data
    except Exception:
        pass
    return {"active": False, "message": ""}


def start_eval_run_async(call_llm_fn, label: str = None) -> bool:
    """Kick off run_eval_suite() in a background thread. Returns False (and
    does nothing) if a run is already active."""
    if _eval_active.is_set():
        return False

    def _worker():
        _eval_active.set()
        _set_status(True, "starting")
        try:
            run_eval_suite(
                call_llm_fn, label=label, on_progress=lambda m: _set_status(True, m)
            )
            _set_status(False, "done")
        except Exception as e:
            _set_status(False, f"error: {e}")
        finally:
            _eval_active.clear()

    t = threading.Thread(target=_worker, daemon=True)
    t.name = "nex-eval-run"
    t.start()
    return True
