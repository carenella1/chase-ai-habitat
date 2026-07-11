"""
nex_verifier.py — Independent Verification Gate

WHAT THIS DOES:
  A second, independently-prompted LLM call whose only job is skepticism,
  run before a claim is written into structured_memory. Today NEX's two
  live memory-write pipelines write straight to the database at whatever
  confidence the caller (or the same model that generated the claim) hands
  them:
    - run_ui.py's cognition loop -> nex_memory.learn() for every cycle's
      web-research snippet, flat confidence 0.7 regardless of quality.
    - deep_research_trigger.py -> mem.learn() for deep-research
      conclusions, at whatever confidence the *same* synthesis pipeline's
      own self-critique assigned itself.
  Neither is checked by anything independent. Left unchecked, a single
  bad or garbled claim just sits in memory at face-value confidence and
  compounds into future reasoning built on top of it.

TWO PROMPT MODES — because the two call sites hand this genuinely
different material:
  "web_fact" — the claim and its "source" are the same scraped web text
      (run_ui.py's `research` variable is already near-verbatim extracted
      page text, not a separate LLM-generated claim about a source). So
      this mode isn't a hallucination cross-check, it's a coherence /
      plausibility gate: is this actually meaningful factual content, or
      scraper noise, nav junk, ad copy, or garbled HTML dressed up as a
      "quality_score"?
  "research_conclusion" — real independent evidence exists here (the raw
      tool data gathered during a deep-research investigation). The
      verifier is asked directly whether that evidence supports the
      conclusion, or whether the conclusion overreaches beyond what was
      actually found. This is the real "is this claim supported by the
      source" check.

USAGE:
    from nex_verifier import verify_claim, gate_confidence

    result = verify_claim(claim_text, evidence_text, call_llm, claim_kind="web_fact")
    final_confidence = gate_confidence(
        0.7, result, claim=claim_text, evidence=evidence_text,
        claim_kind="web_fact", source="web",
    )
    if final_confidence is not None:
        nex_memory.learn(claim_text, confidence=final_confidence, ...)
    # else: the verifier rejected it -- don't write it.

Every check (accepted or rejected) is logged to data/verifier_log.db so
"why didn't NEX remember X" is answerable later.
"""

import json
import os
import re
import sqlite3
import time
from datetime import datetime
from typing import Optional

VERIFIER_DB = "data/verifier_log.db"
REJECT_FLOOR = 0.35  # verifier confidence below this -> the claim is not written
VERIFIER_TIMEOUT = 45  # matches other short single-call prompts elsewhere
# (deep_research.py's _decompose/_critique, deep_research_trigger.py's
# _build_question all use 45s)


# ─────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────


