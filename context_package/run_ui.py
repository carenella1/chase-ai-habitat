# =========================
# IMPORTS
# =========================
from habitat.knowledge.knowledge_manager import (
    add_knowledge_entry,
    search_knowledge,
    get_recent_knowledge,
)

import json
import os
import threading
import time
import base64
import traceback
import random

import requests
from flask import Flask, render_template, jsonify, request
from elevenlabs.client import ElevenLabs

from scripts.run_core_loop import CoreLoop
from habitat.memory.memory_manager import MemoryManager


# =========================
# 🧠 TOPIC EXTRACTION
# =========================
def extract_topic_from_insight(insight):
    if not insight:
        return ""

    words = [w.strip(".,:;!?()[]{}").lower() for w in insight.split()]

    # 🔥 remove junk tokens
    words = [w for w in words if w not in {"insight", "lets", "here", "based", "using"}]

    STOPWORDS = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "is",
        "are",
        "this",
        "that",
        "here",
        "there",
        "what",
        "when",
        "where",
        "why",
        "how",
        "new",
        "idea",
        "insight",
        "concept",
        "approach",
        "system",
    }

    filtered = [w for w in words if len(w) > 4 and w.lower() not in STOPWORDS]

    if len(filtered) >= 2:
        return " ".join(filtered[:2])

    if len(words) >= 2:
        return " ".join(words[:2])

    return " ".join(words[:3])


# =========================
# APP INIT
# =========================
app = Flask(__name__, static_folder="static", template_folder="templates")

MEMORY_FILE = "memory.json"
IDENTITY_FILE = "identity.txt"


# =========================
# 🔊 VOICE
# =========================
client = ElevenLabs(api_key="YOUR_API_KEY_HERE")


def generate_voice(text):
    try:
        audio_stream = client.text_to_speech.convert(
            text=text,
            voice_id="EXAVITQu4vr4xnSDxMaL",
            model_id="eleven_multilingual_v2",
        )
        audio_bytes = b"".join(audio_stream)
        return base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else ""
    except Exception:
        return ""


# =========================
# 🧱 CORE UTIL
# =========================
def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2)


def load_identity():
    if not os.path.exists(IDENTITY_FILE):
        return ""
    with open(IDENTITY_FILE, "r", encoding="utf-8") as f:
        return f.read()


def ensure_memory(memory):
    memory.setdefault("cognition_history", [])
    memory.setdefault("agents", [])
    memory.setdefault("topic_interest", {})
    memory.setdefault("topic_scores", {})
    memory.setdefault("topic_history", [])
    memory.setdefault("high_value_insights", [])
    # 🧠 NEW
    memory.setdefault("active_goal", None)
    memory.setdefault("goal_progress", [])
    return memory


TOPIC_ALIASES = {
    "ai": "artificial intelligence",
    "artificial intelligence": "artificial intelligence",
    "machine learning": "artificial intelligence",
    "ml": "artificial intelligence",
    "llm": "large language models",
    "llms": "large language models",
    "language model": "large language models",
    "language models": "large language models",
    "agents": "agent systems",
    "agent": "agent systems",
    "multi-agent": "agent systems",
    "automation": "automation",
    "systems": "systems design",
    "system": "systems design",
    "architecture": "systems design",
}


def normalize_topic_name(topic):
    if not topic:
        return ""

    t = str(topic).strip().lower()

    # normalize plurals (basic)
    if t.endswith("s"):
        t = t[:-1]

    # clean junk formatting
    t = t.replace("*", "").replace('"', "").replace("'", "")
    t = " ".join(t.split())

    # 🔥 REMOVE BAD LLM TAILS
    if "this title" in t:
        t = t.split("this title")[0]

    if "this" in t:
        t = t.split("this")[0]

    t = t.strip()

    # apply alias mapping LAST
    return TOPIC_ALIASES.get(t, t)


def extract_topic_candidates(text, limit=5):
    if not text:
        return []

    stopwords = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "is",
        "are",
        "this",
        "that",
        "here",
        "there",
        "what",
        "when",
        "where",
        "why",
        "how",
        "from",
        "into",
        "over",
        "under",
        "about",
        "idea",
        "insight",
        "concept",
        "approach",
        "system",
    }

    words = [w.strip(".,:;!?()[]{}").lower() for w in text.split()]

    words = [w for w in words if len(w) > 4 and w not in stopwords]

    seen = []
    for w in words:
        if w not in seen:
            seen.append(w)

    return seen[:limit]


