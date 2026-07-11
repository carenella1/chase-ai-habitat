"""
nex_digest.py — Daily briefing of what NEX has been up to.

NEX's background cognition loop runs constantly, but almost none of it is
visible unless you go digging through the Self/Discovery/Memory dashboards.
This module periodically (once a day, wall-clock — not cycle-count, since
cycle time drifts with LLM load) collects what actually changed since the
last briefing — new beliefs, resolved contradictions, completed deep
research, self-model observations — and asks the fast chat model to write a
short, structured summary. Stored append-only, same shape as the journal.

Called from run_ui.py's cognition loop via `maybe_generate_digest()`.
"""

import json
import os
import time
from datetime import datetime

DIGEST_STATE_FILE = "data/digest_state.json"
DIGEST_LOG_FILE = "data/nex_digests.jsonl"
DIGEST_INTERVAL_SECONDS = 86400  # once a day

MAX_ITEMS_PER_SECTION = 8


def _load_state() -> dict:
    if not os.path.exists(DIGEST_STATE_FILE):
        return {"last_digest_at": 0}
    try:
        with open(DIGEST_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_digest_at": 0}


def _save_state(state: dict):
    os.makedirs("data", exist_ok=True)
    with open(DIGEST_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def is_due() -> bool:
    state = _load_state()
    return (time.time() - state.get("last_digest_at", 0)) >= DIGEST_INTERVAL_SECONDS


def _iso_from_epoch(epoch_ts: float) -> str:
    return datetime.utcfromtimestamp(epoch_ts).isoformat()


def _gather_beliefs(nex_memory, since_ts: float) -> list:
    try:
        rows = nex_memory.beliefs.beliefs_since(_iso_from_epoch(since_ts))
        return [r.get("statement", "") for r in rows[:MAX_ITEMS_PER_SECTION] if r.get("statement")]
    except Exception as e:
        print(f"⚠️ DIGEST: belief gather error — {e}")
        return []


def _gather_facts(nex_memory, since_ts: float) -> list:
    try:
        rows = nex_memory.facts.facts_since(_iso_from_epoch(since_ts))
        return [r.get("content", "") for r in rows[:MAX_ITEMS_PER_SECTION] if r.get("content")]
    except Exception as e:
        print(f"⚠️ DIGEST: fact gather error — {e}")
        return []


def _gather_resolved_contradictions(since_ts: float) -> list:
    try:
        from habitat.reasoning.contradiction_engine import load_contradictions

        data = load_contradictions()
        resolved = [
            r for r in data.get("resolved", []) if r.get("resolved_at", 0) > since_ts
        ]
        return [
            f"{r.get('verdict', '?')}: {r.get('resolution_text', '')[:200]}"
            for r in resolved[:MAX_ITEMS_PER_SECTION]
        ]
    except Exception as e:
        print(f"⚠️ DIGEST: contradiction gather error — {e}")
        return []


def _gather_deep_research(since_ts: float) -> list:
    try:
        from deep_research_trigger import RESULTS_FILE

        if not os.path.exists(RESULTS_FILE):
            return []
        items = []
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue
                if entry.get("timestamp", 0) > since_ts:
                    items.append(entry)
        items.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
        return [
            f"{e.get('question', '')}: {e.get('synthesis', '')[:250]}"
            for e in items[:MAX_ITEMS_PER_SECTION]
        ]
    except Exception as e:
        print(f"⚠️ DIGEST: deep research gather error — {e}")
        return []


def _gather_self_observations(since_ts: float) -> list:
    try:
        from habitat.self_model.self_model import get_full_model

        model = get_full_model()
        obs = [
            o
            for o in model.get("self_observations", [])
            if o.get("timestamp", 0) > since_ts
        ]
        return [o.get("observation", "") for o in obs[:MAX_ITEMS_PER_SECTION] if o.get("observation")]
    except Exception as e:
        print(f"⚠️ DIGEST: self-observation gather error — {e}")
        return []


def _build_prompt(period_start_human: str, sections: dict) -> str:
    def block(title, items):
        if not items:
            return ""
        lines = "\n".join(f"- {i}" for i in items)
        return f"\n{title}:\n{lines}\n"

    body = (
        block("New beliefs formed", sections["beliefs"])
        + block("New facts learned", sections["facts"])
        + block("Contradictions resolved", sections["contradictions"])
        + block("Deep research completed", sections["deep_research"])
        + block("Self-observations", sections["self_observations"])
    )

    if not body.strip():
        return ""

    return f"""You are writing a short daily briefing for Chase, summarizing what
Nexarion's background thinking has produced since {period_start_human}.

Raw material from the last day:
{body}

Write a compact briefing with this structure:

CORE UNDERSTANDING
[1-2 sentences: what stood out most]

KEY CONCLUSIONS
[bullet-style, 2-4 items — the most significant new beliefs/facts]

OPEN QUESTIONS
[bullet-style, 1-3 items — things still uncertain or worth Chase's attention]

CONFIDENCE
[High/Medium/Low — how solid this day's thinking was overall, one line why]

Be concrete and specific. No filler, no restating this instruction."""


def generate_digest(call_llm_fn, nex_memory) -> dict:
    """
    Gather what's changed since the last digest, write a summary, store it,
    and advance the digest state. Safe to call unconditionally — internally
    checks is_due(). Returns the new entry dict, or None if not due yet or
    generation failed.
    """
    if not is_due():
        return None

    state = _load_state()
    since_ts = state.get("last_digest_at", 0) or (time.time() - DIGEST_INTERVAL_SECONDS)
    period_start_human = datetime.utcfromtimestamp(since_ts).strftime("%Y-%m-%d %H:%M UTC")

    sections = {
        "beliefs": _gather_beliefs(nex_memory, since_ts),
        "facts": _gather_facts(nex_memory, since_ts),
        "contradictions": _gather_resolved_contradictions(since_ts),
        "deep_research": _gather_deep_research(since_ts),
        "self_observations": _gather_self_observations(since_ts),
    }
    counts = {k: len(v) for k, v in sections.items()}
    total_items = sum(counts.values())

    if total_items == 0:
        digest_text = (
            "Quiet stretch — nothing new formed, resolved, or researched "
            "since the last briefing."
        )
    else:
        prompt = _build_prompt(period_start_human, sections)
        try:
            digest_text = call_llm_fn(prompt, timeout=60)
        except Exception as e:
            print(f"⚠️ DIGEST: generation error — {e}")
            digest_text = ""
        if not digest_text or len(digest_text.strip()) < 20:
            digest_text = (
                f"{total_items} new item(s) since the last briefing, but the "
                "summary couldn't be generated this time."
            )

    now = time.time()
    entry = {
        "timestamp": int(now),
        "timestamp_human": time.strftime("%Y-%m-%d %H:%M:%S"),
        "period_start": int(since_ts),
        "period_start_human": period_start_human,
        "digest": digest_text.strip(),
        "counts": counts,
    }

    os.makedirs("data", exist_ok=True)
    with open(DIGEST_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    _save_state({"last_digest_at": now})
    print(f"📰 DIGEST: written ({total_items} items since {period_start_human})")
    return entry


def get_status() -> dict:
    """Status summary for the /api/digest/status endpoint."""
    state = _load_state()
    last_at = state.get("last_digest_at", 0)
    total = 0
    if os.path.exists(DIGEST_LOG_FILE):
        try:
            with open(DIGEST_LOG_FILE, "r", encoding="utf-8") as f:
                total = sum(1 for line in f if line.strip())
        except Exception:
            pass
    return {
        "last_digest_at": int(last_at),
        "next_due_at": int(last_at + DIGEST_INTERVAL_SECONDS),
        "total_entries": total,
    }


def get_entries(limit: int = 50) -> list:
    if not os.path.exists(DIGEST_LOG_FILE):
        return []
    entries = []
    try:
        with open(DIGEST_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    except Exception:
        pass
    return list(reversed(entries[-limit:]))
