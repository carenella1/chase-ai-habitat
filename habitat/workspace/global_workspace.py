# =========================
# 🌐 GLOBAL WORKSPACE
# Chase AI Habitat — Milestone A + B
#
# Milestone A: Global broadcast (Baars, 1988 — Global Workspace Theory)
# Milestone B: Active Working Memory Buffer (Baddeley, 1974)
# =========================

import threading
import time
import json
from collections import Counter

# =========================
# 🧠 SALIENCE SCORING
# =========================

SALIENCE_KEYWORDS = [
    "pattern", "system", "conflict", "contradiction", "emergence",
    "network", "feedback", "loop", "structure", "mechanism",
    "theory", "principle", "evidence", "paradox", "discovery",
    "critical", "insight", "fundamental", "breakthrough", "novel"
]

SALIENCE_BOOST_SOURCES = {"wikipedia": 2.0, "web": 1.5, "llm": 1.0}


def compute_salience(insight: str, source: str = "llm", stance: str = "") -> float:
    if not insight:
        return 0.0
    score = 0.0
    length = len(insight)
    if length > 500:
        score += 3.0
    elif length > 300:
        score += 2.0
    elif length > 150:
        score += 1.0
    text_lower = insight.lower()
    keyword_hits = sum(1 for kw in SALIENCE_KEYWORDS if kw in text_lower)
    score += keyword_hits * 0.5
    score += SALIENCE_BOOST_SOURCES.get(source, 1.0)
    if stance in ("CHALLENGE", "REFRAME"):
        score += 1.5
    elif stance == "EXPAND":
        score += 0.5
    if "Claim:" in insight:
        score += 1.0
    if "Insight:" in insight:
        score += 1.0
    return round(score, 2)


# =========================
# 🧠 MILESTONE B — WORKING MEMORY ANALYSIS
# =========================

def analyze_thread(working_memory: list) -> dict:
    """
    Analyze the working memory buffer to extract temporal patterns.
    Returns loop detection, thread direction, dominant topic, stance mix.
    This output gets injected into agent prompts as temporal context.
    """
    if not working_memory:
        return {
            "dominant_topic": None,
            "topic_diversity": 0,
            "stance_distribution": {},
            "loop_detected": False,
            "thread_direction": "empty",
            "cycles_on_topic": 0,
            "agents_active": [],
            "summary": "No working memory yet.",
        }

    topics = [m.get("topic", "") for m in working_memory if m.get("topic")]
    stances = [m.get("stance", "") for m in working_memory if m.get("stance")]
    agents = [m.get("agent", "") for m in working_memory if m.get("agent")]

    topic_counts = Counter(topics)
    stance_counts = Counter(stances)
    dominant_topic = topic_counts.most_common(1)[0][0] if topic_counts else None
    topic_diversity = len(topic_counts)

    # Loop detection: same topic in last 3+ consecutive entries
    cycles_on_topic = 0
    loop_detected = False
    if topics:
        current = topics[-1]
        for t in reversed(topics):
            if t == current:
                cycles_on_topic += 1
            else:
                break
        loop_detected = cycles_on_topic >= 3

    # Thread direction
    if len(working_memory) >= 4:
        mid = len(working_memory) // 2
        first_topics = len(set(m.get("topic", "") for m in working_memory[:mid]))
        second_topics = len(set(m.get("topic", "") for m in working_memory[mid:]))
        if second_topics > first_topics:
            thread_direction = "diverging"
        elif second_topics < first_topics:
            thread_direction = "converging"
        else:
            thread_direction = "stable"
    else:
        thread_direction = "forming"

    stance_str = ", ".join(f"{s}x{c}" for s, c in stance_counts.most_common())

    if loop_detected:
        summary = (
            f"LOOP DETECTED: '{dominant_topic}' dominated {cycles_on_topic} "
            f"consecutive cycles. Shift to a different topic or angle."
        )
    elif thread_direction == "diverging":
        summary = (
            f"Thread diverging across {topic_diversity} topics. "
            f"Consider focusing on '{dominant_topic}'."
        )
    elif thread_direction == "converging":
        summary = (
            f"Thread converging on '{dominant_topic}'. "
            f"Deepen this reasoning."
        )
    else:
        summary = (
            f"{topic_diversity} topics in working memory. "
            f"Dominant: '{dominant_topic}'. Stances: {stance_str}."
        )

    return {
        "dominant_topic": dominant_topic,
        "topic_diversity": topic_diversity,
        "stance_distribution": dict(stance_counts),
        "loop_detected": loop_detected,
        "thread_direction": thread_direction,
        "cycles_on_topic": cycles_on_topic,
        "agents_active": list(set(agents)),
        "summary": summary,
    }