def normalize_topic(topic):
    if not topic:
        return None

    t = str(topic).lower().strip()
    # ✂️ HARD CUT AT FIRST SENTENCE SIGNAL
    for sep in [".", "there is", "this is", "which", "that"]:
        if sep in t:
            t = t.split(sep)[0]

    # 🚫 HARD KILL LLM PHRASES
    if any(
        x in t
        for x in [
            "its a well-known",
            "this is a",
            "there is",
            "existing topic",
        ]
    ):
        return None

    # 🔥 normalize plurals
    if t.endswith("s"):
        t = t[:-1]

    # ✂️ trim length
    if len(t) > 40:
        t = t[:40]

    # ✂️ split punctuation only
    for sep in [".", ","]:
        if sep in t:
            t = t.split(sep)[0]

    # remove filler words
    stop_words = ["this", "that", "there", "is", "a", "the"]
    words = [w for w in t.split() if w not in stop_words]

    if not words:
        return None

    # 🚫 trailing prepositions
    if words[-1] in ("in", "of", "for", "to", "with"):
        return None

    # limit to 3 words
    t = " ".join(words[:3])

    # 🧠 COLLAPSE EXTENSIONS
    words = t.split()

    if len(words) > 2:
        t = " ".join(words[:2])

    return t.strip()


def update_topic_scores(memory, insight, search_term, source):
    # 🚫 HARD FILTER (LLM GARBAGE)
    INVALID_TOPIC_PATTERNS = [
        "its a",
        "it is",
        "this is",
        "there is",
        "i ",
        "apologize",
        "misunderstanding",
        "response",
        "agent",
        "stance",
    ]

    def is_valid_topic(topic):
        t = topic.lower().strip()
        if t in {"general", "claim", "supporting"}:
            return False

        if not topic:
            return False

        # 🚫 kill obvious garbage
        if len(t) < 4:
            return False

        if t.startswith("its"):
            return False

        if t.startswith("it is"):
            return False
        if any(x in t for x in ["taking", "refer", "spectrum"]):
            return False
        if any(
            x in t
            for x in [
                "well-known",
                "response",
                "agent",
                "stance",
                "apologize",
                "misunderstanding",
            ]
        ):
            return False

        # 🚫 must contain at least one meaningful word
        words = t.split()
        if len(words) == 1 and len(words[0]) < 5:
            return False

        return True

    memory = ensure_memory(memory)

    topic_scores = memory.setdefault("topic_scores", {})
    # =========================
    # 🧹 CLEAN EXISTING TOPICS (CRITICAL)
    # =========================

    cleaned_scores = {}

    for topic, score in topic_scores.items():
        normalized = normalize_topic(topic)

        if not normalized or not is_valid_topic(normalized):
            continue

        cleaned_scores[normalized] = cleaned_scores.get(normalized, 0) + score

    topic_scores.clear()
    topic_scores.update(cleaned_scores)
    # =========================
    # 🧹 DROP LOW-VALUE TOPICS
    # =========================

    topic_scores.clear()
    topic_scores.update(
        {k: v for k, v in cleaned_scores.items() if v > 0.5}
    )  # threshold
    topic_history = memory.setdefault("topic_history", [])

    # =========================
    # 🧠 LIMIT TOTAL TOPICS
    # =========================

    MAX_TOPICS = 25

    sorted_topics = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)

    topic_scores.clear()
    topic_scores.update(dict(sorted_topics[:MAX_TOPICS]))

    # 🚫 BLOCKED TOPICS (ADD HERE)
    BLOCKED_TOPICS = {
        "researcher",
        "explorer",
        "strategist",
        "archivist",
        "builder",
        "curator",
        "insight",
        "idea",
        "response",
    }
    # 🧠 TOPIC FATIGUE (ADD THIS HERE)
    for k in topic_scores:
        topic_scores[k] *= 0.97
        print(f"🧠 DECAY: {k} → {topic_scores[k]:.2f}")

    primary = normalize_topic(search_term)

    if primary:
        primary = primary.split("this title")[0].strip()

    # 🚫 filter bad topics (SAFE)
    if not primary:
        primary = None
    else:
        if primary in BLOCKED_TOPICS:
            primary = None

        elif len(primary.split()) > 5:
            primary = " ".join(primary.split()[:3])

        if primary and is_valid_topic(primary):
            topic_scores[primary] = topic_scores.get(primary, 0) + 1.5
            topic_history.append(primary)

    for candidate in extract_topic_candidates(insight, limit=3):

        # 🔥 NORMALIZE FIRST (THIS WAS MISSING)
        candidate = normalize_topic(candidate)

        # 🚫 skip invalid after normalization
        if not candidate or not is_valid_topic(candidate):
            continue

        # 🚫 skip blocked topics
        if any(bad in candidate for bad in BLOCKED_TOPICS):
            continue

        topic_scores[candidate] = topic_scores.get(candidate, 0) + 1
        topic_history.append(candidate)

    if source == "wikipedia" and primary:
        topic_scores[primary] = topic_scores.get(primary, 0) + 1
        # 🧠 HARD CAP (prevents runaway topics)
        for k in topic_scores:
            if topic_scores[k] > 120:
                topic_scores[k] *= 0.9

    memory["topic_history"] = topic_history[-100:]
    return memory


