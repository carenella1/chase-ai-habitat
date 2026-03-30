from collections import Counter
from habitat.memory.memory_manager import MemoryManager
from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()

class CuriosityEngineAgent:

    def __init__(self):

        self.memory = MemoryManager()

        self.stopwords = {
            "habitat", "research", "systems", "system", "knowledge",
            "possible", "insight", "showing", "indicate", "promising",
            "opportunities", "recent", "memory", "agent", "agents",
            "result", "results", "question", "questions", "cycle",
            "analysis", "thread", "threads", "discovery", "discoveries",
            "proposal", "proposals", "recommendation", "recommendations",
            "topic", "topics", "current", "suggested", "continue",
            "related", "within", "across", "future", "further",
            "exploring", "exploration", "recommended"
        }

        self.source_weights = {
            "web_research_agent": 4,
            "researcher_agent": 3,
            "research_thread_agent": 3,
            "topic_explorer_agent": 2,
            "idea_graph_agent": 2,
            "curator_agent": 1,
            "strategist_agent": 1,
            "builder_agent": 1,
            "insight_agent": 1
        }

    def tokenize(self, text):

        cleaned = []
        for token in text.lower().split():
            token = token.strip(".,:;!?()[]{}\"'`-/\\")
            if len(token) < 5:
                continue
            if token in self.stopwords:
                continue
            cleaned.append(token)

        return cleaned

    def score_topics(self):

        entries = self.memory.get_recent_memory_entries(80)

        counter = Counter()

        for entry in entries:

            source = entry["source"]
            content = entry["content"]

            weight = self.source_weights.get(source, 1)

            tokens = self.tokenize(content)

            for token in tokens:
                counter[token] += weight

        ranked = counter.most_common(10)

        return [
            {"topic": topic, "score": score}
            for topic, score in ranked
        ]