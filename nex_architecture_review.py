"""
nex_architecture_review.py — NEX reviews its own recent code changes and
proposes updates to the How Nex Works page (how_it_works_content.json) when
something it describes has gone stale.

This exists because the page already drifted once: a subsystem went from
dormant to live and the page kept saying "none of this runs" for a full
session afterward. Rather than relying purely on remembering to update the
page by hand, NEX periodically looks at what actually changed in the
codebase and drafts proposed corrections -- but nothing it drafts goes live
without a human approving it first, the same trust-gated pattern already
used for sandbox code execution and self-optimizer prompt rewrites.

Deliberately bounded for safety: proposals can only ever change plain-text
fields (kicker/title/status/lead/why_hook/why_body/facts) within the fixed
card structure the template already renders -- never raw HTML, styling, or
script. See CONTENT_SCHEMA_KEYS below.
"""

import json
import os
import re
import sqlite3
import subprocess
import threading
import time
from datetime import datetime

REVIEW_STATE_FILE = "data/architecture_review_state.json"
REVIEW_DB = "data/architecture_review.db"
CONTENT_FILE = "how_it_works_content.json"

REVIEW_INTERVAL_SECONDS = 7 * 86400  # weekly
FALLBACK_COMMIT_WINDOW = 20  # if there's no prior review, look at the last N commits
MAX_DIFF_LINES_PER_FILE = 150

# Only files that an existing (or plausible new) card would describe get a
# capped diff included in the review prompt -- keeps the prompt small and
# targeted rather than dumping the whole repo's changes.
NOTABLE_FILES = [
    "run_ui.py",
    "nex_trainer.py",
    "self_optimizer.py",
    "nex_sandbox.py",
    "nex_digest.py",
    "launch_habitat.py",
    "docker-compose.yml",
    "structured_memory.py",
    "knowledge_graph.py",
    "nex_docker_agent.py",
    "deep_research_trigger.py",
    "habitat/agents/tool_executor.py",
]

# The only fields a proposal is ever allowed to touch. Anything else in a
# proposed_fields dict is silently dropped when applied.
CONTENT_SCHEMA_KEYS = {
    "kicker",
    "title",
    "status",
    "lead",
    "why_hook",
    "why_body",
    "facts",
}
VALID_STATUSES = {"live", "manual", "dormant"}

_lock = threading.Lock()


# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────