def _conn():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(VERIFIER_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checked_at TEXT,
            claim_kind TEXT,
            source TEXT,
            claim TEXT,
            evidence_snippet TEXT,
            verdict TEXT,
            verifier_confidence REAL,
            original_confidence REAL,
            final_confidence REAL,
            reasoning TEXT,
            parsed INTEGER
        )"""
    )
    conn.commit()
    return conn


def _log_verification(
    claim: str,
    evidence: str,
    claim_kind: str,
    source: str,
    verdict: str,
    verifier_confidence: float,
    original_confidence: float,
    final_confidence: Optional[float],
    reasoning: str,
    parsed: bool,
):
    try:
        conn = _conn()
        conn.execute(
            """INSERT INTO verifications
               (checked_at, claim_kind, source, claim, evidence_snippet, verdict,
                verifier_confidence, original_confidence, final_confidence,
                reasoning, parsed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.utcnow().isoformat(),
                claim_kind,
                source,
                (claim or "")[:500],
                (evidence or "")[:300],
                verdict,
                verifier_confidence,
                original_confidence,
                final_confidence,
                (reasoning or "")[:300],
                1 if parsed else 0,
            ),
        )
        # Keep the log from growing unbounded -- this is an audit trail for
        # recent decisions, not a permanent record.
        conn.execute(
            """DELETE FROM verifications WHERE id NOT IN (
                   SELECT id FROM verifications ORDER BY id DESC LIMIT 5000
               )"""
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ VERIFIER: log write failed: {e}")


def get_verifier_stats(recent_limit: int = 25) -> dict:
    conn = _conn()
    total = conn.execute("SELECT COUNT(*) c FROM verifications").fetchone()["c"]
    accepted = conn.execute(
        "SELECT COUNT(*) c FROM verifications WHERE verdict = 'accepted'"
    ).fetchone()["c"]
    rejected = total - accepted
    recent = conn.execute(
        "SELECT * FROM verifications ORDER BY id DESC LIMIT ?", (recent_limit,)
    ).fetchall()
    conn.close()
    return {
        "total_checked": total,
        "accepted": accepted,
        "rejected": rejected,
        "accept_rate": round(accepted / total, 3) if total else None,
        "recent": [dict(r) for r in recent],
    }


# ─────────────────────────────────────────────
# VERIFICATION
# ─────────────────────────────────────────────


def _build_prompt(claim: str, evidence: str, claim_kind: str) -> str:
    if claim_kind == "research_conclusion":
        return f"""You are an independent fact-checker. You did not write the conclusion below — your only job is to judge whether the evidence actually supports it.

EVIDENCE (gathered during research):
{evidence[:2000] or "(no evidence text available)"}

CONCLUSION (drawn from that evidence):
{claim[:600]}

Does the evidence actually support this conclusion, or does the conclusion overreach beyond what the evidence shows?

Respond in exactly this format:
SUPPORTED: yes or no
CONFIDENCE: a number from 0 to 100
REASON: one sentence explaining your judgment"""

    # "web_fact" -- claim and evidence are the same scraped web text; this
    # is a coherence/plausibility gate, not a source cross-check.
    return f"""You are checking whether a piece of text scraped from the web is worth remembering as a fact. You did not write it — judge it on its own merits.

TEXT:
{claim[:600]}

Is this coherent, meaningful factual content — not garbled HTML remnants, navigation text, ads, or scraper noise — and does it contain a clear, specific claim rather than vague filler?

Respond in exactly this format:
SUPPORTED: yes or no
CONFIDENCE: a number from 0 to 100
REASON: one sentence explaining your judgment"""


def _parse_verification(raw: str) -> dict:
    supported_match = re.search(r"SUPPORTED:\s*(yes|no)", raw, re.IGNORECASE)
    confidence_match = re.search(r"CONFIDENCE:\s*(\d+)", raw)
    reason_match = re.search(r"REASON:\s*(.+)", raw, re.IGNORECASE)

    if supported_match and confidence_match:
        supported = supported_match.group(1).lower() == "yes"
        confidence = max(0.0, min(1.0, int(confidence_match.group(1)) / 100))
        reasoning = reason_match.group(1).strip()[:300] if reason_match else ""
        return {
            "supported": supported,
            "confidence": confidence,
            "reasoning": reasoning,
            "parsed": True,
        }

    # Unparseable response -- fail toward a moderate discount rather than
    # either fully trusting or permanently blocking all writes on a format
    # hiccup (mirrors deep_research_trigger.py's _parse_critique_confidence
    # default-on-parse-failure pattern).
    return {
        "supported": True,
        "confidence": 0.6,
        "reasoning": "verifier response did not parse -- accepted at a discount",
        "parsed": False,
    }


def verify_claim(
    claim: str, evidence: str, call_llm_fn, claim_kind: str = "web_fact"
) -> dict:
    """
    Runs the independent check and returns
    {"supported": bool, "confidence": float 0-1, "reasoning": str, "parsed": bool}.
    Does not write to memory or log anything itself -- pair with
    gate_confidence(), which does both.
    """
    claim = (claim or "").strip()
    evidence = (evidence or "").strip()
    if not claim:
        return {
            "supported": False,
            "confidence": 0.0,
            "reasoning": "empty claim",
            "parsed": True,
        }

    prompt = _build_prompt(claim, evidence, claim_kind)
    try:
        raw = call_llm_fn(prompt, timeout=VERIFIER_TIMEOUT)
        if isinstance(raw, tuple):  # defensive: log_thinking=True shape
            raw = raw[0]
    except Exception as e:
        raw = ""
        print(f"⚠️ VERIFIER: call_llm error: {e}")

    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL).strip()
    return _parse_verification(raw)


def gate_confidence(
    original_confidence: float,
    verify_result: dict,
    claim: str = "",
    evidence: str = "",
    claim_kind: str = "",
    source: str = "",
) -> Optional[float]:
    """
    Decides whether a claim gets written, and at what confidence, then logs
    the decision (accepted or rejected) to data/verifier_log.db. Returns the
    confidence to store, or None if the write should be skipped entirely.
    """
    supported = verify_result.get("supported", False)
    verifier_confidence = float(verify_result.get("confidence", 0.0))
    accepted = supported and verifier_confidence >= REJECT_FLOOR
    final_confidence = (
        round(min(original_confidence, verifier_confidence), 3) if accepted else None
    )

    _log_verification(
        claim=claim,
        evidence=evidence,
        claim_kind=claim_kind,
        source=source,
        verdict="accepted" if accepted else "rejected",
        verifier_confidence=verifier_confidence,
        original_confidence=original_confidence,
        final_confidence=final_confidence,
        reasoning=verify_result.get("reasoning", ""),
        parsed=verify_result.get("parsed", True),
    )

    return final_confidence
