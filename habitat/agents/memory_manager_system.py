"""
memory_manager_system.py

Nexarion's Permanent Memory Management System.

Keeps storage permanently under control while preserving ALL
of Nexarion's accumulated intelligence. Nothing is lost —
raw cognition gets distilled by the synthesizer first, then
pruned. Journals rotate into archives. Goals self-cap.

Three operations run automatically in the brain loop:

1. COGNITION PRUNING (every 500 cycles)
   - Keeps last 300 raw cognition entries in memory.json
   - Everything older has already been synthesized into
     data/knowledge_synthesis.json — the real knowledge lives there
   - Prevents memory.json from growing beyond ~5MB ever

2. JOURNAL ROTATION (when journal exceeds 800 entries)
   - Archives old entries to data/journal_archive_YYYY-MM.jsonl
   - Keeps last 200 entries in the live journal
   - Archives get pushed to GitHub automatically via push.bat
   - Nexarion's private thoughts preserved forever, locally tiny

3. HIGH VALUE INSIGHT CAPPING (every 500 cycles)
   - memory.json high_value_insights array capped at 50 entries
   - These are already stored in SQLite memory.db — no loss

Storage projection with this system active:
   memory.json:          ~2-4MB permanently (was growing to 500MB+)
   journal (live):       ~200KB permanently
   journal (archives):   ~1MB/month, stored on GitHub
   knowledge_synthesis:  ~500KB permanently (the real intelligence)
   memory.db (SQLite):   self-managing, ~20MB cap
   Total local:          ~30MB permanently regardless of runtime

"""

import json
import os
import time
import shutil


MEMORY_FILE = "memory.json"
JOURNAL_FILE = "data/nexarion_journal.jsonl"

# How many raw cognition entries to keep after pruning
COGNITION_KEEP = 300

# How many journal entries before rotation triggers
JOURNAL_ROTATION_THRESHOLD = 800

# How many journal entries to keep after rotation
JOURNAL_KEEP_AFTER_ROTATION = 200

# Max high_value_insights in memory.json
HIGH_VALUE_CAP = 50


def prune_cognition_history(memory: dict, current_cycle: int) -> tuple[dict, bool]:
    """
    Trim cognition_history to the most recent COGNITION_KEEP entries.
    Safe to call at any time — the knowledge synthesizer has already
    distilled older entries into structured domain knowledge.
    Returns (updated_memory, was_pruned).
    """
    history = memory.get("cognition_history", [])
    original_len = len(history)

    if original_len <= COGNITION_KEEP:
        return memory, False

    # Keep only the most recent entries
    memory["cognition_history"] = history[-COGNITION_KEEP:]
    pruned = original_len - COGNITION_KEEP

    print(
        f"🧹 COGNITION PRUNED: {original_len} → {COGNITION_KEEP} entries "
        f"({pruned} raw entries removed, knowledge preserved in synthesis)"
    )

    return memory, True


def prune_high_value_insights(memory: dict, current_cycle: int) -> tuple[dict, bool]:
    """
    Cap high_value_insights at HIGH_VALUE_CAP entries.
    These are also stored in SQLite memory.db — no loss.
    """
    insights = memory.get("high_value_insights", [])
    if len(insights) <= HIGH_VALUE_CAP:
        return memory, False

    original_len = len(insights)
    memory["high_value_insights"] = insights[-HIGH_VALUE_CAP:]
    print(f"🧹 HIGH VALUE INSIGHTS CAPPED: {original_len} → {HIGH_VALUE_CAP}")
    return memory, True


def rotate_journal(current_cycle: int) -> bool:
    """
    Rotate the journal file when it gets too large.
    Old entries archived to data/journal_archive_YYYY-MM.jsonl
    Recent entries kept in the live journal.
    Returns True if rotation happened.
    """
    if not os.path.exists(JOURNAL_FILE):
        return False

    try:
        with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
            lines = [l for l in f.readlines() if l.strip()]

        if len(lines) < JOURNAL_ROTATION_THRESHOLD:
            return False

        # Archive filename by month
        archive_name = f"data/journal_archive_{time.strftime('%Y-%m')}.jsonl"
        lines_to_archive = lines[:-JOURNAL_KEEP_AFTER_ROTATION]
        lines_to_keep = lines[-JOURNAL_KEEP_AFTER_ROTATION:]

        # Append to archive (may already exist from earlier this month)
        os.makedirs("data", exist_ok=True)
        with open(archive_name, "a", encoding="utf-8") as f:
            f.writelines(lines_to_archive)

        # Rewrite live journal with just recent entries
        with open(JOURNAL_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines_to_keep)

        print(f"📚 JOURNAL ROTATED: {len(lines_to_archive)} entries → {archive_name}")
        print(f"📚 JOURNAL LIVE: {len(lines_to_keep)} entries remaining")
        return True

    except Exception as e:
        print(f"⚠️ Journal rotation error: {e}")
        return False