def get_top_topics(memory, limit=5):
    memory = ensure_memory(memory)
    scores = memory.get("topic_scores", {})
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return ranked[:limit]


# =========================
# 🧠 BELIEF EXTRACTION
# =========================
def extract_belief_statement(insight):
    if not insight:
        return None

    lines = insight.split("\n")

    for line in lines:
        if "Claim:" in line:
            claim = line.split("Claim:")[-1].strip()
            return claim[:200]

    # fallback → use insight
    if "Insight:" in insight:
        text = insight.split("Insight:")[-1].strip()
        return text[:200]

    return None


def find_matching_belief(memory_manager, statement):
    beliefs = memory_manager.get_all_beliefs(limit=20)

    for b in beliefs:
        existing = b["statement"].lower()
        incoming = statement.lower()

        # simple overlap match
        if incoming in existing or existing in incoming:
            return b

    return None


# =========================
# 🧠 SERVICE LAYER
# =========================
def extract_clean_insight_text(insight):
    if not insight:
        return ""

    if "Insight:" in insight:
        text = insight.split("Insight:")[-1]
    else:
        text = insight

    # remove structure junk
    text = text.replace("--- Debate Response ---", "")
    text = text.replace("Agent:", "")
    text = text.replace("Stance:", "")
    text = text.replace("Claim:", "")
    text = text.replace("Response:", "")

    return text.strip()[:200]


def get_cognition_entries():
    memory = load_memory()  # 🔥 DO NOT reuse cached memory
    memory = ensure_memory(memory)
    entries = memory.get("cognition_history", [])[-30:]
    entries = sorted(entries, key=lambda x: x.get("timestamp", 0))
    entries = entries[-30:]

    # newest first
    entries = sorted(entries, key=lambda x: x.get("timestamp", 0), reverse=True)

    return entries[:50]


def add_cognition_entry(entry):
    memory = ensure_memory(load_memory())  # 🔥 FORCE FRESH LOAD

    history = memory.get("cognition_history", [])
    history.append(entry)

    memory["cognition_history"] = history

    save_memory(memory)

    print(f"🧠 TOTAL STORED: {len(history)}")


def get_agents_data():
    memory = ensure_memory(load_memory())
    agents = memory.get("agents", [])

    if not agents:
        agents = [
            {"name": "Researcher", "status": "idle"},
            {"name": "Builder", "status": "idle"},
            {"name": "Archivist", "status": "idle"},
            {"name": "Explorer", "status": "idle"},
            {"name": "Strategist", "status": "idle"},
        ]

    return agents


# =========================
# 🧠 LLM
# =========================
def call_llm(prompt):
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "llama3:latest", "prompt": prompt, "stream": False},
            timeout=60,
        )
        return response.json().get("response", "")
    except:
        return "LLM unavailable."


