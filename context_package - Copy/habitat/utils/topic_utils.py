def normalize_topic(topic):
    if not topic:
        return "general"

    topic = str(topic).lower()

    # =========================
    # 🧹 CLEAN SYMBOLS
    # =========================
    topic = topic.replace("*", "")
    topic = topic.replace('"', "")
    topic = topic.replace("'", "")
    topic = topic.strip()

    # =========================
    # ✂️ REMOVE COMMON GARBAGE PHRASES
    # =========================
    garbage_phrases = [
        "this title meets the guidelines",
        "based on the provided text",
        "i identified",
        "the following",
        "in this context",
        "analysis",
        "insight",
        "pattern",
    ]

    for phrase in garbage_phrases:
        topic = topic.replace(phrase, "")

    # =========================
    # ✂️ CUT AT FIRST SENTENCE BREAK
    # =========================
    for splitter in [".", ":", "\n"]:
        if splitter in topic:
            topic = topic.split(splitter)[0]

    # =========================
    # ✂️ LIMIT LENGTH
    # =========================
    topic = topic.strip()
    topic = topic[:60]

    # =========================
    # 🧠 FALLBACK
    # =========================
    if not topic or len(topic) < 3:
        return "general"

    return topic


print(f"🧹 NORMALIZED TOPIC: {topic}")