def extract_claim_from_broadcast(content: str) -> str:
    """Extract the Claim or best sentence from a debate response block."""
    if not content:
        return ""
    for marker in ["Claim:", "Insight:", "Response:"]:
        if marker in content:
            after = content.split(marker)[-1].strip()
            first_line = after.split("\n")[0].strip()
            if len(first_line) > 20 and "[" not in first_line:
                return first_line[:180]
    for line in content.split("\n"):
        line = line.strip()
        if (len(line) > 30
                and not line.startswith("---")
                and not line.startswith("Agent:")
                and not line.startswith("Stance:")
                and "[" not in line):
            return line[:180]
    return ""


# =========================
# 🌐 THE GLOBAL WORKSPACE
# =========================

class GlobalWorkspace:
    """
    Milestone A: Shared broadcast blackboard — all agents read/write.
    Milestone B: Active working memory — buffer now influences behavior.

    New in Milestone B:
    - analyze_thread() called after each broadcast
    - Thread analysis injected into agent prompts
    - Loop detection signals agent selection to diversify
    - get_thread_analysis(), should_break_loop(), get_thread_direction()
    """

    SALIENCE_THRESHOLD = 3.0
    WORKING_MEMORY_SIZE = 7  # Miller's Law 7+-2

    def __init__(self):
        self._lock = threading.Lock()

        self._broadcast = {
            "content": None,
            "agent": None,
            "stance": None,
            "topic": None,
            "source": None,
            "salience": 0.0,
            "timestamp": None,
            "cycle": 0,
        }

        self._working_memory = []
        self._thread_analysis = {}
        self._cycle_count = 0
        self._suppression_map = {}
        self._salience_override = False  # When True, accept any salience next broadcast

        print("🌐 GLOBAL WORKSPACE INITIALIZED (Milestone A+B)")

    # =========================
    # 📡 BROADCAST
    # =========================

    def broadcast(self, insight: str, agent: str, stance: str,
                  topic: str, source: str) -> dict:
        salience = compute_salience(insight, source, stance)

        record = {
            "content": insight,
            "agent": agent,
            "stance": stance,
            "topic": topic,
            "source": source,
            "salience": salience,
            "timestamp": int(time.time() * 1000),
            "cycle": self._cycle_count,
            "broadcast": False,
        }

        with self._lock:
            cycles_since_last = self._cycle_count - self._suppression_map.get(topic, -999)
            suppressed = (cycles_since_last < 3) and (topic == self._broadcast.get("topic"))

            # Override: accept any broadcast when forced (duplicate escape)
            force = self._salience_override
            if force:
                self._salience_override = False
                suppressed = False  # lift suppression too
                print("🌐 SALIENCE OVERRIDE ACTIVE — accepting forced broadcast")

            if (salience >= self.SALIENCE_THRESHOLD or force) and not suppressed:
                self._broadcast = {
                    "content": insight,
                    "agent": agent,
                    "stance": stance,
                    "topic": topic,
                    "source": source,
                    "salience": salience,
                    "timestamp": record["timestamp"],
                    "cycle": self._cycle_count,
                }

                self._suppression_map[topic] = self._cycle_count
                self._working_memory.append(dict(self._broadcast))

                if len(self._working_memory) > self.WORKING_MEMORY_SIZE:
                    self._working_memory.pop(0)

                # Milestone B: recompute thread analysis after each broadcast
                self._thread_analysis = analyze_thread(self._working_memory)

                record["broadcast"] = True
                print(f"📡 BROADCAST: [{agent}/{stance}] salience={salience} topic={topic}")
                print(f"🧵 THREAD: {self._thread_analysis.get('summary', '')}")
            else:
                reason = "suppressed" if suppressed else f"low_salience({salience:.1f}<{self.SALIENCE_THRESHOLD})"
                print(f"📻 NOT BROADCAST: [{agent}] {reason}")

        return record

    # =========================
    # 👁️ READ
    # =========================

    def get_broadcast(self) -> dict:
        with self._lock:
            return dict(self._broadcast)

    def get_working_memory(self) -> list:
        with self._lock:
            return list(self._working_memory)

    def get_thread_analysis(self) -> dict:
        """Milestone B: current thread analysis — called by cognition loop."""
        with self._lock:
            return dict(self._thread_analysis)

    # =========================
    # 🔄 CYCLE MANAGEMENT
    # =========================

    def increment_cycle(self):
        with self._lock:
            self._cycle_count += 1
            print(f"🔄 WORKSPACE CYCLE: {self._cycle_count}")
        return self._cycle_count

    def get_cycle(self) -> int:
        with self._lock:
            return self._cycle_count

    # =========================
    # 🧠 CONTEXT INJECTION (Milestone B enhanced)
    # =========================

    def build_context_block(self) -> str:
        """
        Compact context for LLM prompts.
        Milestone B: includes thread summary and loop warning when relevant.
        Kept short to preserve Llama3 format compliance.
        """
        with self._lock:
            broadcast = dict(self._broadcast)
            thread = dict(self._thread_analysis)

        if not broadcast.get("content"):
            return ""

        core = extract_claim_from_broadcast(broadcast.get("content", ""))
        if not core:
            return ""

        topic = broadcast.get("topic", "unknown")
        agent_src = broadcast.get("agent", "?")
        context = f"Prior claim ({agent_src}, topic: {topic}): {core}"

        # Append thread state — only when it carries real signal
        if thread.get("loop_detected"):
            context += f"\nWARNING: {thread.get('summary', '')}"
        elif thread.get("thread_direction") in ("converging", "diverging"):
            context += f"\nThread: {thread.get('summary', '')}"

        return context

    # =========================
    # 🧠 MILESTONE B: BEHAVIORAL SIGNALS
    # Called by the cognition loop to steer agent selection and topic choice
    # =========================

    def should_break_loop(self) -> bool:
        """True if working memory shows a cognitive loop (same topic 3+ cycles)."""
        with self._lock:
            return self._thread_analysis.get("loop_detected", False)

    def get_dominant_topic(self) -> str:
        """Topic that has dominated recent working memory."""
        with self._lock:
            return self._thread_analysis.get("dominant_topic", "")

    def get_thread_direction(self) -> str:
        """'converging' | 'diverging' | 'stable' | 'forming' | 'empty'"""
        with self._lock:
            return self._thread_analysis.get("thread_direction", "empty")

    def get_cycles_on_topic(self) -> int:
        """Consecutive cycles on the current dominant topic."""
        with self._lock:
            return self._thread_analysis.get("cycles_on_topic", 0)

    def get_recommended_stance(self) -> str:
        """
        Milestone B: recommend a stance based on thread state.
        If converging → CHALLENGE to test the idea
        If diverging → EXPAND to build momentum on a thread
        If looping → REFRAME to break the pattern
        """
        with self._lock:
            direction = self._thread_analysis.get("thread_direction", "")
            loop = self._thread_analysis.get("loop_detected", False)
            stances = self._thread_analysis.get("stance_distribution", {})

        if loop:
            return "REFRAME"
        if direction == "converging":
            return "CHALLENGE"
        if direction == "diverging":
            return "EXPAND"
        # Least-used stance for variety
        all_stances = ["SUPPORT", "CHALLENGE", "EXPAND", "REFRAME"]
        if stances:
            return min(all_stances, key=lambda s: stances.get(s, 0))
        return ""

    # =========================
    # 📊 STATUS
    # =========================

    def get_status(self) -> dict:
        with self._lock:
            return {
                "cycle": self._cycle_count,
                "broadcast": dict(self._broadcast),
                "working_memory": list(self._working_memory),
                "salience_threshold": self.SALIENCE_THRESHOLD,
                "suppression_map": dict(self._suppression_map),
                "thread_analysis": dict(self._thread_analysis),
            }

    # =========================
    # 💾 PERSISTENCE
    # =========================

    def save_to_memory(self, memory: dict) -> dict:
        with self._lock:
            memory["global_workspace"] = {
                "broadcast": dict(self._broadcast),
                "working_memory": list(self._working_memory),
                "cycle_count": self._cycle_count,
                "suppression_map": dict(self._suppression_map),
                "thread_analysis": dict(self._thread_analysis),
            }
        return memory

    def restore_from_memory(self, memory: dict):
        ws_data = memory.get("global_workspace", {})
        if not ws_data:
            return

        with self._lock:
            self._broadcast = ws_data.get("broadcast", self._broadcast)
            self._working_memory = ws_data.get("working_memory", [])
            self._cycle_count = ws_data.get("cycle_count", 0)
            self._suppression_map = ws_data.get("suppression_map", {})
            self._thread_analysis = ws_data.get("thread_analysis", {})

            if not self._thread_analysis and self._working_memory:
                self._thread_analysis = analyze_thread(self._working_memory)

        print(f"🌐 WORKSPACE RESTORED: cycle={self._cycle_count}, "
              f"topic={self._broadcast.get('topic', 'none')}, "
              f"thread={self._thread_analysis.get('thread_direction', 'unknown')}")


# =========================
# 🌐 SINGLETON
# =========================
workspace = GlobalWorkspace()