def generate_search_topic(insight):
    if not insight:
        return ""

    prompt = f"""
Convert the following concept into a REAL Wikipedia article title.

STRICT RULES:
- Must be a well-known, existing topic
- Use simple, common terms
- 1–3 words ONLY
- NO creative phring
- Prefer broad topics

Concept:
{insight}
"""

    # ✅ CALL LLM
    topic = call_llm(prompt)

    # ✅ SAFE FALLBACK
    if not topic or len(topic.strip()) == 0:
        topic = extract_topic_from_insight(insight)

    # ✅ CLEAN ONCE (NOT 5 TIMES)
    topic = topic.replace("*", "")
    topic = topic.replace('"', "")
    topic = topic.replace("'", "")
    topic = topic.strip()

    # ✅ FINAL SAFETY
    if not topic:
        topic = extract_topic_from_insight(insight)

    return topic


# =========================
# 🌐 WIKI
# =========================
def fetch_wikipedia_summary(query):
    try:
        from urllib.parse import quote

        if not query:
            return None

        encoded_query = quote(query)
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_query}"

        headers = {"User-Agent": "Chase-AI-Habitat/1.0"}

        res = requests.get(url, headers=headers, timeout=5)

        if res.status_code != 200:
            return None

        data = res.json()

        if data.get("type") == "disambiguation":
            return None

        return data.get("extract")

    except:
        return None


# =========================
# 📄 ROUTES
# =========================
@app.route("/")
@app.route("/chat")
def chat_page():
    return render_template("chat.html", active="chat")


@app.route("/habitat")
def habitat_page():
    return render_template("habitat.html", active="habitat")


@app.route("/agents")
def agents_page():
    return render_template("agents.html", active="agents")


@app.route("/api/cognition/all")
def api_cognition_all():
    memory = ensure_memory(load_memory())

    entries = get_cognition_entries()  # ✅ THIS WAS MISSING

    top_topics = get_top_topics(memory, limit=5)
    synthesis = memory.get("last_synthesis", [])
    high_value = memory.get("high_value_insights", [])[-5:]

    return jsonify(
        {
            "entries": entries,
            "top_topics": top_topics,
            "synthesis": synthesis,
            "memory": high_value,
        }
    )


@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        data = request.get_json() or {}
        msg = data.get("message", "")

        identity = load_identity()
        memory = ensure_memory(load_memory())

        prompt = f"""
Identity:
{identity}

Recent Memory:
{json.dumps(memory["cognition_history"][-5:], indent=2)}

User:
{msg}
"""

        output = call_llm(prompt)

        add_cognition_entry(
            {"timestamp": int(time.time() * 1000), "input": msg, "output": output}
        )

        return jsonify({"response": output})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"response": str(e)})


# =========================
# 🏗️ BUILDER API (RESTORE THIS)
# =========================


@app.route("/api/build/pending", methods=["GET"])
def api_build_pending():
    memory = ensure_memory(load_memory())
    history = get_cognition_entries()[:10]

    proposals = []
    seen = set()

    for entry in history:
        c = entry.get("cognition", {})

        insight = c.get("insight")
        research = c.get("research", "")
        source = c.get("source", "llm")

        if not insight:
            continue

        confidence = 0.9 if source == "wikipedia" else 0.6

        sig = insight[:80]
        if sig in seen:
            continue
        seen.add(sig)

        clean = extract_clean_insight_text(insight)

        proposals.append(
            {
                "id": hash(sig),
                "description": f"Act on: {clean}",
                "reason": "Generated from cognition",
                "impact": (
                    research[:120] if research else "Potential system improvement"
                ),
                "confidence": confidence,
                "importance": len(insight) + (confidence * 100),
            }
        )

    proposals = sorted(proposals, key=lambda x: x["importance"], reverse=True)

    return jsonify({"status": "ok", "data": {"pending": proposals[:3]}})


def simplify_query_for_wikipedia(query):
    if not query:
        return ""

    # remove quotes + cleanup
    q = query.replace('"', "").replace("'", "").strip()

    # remove filler words (THIS IS KEY)
    STOPWORDS = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "is",
        "are",
        "this",
        "that",
        "here",
    }

    words = [w for w in q.split() if w.lower() not in STOPWORDS]

    # prioritize meaningful words
    if len(words) >= 3:
        return " ".join(words[:3])

    return " ".join(words[:2]) if words else q[:50]


# =========================
# 🧠 AGENT SELECTION
# =========================
def select_agent():
    agents = ["Researcher", "Builder", "Archivist", "Explorer", "Strategist"]
    return random.choice(agents)