def prune_topic_scores(memory: dict) -> tuple[dict, bool]:
    """
    Clean up topic_scores — remove entries below 0.5 and cap at 30 topics.
    Prevents topic score bloat over time.
    """
    scores = memory.get("topic_scores", {})
    original = len(scores)

    # Remove very low scores
    cleaned = {k: v for k, v in scores.items() if v >= 0.5}

    # Sort and keep top 30
    sorted_scores = dict(sorted(cleaned.items(), key=lambda x: x[1], reverse=True)[:30])

    if len(sorted_scores) < original:
        memory["topic_scores"] = sorted_scores
        print(f"🧹 TOPIC SCORES CLEANED: {original} → {len(sorted_scores)} topics")
        return memory, True

    return memory, False


def prune_topic_history(memory: dict) -> tuple[dict, bool]:
    """Keep only the last 200 topic history entries."""
    history = memory.get("topic_history", [])
    if len(history) <= 200:
        return memory, False
    memory["topic_history"] = history[-200:]
    return memory, True


def prune_goal_progress(goals_file: str = "data/persistent_goals.json") -> bool:
    """
    Cap progress_entries in the active goal at 100 entries.
    Key findings are already capped at 20 in persistent_goals.py.
    """
    if not os.path.exists(goals_file):
        return False
    try:
        with open(goals_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        active = data.get("active")
        if not active:
            return False

        entries = active.get("progress_entries", [])
        if len(entries) <= 100:
            return False

        active["progress_entries"] = entries[-100:]
        data["active"] = active

        with open(goals_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"🧹 GOAL PROGRESS CAPPED: kept last 100 of {len(entries)} entries")
        return True
    except Exception as e:
        print(f"⚠️ Goal progress pruning error: {e}")
        return False


def get_storage_report() -> dict:
    """
    Return a dict describing current storage usage of key files.
    Used by /api/storage/status endpoint.
    """
    files = {
        "memory.json": MEMORY_FILE,
        "journal": JOURNAL_FILE,
        "knowledge_synthesis": "data/knowledge_synthesis.json",
        "memory_db": "data/memory.db",
        "goals": "data/persistent_goals.json",
        "research_sessions": "data/research_sessions.jsonl",
        "contradictions": "contradictions.json",
    }

    report = {}
    total_bytes = 0

    for name, path in files.items():
        if os.path.exists(path):
            size = os.path.getsize(path)
            total_bytes += size
            report[name] = {
                "path": path,
                "size_kb": round(size / 1024, 1),
                "size_mb": round(size / 1024 / 1024, 2),
            }
        else:
            report[name] = {"path": path, "size_kb": 0, "size_mb": 0}

    # Count journal archives
    archive_total = 0
    archive_count = 0
    for f in os.listdir("data") if os.path.exists("data") else []:
        if f.startswith("journal_archive_"):
            size = os.path.getsize(os.path.join("data", f))
            archive_total += size
            archive_count += 1

    report["journal_archives"] = {
        "count": archive_count,
        "size_kb": round(archive_total / 1024, 1),
        "size_mb": round(archive_total / 1024 / 1024, 2),
    }

    report["total_mb"] = round(total_bytes / 1024 / 1024, 2)
    return report


def run_full_maintenance(memory: dict, current_cycle: int) -> dict:
    """
    Run all maintenance operations. Called from the brain loop.
    Returns the (possibly modified) memory dict.
    Safe — wrapped in try/except, never crashes the brain loop.
    """
    try:
        any_changed = False

        memory, changed = prune_cognition_history(memory, current_cycle)
        any_changed = any_changed or changed

        memory, changed = prune_high_value_insights(memory, current_cycle)
        any_changed = any_changed or changed

        memory, changed = prune_topic_scores(memory)
        any_changed = any_changed or changed

        memory, changed = prune_topic_history(memory)
        any_changed = any_changed or changed

        # Journal rotation (checks its own threshold internally)
        rotate_journal(current_cycle)

        # Goal progress pruning
        prune_goal_progress()

        if any_changed:
            print(
                f"🧹 MAINTENANCE COMPLETE (cycle {current_cycle}) — "
                f"storage optimized"
            )

        # Log storage report every 1000 cycles
        if current_cycle % 1000 == 0:
            report = get_storage_report()
            print(f"💾 STORAGE REPORT: {report['total_mb']}MB total")
            for name, info in report.items():
                if name != "total_mb" and info.get("size_kb", 0) > 0:
                    print(f"   {name}: {info['size_kb']}KB")

    except Exception as e:
        print(f"⚠️ MAINTENANCE ERROR: {e}")

    return memory