def _load_state() -> dict:
    if not os.path.exists(REVIEW_STATE_FILE):
        return {"last_reviewed_sha": "", "last_reviewed_at": 0}
    try:
        with open(REVIEW_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_reviewed_sha": "", "last_reviewed_at": 0}


def _save_state(state: dict):
    os.makedirs("data", exist_ok=True)
    with open(REVIEW_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def is_due() -> bool:
    state = _load_state()
    return (time.time() - state.get("last_reviewed_at", 0)) >= REVIEW_INTERVAL_SECONDS


def get_status() -> dict:
    state = _load_state()
    return {
        "last_reviewed_at": int(state.get("last_reviewed_at", 0)),
        "last_reviewed_sha": state.get("last_reviewed_sha", ""),
        "next_due_at": int(state.get("last_reviewed_at", 0) + REVIEW_INTERVAL_SECONDS),
    }


# ─────────────────────────────────────────────
# DATABASE — mirrors nex_sandbox.SandboxLog's pending_approvals shape
# ─────────────────────────────────────────────


def _conn():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(REVIEW_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id TEXT NOT NULL,
            action TEXT NOT NULL,
            proposed_fields_json TEXT NOT NULL,
            reasoning TEXT,
            commit_range TEXT,
            status TEXT DEFAULT 'pending',
            submitted_at TEXT
        )"""
    )
    conn.commit()
    return conn


def get_pending_proposals() -> list:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM proposals WHERE status = 'pending' ORDER BY id DESC"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["proposed_fields"] = json.loads(d.pop("proposed_fields_json"))
        except Exception:
            d["proposed_fields"] = {}
        out.append(d)
    return out


def _get_proposal(proposal_id: int):
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM proposals WHERE id = ? AND status = 'pending'", (proposal_id,)
    ).fetchone()
    return dict(row) if row else None


def _mark_status(proposal_id: int, status: str):
    conn = _conn()
    conn.execute("UPDATE proposals SET status = ? WHERE id = ?", (status, proposal_id))
    conn.commit()


def reject_proposal(proposal_id: int) -> bool:
    proposal = _get_proposal(proposal_id)
    if not proposal:
        return False
    _mark_status(proposal_id, "rejected")
    return True


def approve_proposal(proposal_id: int) -> bool:
    """Apply the proposal's fields onto how_it_works_content.json. Only
    whitelisted schema keys are ever written -- anything else in the
    proposal is dropped, not applied."""
    proposal = _get_proposal(proposal_id)
    if not proposal:
        return False

    try:
        proposed_fields = json.loads(proposal["proposed_fields_json"])
    except Exception:
        proposed_fields = {}
    safe_fields = {k: v for k, v in proposed_fields.items() if k in CONTENT_SCHEMA_KEYS}
    if "status" in safe_fields and safe_fields["status"] not in VALID_STATUSES:
        safe_fields.pop("status")

    with _lock:
        try:
            with open(CONTENT_FILE, "r", encoding="utf-8") as f:
                cards = json.load(f)
        except Exception as e:
            print(f"⚠️ ARCH REVIEW: could not read {CONTENT_FILE} — {e}")
            return False

        card_id = proposal["card_id"]
        existing = next((c for c in cards if c.get("id") == card_id), None)

        if proposal["action"] == "new" and not existing:
            new_card = {
                "id": card_id,
                "kicker": "",
                "title": card_id.replace("-", " ").title(),
                "status": "dormant",
                "lead": "",
                "why_hook": "",
                "why_body": "",
                "facts": [],
                "live_status_check": None,
            }
            new_card.update(safe_fields)
            cards.append(new_card)
        elif existing:
            existing.update(safe_fields)
        else:
            print(f"⚠️ ARCH REVIEW: proposal for unknown card '{card_id}', dropped")
            return False

        try:
            with open(CONTENT_FILE, "w", encoding="utf-8") as f:
                json.dump(cards, f, indent=2)
        except Exception as e:
            print(f"⚠️ ARCH REVIEW: could not write {CONTENT_FILE} — {e}")
            return False

    _mark_status(proposal_id, "approved")
    print(f"✅ ARCH REVIEW: proposal #{proposal_id} approved -> applied to '{card_id}'")
    return True


# ─────────────────────────────────────────────
# GIT — what actually changed since the last review
# ─────────────────────────────────────────────


def _run_git(args: list) -> str:
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"⚠️ ARCH REVIEW: git command failed {args} — {e}")
        return ""


def _current_sha() -> str:
    return _run_git(["rev-parse", "HEAD"])


def _gather_changes(last_sha: str) -> dict:
    """Returns {'commit_log': str, 'changed_files': [str], 'diffs': {file: str},
    'range_label': str}. If there's no prior review, falls back to the last
    FALLBACK_COMMIT_WINDOW commits rather than diffing all of history."""
    if last_sha:
        range_spec = f"{last_sha}..HEAD"
        commit_log = _run_git(["log", "--oneline", range_spec])
        changed_files_raw = _run_git(["diff", "--name-only", range_spec])
    else:
        range_spec = f"-{FALLBACK_COMMIT_WINDOW}"
        commit_log = _run_git(["log", "--oneline", range_spec])
        changed_files_raw = _run_git(
            ["diff", "--name-only", f"HEAD~{FALLBACK_COMMIT_WINDOW}", "HEAD"]
        )

    changed_files = [l for l in changed_files_raw.splitlines() if l.strip()]

    diffs = {}
    for f in changed_files:
        if f not in NOTABLE_FILES:
            continue
        diff_spec = range_spec if last_sha else f"HEAD~{FALLBACK_COMMIT_WINDOW}..HEAD"
        diff_text = _run_git(["diff", diff_spec, "--", f])
        if diff_text:
            diffs[f] = "\n".join(diff_text.splitlines()[:MAX_DIFF_LINES_PER_FILE])

    return {
        "commit_log": commit_log,
        "changed_files": changed_files,
        "diffs": diffs,
        "range_label": range_spec,
    }


# ─────────────────────────────────────────────
# PROPOSAL GENERATION
# ─────────────────────────────────────────────


def _build_prompt(cards: list, changes: dict) -> str:
    current_content = json.dumps(
        [
            {k: c.get(k) for k in ["id", "kicker", "title", "status", "lead", "why_hook", "why_body", "facts"]}
            for c in cards
        ],
        indent=2,
    )
    diffs_block = "\n\n".join(
        f"--- diff for {f} ---\n{d}" for f, d in changes["diffs"].items()
    )

    return f"""You are reviewing recent code changes to decide whether an explainer page
about your own architecture ("How Nex Works") has gone out of date.

CURRENT PAGE CONTENT (one card per subsystem):
{current_content}

RECENT COMMITS:
{changes['commit_log'] or '(none)'}

CHANGED FILES:
{', '.join(changes['changed_files']) or '(none)'}

{diffs_block}

For each existing card, decide if these changes make anything it says inaccurate
(e.g. a status that should change from dormant to live, or a described
behavior that no longer matches the code). If a genuinely new subsystem was
introduced that deserves its own card, propose one.

Respond with ONLY a JSON array (no markdown fences, no explanation), where each
item has this exact shape:
{{
  "card_id": "existing-card-id-or-new-slug",
  "action": "update" | "new" | "status_change",
  "reasoning": "one or two sentences citing the specific change",
  "proposed_fields": {{
    "status": "live|manual|dormant"    (only if changing),
    "lead": "...",                      (only if changing)
    "why_hook": "...",                  (only if changing)
    "why_body": "...",                  (only if changing)
    "facts": ["...", "..."]             (only if changing)
  }}
}}

Only include fields that should actually change. If nothing needs updating,
respond with an empty array: []"""


def _parse_proposals(raw: str) -> list:
    if not raw:
        return []
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        text = match.group(0)
    try:
        proposals = json.loads(text)
        if not isinstance(proposals, list):
            return []
        return proposals
    except Exception as e:
        print(f"⚠️ ARCH REVIEW: could not parse LLM proposals — {e}")
        return []


def run_review(call_llm_deep_fn):
    """Main entry point. Safe to call unconditionally -- checks its own
    due-ness internally when called from the cognition loop; the manual
    'Review Now' path bypasses is_due() intentionally."""
    with _lock:
        state = _load_state()
        current_sha = _current_sha()
        if not current_sha:
            print("⚠️ ARCH REVIEW: could not resolve current git SHA, skipping")
            return

        changes = _gather_changes(state.get("last_reviewed_sha", ""))
        if not changes["commit_log"]:
            print("📐 ARCH REVIEW: no new commits since last review")
            _save_state({"last_reviewed_sha": current_sha, "last_reviewed_at": time.time()})
            return

        try:
            with open(CONTENT_FILE, "r", encoding="utf-8") as f:
                cards = json.load(f)
        except Exception as e:
            print(f"⚠️ ARCH REVIEW: could not read {CONTENT_FILE} — {e}")
            return

        prompt = _build_prompt(cards, changes)
        llm_call_succeeded = False
        try:
            # No explicit timeout override -- this is a weekly background
            # task with nobody waiting, so it uses llm_router's own generous
            # DEEP_TIMEOUT default rather than a latency-tuned shorter one.
            result = call_llm_deep_fn(prompt)
            raw = result.get("response", "") if isinstance(result, dict) else str(result)
            llm_call_succeeded = bool(raw)
        except Exception as e:
            print(f"⚠️ ARCH REVIEW: LLM call failed — {e}")
            raw = ""

        if not llm_call_succeeded:
            # Don't advance last_reviewed_sha on a failed/timed-out/empty
            # call -- these commits need to actually be reviewed next time,
            # not silently skipped forever because a run happened to fail.
            print("⚠️ ARCH REVIEW: LLM call produced no output, will retry this same range next time")
            return

        proposals = _parse_proposals(raw)
        known_ids = {c["id"] for c in cards}
        stored = 0
        conn = _conn()
        for p in proposals:
            card_id = p.get("card_id")
            action = p.get("action")
            if not card_id or action not in ("update", "new", "status_change"):
                continue
            if action != "new" and card_id not in known_ids:
                continue
            proposed_fields = p.get("proposed_fields", {})
            if not isinstance(proposed_fields, dict) or not proposed_fields:
                continue
            conn.execute(
                """INSERT INTO proposals
                   (card_id, action, proposed_fields_json, reasoning, commit_range, status, submitted_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    card_id,
                    action,
                    json.dumps(proposed_fields),
                    p.get("reasoning", ""),
                    changes["range_label"],
                    datetime.utcnow().isoformat(),
                ),
            )
            stored += 1
        conn.commit()

        _save_state({"last_reviewed_sha": current_sha, "last_reviewed_at": time.time()})
        print(f"📐 ARCH REVIEW: {stored} proposal(s) generated from {changes['range_label']}")


def run_review_async(call_llm_deep_fn):
    threading.Thread(target=run_review, args=(call_llm_deep_fn,), daemon=True).start()