# =========================
# 🧠 BACKGROUND BRAIN THREAD
# =========================
def is_similar(a, b):
    if not a or not b:
        return False

    a_words = set(a.lower().split())
    b_words = set(b.lower().split())

    overlap = len(a_words & b_words)
    similarity = overlap / max(len(a_words), 1)

    return similarity > 0.6


def score_agents(memory, history):
    scores = {
        "Researcher": 0,
        "Explorer": 0,
        "Strategist": 0,
        "Curator": 0,
        "Archivist": 0,
        "Builder": 0,
    }

    recent = history[-5:]

    recent_agents = [
        h.get("cognition", {}).get("agent") for h in recent if h.get("cognition")
    ]

    recent_text = " ".join(
        h.get("cognition", {}).get("insight", "") for h in recent
    ).lower()

    top_topics = get_top_topics(memory, limit=3)

    # 🧠 RULES

    # Avoid repeating same agent
    if recent_agents:
        scores[recent_agents[-1]] -= 3

    # Researcher → if topics are weak
    if len(top_topics) < 2:
        scores["Researcher"] += 3

    # Explorer → if repetition detected
    if "duplicate" in recent_text:
        scores["Explorer"] += 2

    # Strategist → if patterns forming
    if len(set(recent_agents)) > 2:
        scores["Strategist"] += 2

    # Curator → if too many insights
    if len(history) % 5 == 0:
        scores["Curator"] += 3

    # Archivist → if long memory exists
    if len(history) > 20:
        scores["Archivist"] += 2

    # Builder → if strong topics exist
    if top_topics:
        scores["Builder"] += 1

    return scores


# =========================
# 🧠 DEBATE MODE
# =========================

STANCES = ["SUPPORT", "CHALLENGE", "EXPAND", "REFRAME"]

AGENT_STANCE_TENDENCIES = {
    "Researcher": ["SUPPORT", "EXPAND"],
    "Explorer": ["EXPAND", "REFRAME"],
    "Strategist": ["CHALLENGE", "REFRAME"],
    "Archivist": ["REFRAME", "SUPPORT"],
    "Builder": ["EXPAND", "SUPPORT"],
    "Curator": ["REFRAME", "CHALLENGE"],
}


def select_stance(agent):
    options = AGENT_STANCE_TENDENCIES.get(agent, STANCES)
    return random.choice(options)


def enforce_structure(agent, stance, text):
    if "--- Debate Response ---" in text:
        return text.strip()

    print("⚠️ FORCING STRUCTURED REWRITE")

    short = text.strip().split("\n")[0][:200]

    return f"""
--- Debate Response ---
Agent: {agent}
Stance: {stance}

Claim:
{short}

Response:
Refinement needed due to malformed output.

Insight:
System enforced structured cognition output.
"""


