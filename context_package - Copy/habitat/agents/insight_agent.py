from habitat.memory.memory_manager import MemoryManager
from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()

class InsightAgent:

    def __init__(self):

        self.memory = MemoryManager()

        self.preferred_sources = {
            "researcher_agent",
            "web_research_agent",
            "topic_explorer_agent",
            "research_thread_agent",
            "archivist_agent",
            "voice_interface"
        }

    def generate_insight(self):

        entries = self.memory.get_recent_memory_entries(30)

        filtered = []

        for entry in entries:

            source = entry["source"]
            content = entry["content"]

            if source in self.preferred_sources:
                filtered.append(content)

        if not filtered:
            filtered = [e["content"] for e in entries[:5]]

        filtered = filtered[:5]

        if not filtered:
            return "No memories available yet."

        combined = "\n\n".join(filtered)

        insight = f"""
Recent Habitat Knowledge:

{combined}

Possible Insight:
The Habitat is showing recurring themes that may indicate promising opportunities, underdeveloped systems, or expandable project directions.
"""

        return insight.strip()