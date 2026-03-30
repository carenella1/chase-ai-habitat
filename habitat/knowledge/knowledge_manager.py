import json
import os
import time

KNOWLEDGE_FILE = "knowledge.json"


def load_knowledge():
    if not os.path.exists(KNOWLEDGE_FILE):
        return []
    try:
        with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_knowledge(data):
    with open(KNOWLEDGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def add_knowledge_entry(topic, content, source, confidence=0.5, tags=None):
    knowledge = load_knowledge()

    entry = {
        "topic": topic,
        "content": content,
        "source": source,
        "confidence": confidence,
        "tags": tags or [],
    }

    knowledge.append(entry)
    save_knowledge(knowledge)


def search_knowledge(query, limit=5):
    knowledge = load_knowledge()
    query = (query or "").lower()

    results = []

    for item in knowledge:
        text = (item.get("topic", "") + " " + item.get("content", "")).lower()

        if query and query in text:
            results.append(item)

    return results[-limit:]


def get_recent_knowledge(limit=5):
    knowledge = load_knowledge()
    return knowledge[-limit:]