def run():
    print("🧠 BRAIN THREAD STARTED")
    memory_manager = MemoryManager()
    synthesis_context = ""
    synthesis_pairs = []
    while True:
        try:
            # =========================
            # 🧠 MEMORY CONTEXT (SAFE INIT)
            # =========================

            memory_context = ""
            recent_memories = []
            topic_memories = []
            print("🧠 RUNNING CORE CYCLE")

            memory = ensure_memory(load_memory())
            # =========================
            # 🎯 GOAL INITIALIZATION
            # =========================
            if not memory.get("active_goal"):
                top_topics = get_top_topics(memory, limit=1)

                if top_topics:
                    memory["active_goal"] = (
                        f"Deepen understanding of {top_topics[0][0]}"
                    )
                else:
                    memory["active_goal"] = "Explore emerging ideas"

                print(f"🎯 NEW GOAL SET: {memory['active_goal']}")
                save_memory(memory)

            history = memory.get("cognition_history", [])
            top_topics = get_top_topics(memory, limit=3)
            top_topic_names = [t[0] for t in top_topics]
            topic_context = (
                ", ".join(top_topic_names) if top_topic_names else "none yet"
            )
            recent_entries = history[-5:]

            recent_insights = [
                e.get("cognition", {}).get("insight", "")
                for e in recent_entries
                if e.get("cognition")
            ]

            recent_agents = [
                e.get("cognition", {}).get("agent", "") for e in recent_entries
            ]

            prev_insight = None
            prev_agent = None

            if history:
                prev = history[-1].get("cognition", {})
                prev_insight = prev.get("insight")
                prev_agent = prev.get("agent")

            # =========================
            # 🧠 AGENT SELECTION
            # =========================
            scores = score_agents(memory, history)

            # pick highest scoring agent
            agent = max(scores, key=scores.get)

            reinforcement = memory.get("reinforcement", {})

            for topic, score in reinforcement.items():
                if "research" in topic:
                    scores["Researcher"] += score * 0.05
                if "pattern" in topic or "system" in topic:
                    scores["Strategist"] += score * 0.05
                if "idea" in topic or "novel" in topic:
                    scores["Explorer"] += score * 0.05

            print(f"🧠 AGENT SCORES: {scores}")
            print(f"🎯 SELECTED AGENT: {agent}")
            print(f"🤖 ACTIVE AGENT: {agent}")
            stance = select_stance(agent)
            print(f"⚔️ STANCE: {stance}")

            # =========================
            # 🧠 PROMPT
            # =========================
            recent_memories = memory_manager.get_high_value_memories(5)

            memory_context = ""

            if recent_memories:
                memory_context = "Relevant past insights:\n"
                for m in recent_memories:
                    summary = m.get("summary", "")
                    if summary:
                        memory_context += f"- {summary}\n"

            goal = memory.get("active_goal", "No goal")
            context_block = "\n\n".join(recent_insights[-3:])

            recent_context = "\n\n".join(
                h.get("cognition", {}).get("insight", "")
                for h in history[-3:]
                if h.get("cognition", {}).get("insight")
            )
            prompt = ""
            debate_context = ""

            if prev_insight:
                debate_context = f"""
            Previous Insight:
            {prev_insight[:300]}

            Previous Agent:
            {prev_agent}
            """

            prompt = f"""
            You are {agent}.

            You produce sharp, structured reasoning.

            STANCE: {stance}

            Context:
            Topics: {topic_context}
            Goal: {goal}

            Previous:
            {prev_insight[:300] if prev_insight else "None"}

            Rules:
            - No introductions
            - No phrases like "as the agent"
            - No apologies
            - No filler
            - Max 2 sentences per section
            - Be direct and assertive

            Stance behavior:
            SUPPORT → strengthen
            CHALLENGE → attack weaknesses
            EXPAND → extend idea
            REFRAME → reinterpret idea

            OUTPUT:

            --- Debate Response ---
            Agent: {agent}
            Stance: {stance}

            Claim:
            [1 sentence max]

            Response:
            [1-2 sentences max]

            Insight:
            [1-2 sentences max]
            """
            # =========================
            # 🧠 MEMORY CONTEXT INJECTION
            # =========================

            recent_memories = memory_manager.get_high_value_memories(5)
            print("\n🧠 MEMORY DEBUG:")
            for m in recent_memories:
                print(f"importance={m.get('importance')} | {m.get('summary')}")
            print("\n")

            memory_context = ""

            if recent_memories:
                print("🧠 USING MEMORY CONTEXT")

                memory_context = "Relevant past insights:\n"

                for m in recent_memories:
                    summary = m.get("summary", "")
                    if summary:
                        memory_context += f"- {summary}\n"

            # =========================
            # 🧠 LLM CALL
            # =========================

            insight = call_llm(prompt)

            # =========================
            # 🧠 FORCE STRUCTURE
            # =========================

            insight = enforce_structure(agent, stance, insight)

            # =========================
            # 🧠 REMOVE META LANGUAGE
            # =========================

            BAD_PATTERNS = [
                "I apologize",
                "as the",
                "I will",
                "Here is",
                "my response",
                "as an",
            ]

            for bad in BAD_PATTERNS:
                if bad.lower() in insight.lower():
                    print("⚠️ STRIPPING META LANGUAGE")
                    insight = insight.replace(bad, "")

            # =========================
            # 🧠 HARD TRIM
            # =========================

            insight = insight.strip()

            if len(insight) > 800:
                insight = insight[:800]

            # =========================
            # 🧠 HARD COMPRESSION
            # =========================

            lines = insight.split("\n")
            compressed = []

            for line in lines:
                if len(line) > 120:
                    line = line[:120]
                compressed.append(line)

                # 🧠 LIMIT TOTAL SIZE HARDER
            if len(insight) > 500:
                insight = insight[:500]

            insight = "\n".join(compressed)

            # =========================
            # 🎯 GOAL PROGRESS SCORING
            # =========================

            goal = memory.get("active_goal", "")
            progress_score = 0

            if goal and insight:
                goal_words = goal.lower().split()
                insight_text = insight.lower()

                matches = sum(1 for w in goal_words if w in insight_text)
                progress_score = matches / max(len(goal_words), 1)

            print(f"📈 GOAL PROGRESS: {round(progress_score, 2)}")
            # =========================
            # 💾 STORE GOAL PROGRESS
            # =========================
            memory = ensure_memory(load_memory())

            progress_log = memory.get("goal_progress", [])

            progress_log.append(
                {
                    "timestamp": int(time.time() * 1000),
                    "agent": agent,
                    "score": progress_score,
                }
            )

            memory["goal_progress"] = progress_log[-50:]

            save_memory(memory)

            # =========================
            # 🧠 GOAL FEEDBACK SIGNAL
            # =========================
            if progress_score < 0.2:
                print("⚠️ LOW GOAL ALIGNMENT → exploration needed")

            elif progress_score > 0.6:
                print("🔥 HIGH GOAL ALIGNMENT → reinforcing direction")

            # =========================
            # 🌐 TOPIC + WIKI
            # =========================
            search_term_raw = generate_search_topic(insight)

            # 🔥 STEP 1 — trim junk FIRST
            search_term = search_term_raw.split(":")[-1].strip()
            search_term = search_term[:80]

            # 🔥 STEP 2 — normalize AFTER cleaning (CRITICAL)
            search_term = normalize_topic_name(search_term)

            print(f"🧠 CLEANED TOPIC: {search_term}")

            wiki = fetch_wikipedia_summary(search_term)

            if wiki:
                research = wiki
                source = "wikipedia"
            else:
                research = ""
                source = "llm"

            # =========================
            # 🔁 DUPLICATE CHECK
            # =========================
            recent_insights = [
                h.get("cognition", {}).get("insight", "") for h in history[-10:]
            ]

            if any(is_similar(prev, insight) for prev in recent_insights):
                print("⚠️ duplicate detected — forcing variation")

                insight += f"\n\n[Variation {int(time.time())}]"

            # =========================
            # 💾 STORE ENTRY
            # =========================
            if len(insight) > 2000:
                insight = insight[:2000]

            new_entry = {
                "timestamp": int(time.time() * 1000),
                "cognition": {
                    "agent": agent,
                    "insight": insight,
                    "research": research,
                    "source": source,
                },
            }

            add_cognition_entry(new_entry)
            print("📡 FEED ENTRY STORED")

            # =========================
            # 🧠 BELIEF ENGINE (NEW)
            # =========================

            belief_statement = extract_belief_statement(insight)

            if belief_statement:
                existing_belief = find_matching_belief(memory_manager, belief_statement)

                if not existing_belief:
                    # 🆕 CREATE BELIEF
                    belief_id = memory_manager.create_belief(
                        statement=belief_statement, agent=agent, confidence=0.6
                    )

                    print(f"🧠 NEW BELIEF: {belief_statement}")

                else:
                    belief_id = existing_belief["belief_id"]

                    # =========================
                    # ⚔️ BELIEF UPDATE LOGIC
                    # =========================

                    if stance == "SUPPORT":
                        memory_manager.update_belief_confidence(
                            belief_id, +0.05, reason="support"
                        )
                        memory_manager.add_evidence(
                            belief_id, insight[:200], "supporting"
                        )

                    elif stance == "CHALLENGE":
                        memory_manager.update_belief_confidence(
                            belief_id, -0.08, reason="challenge"
                        )
                        memory_manager.add_evidence(
                            belief_id, insight[:200], "contradicting"
                        )

                    elif stance == "EXPAND":
                        memory_manager.update_belief_confidence(
                            belief_id, +0.03, reason="expansion"
                        )
                        memory_manager.add_evidence(
                            belief_id, insight[:200], "supporting"
                        )

                    elif stance == "REFRAME":
                        memory_manager.update_belief_confidence(
                            belief_id, -0.02, reason="reframe"
                        )

                    print(f"🧠 BELIEF UPDATED (ID={belief_id})")

            # =========================
            # 🧠 HIGH VALUE MEMORY (SCORING)
            # =========================

            if len(insight) > 400 or source == "wikipedia":

                importance = 0

                if len(insight) > 400:
                    importance += 2

                if source == "wikipedia":
                    importance += 2

                if "pattern" in insight.lower() or "system" in insight.lower():
                    importance += 1

                memory_manager.store_memory(
                    content=insight,
                    summary=insight[:150],
                    source=source,
                    tier="high_value",
                    importance=importance,
                )

            print(f"🔥 HIGH VALUE INSIGHT SAVED (importance={importance})")
            # =========================
            # 🧠 REINFORCEMENT
            # =========================
            print("🧠 REINFORCEMENT TRIGGERED")

            memory = ensure_memory(load_memory())

            reinforcement = memory.get("reinforcement", {})

            key = normalize_topic(normalize_topic_name(search_term))
            if key:
                if key and isinstance(key, str):
                    reinforcement[key] = reinforcement.get(key, 0) + importance
                else:
                    print("⚠️ SKIPPING INVALID REINFORCEMENT:", key)

            memory["reinforcement"] = reinforcement

            save_memory(memory)

            print(f"📈 REINFORCED: {key} (+{importance})")

            # =========================
            # 🧠 TOPIC MEMORY
            # =========================
            # 🔥 RELOAD FRESH MEMORY BEFORE MODIFYING
            memory = ensure_memory(load_memory())

            # 🧠 DECAY OLD TOPICS (prevents domination)
            topic_interest = memory.get("topic_interest", {})
            for k in topic_interest:
                topic_interest[k] *= 0.85  # decay factor

            # ➕ add current topic
            key = normalize_topic_name(search_term)
            current_score = topic_interest.get(key, 0)

            # 🚨 prevent runaway dominance
            if current_score < 50:
                topic_interest[key] = current_score + 1
            else:
                topic_interest[key] = current_score + 0.2  # slow growth

            memory["topic_interest"] = topic_interest

            # 🧠 DEBATE WEIGHTING
            if stance == "CHALLENGE":
                print("⚔️ BOOSTING CONFLICT SIGNAL")
                memory["debate_intensity"] = memory.get("debate_intensity", 0) + 1

            memory = update_topic_scores(
                memory=memory,
                insight=insight,
                search_term=search_term,
                source=source,
            )

            # =========================
            # 🧠 TOPICS
            # =========================

            top_topics = get_top_topics(memory, limit=5)
            top_topic_names = [t[0] for t in top_topics]
            topic_context = (
                ", ".join(top_topic_names) if top_topic_names else "none yet"
            )

            # =========================
            # ⚡ SYNTHESIS (ADD HERE)
            # =========================

            import random

            synthesis_pairs = []

            if len(top_topic_names) >= 2:
                for _ in range(2):
                    a, b = random.sample(top_topic_names, 2)
                    if a != b:
                        pair = tuple(sorted((a, b)))
                    if pair not in synthesis_pairs:
                        synthesis_pairs.append(pair)

            # =========================
            # 🧠 SYNTHESIS CONTEXT
            # =========================

            synthesis_context = ""

            for a, b in synthesis_pairs:
                synthesis_context += f"- Combine '{a}' with '{b}'\n"

            # 🧠 STORE SYNTHESIS FOR UI
            memory["last_synthesis"] = synthesis_pairs
            save_memory(memory)

            # DEBUG (optional but recommended)
            if synthesis_pairs:
                print("⚡ SYNTHESIS PAIRS:", synthesis_pairs)
                print(f"🧠 TOP TOPICS: {top_topics}")

            save_memory(memory)

            time.sleep(30)

        except Exception as e:
            print("❌ BRAIN ERROR:", e)
            time.sleep(5)

            synthesis_context += "\nSynthesis Goal:\n"

            for a, b in synthesis_pairs:
                synthesis_context += (
                    f"Explore how '{a}' influences or transforms '{b}'.\n"
                )


# =========================
# START
# =========================
if __name__ == "__main__":
    print("🔥 HABITAT ONLINE")

    threading.Thread(target=run, daemon=True).start()

    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
