import requests
from habitat.memory.memory_manager import MemoryManager
from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()

class WebResearchAgent:

    def __init__(self):

        self.memory = MemoryManager()

    def search_web(self, query):

        # Simple DuckDuckGo instant API search
        url = f"https://api.duckduckgo.com/?q={query}&format=json"

        try:
            r = requests.get(url)
            data = r.json()

            if "AbstractText" in data and data["AbstractText"]:
                return data["AbstractText"]

            if "RelatedTopics" in data and len(data["RelatedTopics"]) > 0:
                topic = data["RelatedTopics"][0]
                if "Text" in topic:
                    return topic["Text"]

        except Exception as e:
            return f"Web research error: {e}"

        return "No useful information found."

    def research(self, topic):

        result = self.search_web(topic)

        self.memory.store_memory(
            content=result,
            summary="web research discovery",
            source="web_research_agent"
        )

        return result