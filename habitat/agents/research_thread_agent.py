from habitat.memory.memory_manager import MemoryManager
from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()

class ResearchThreadAgent:

    def __init__(self):

        self.memory = MemoryManager()

    def seed_threads(self, scored_topics):

        for item in scored_topics[:5]:

            topic = item["topic"]
            score = int(item["score"])

            self.memory.upsert_research_thread(
                topic=topic,
                status="active",
                priority=score,
                last_result=""
            )

    def choose_thread(self):

        threads = self.memory.get_active_threads(10)

        if not threads:
            return None

        return threads[0]

    def update_thread(self, topic, result, priority=1):

        self.memory.upsert_research_thread(
            topic=topic,
            status="active",
            priority=priority,
            last_result=result
        )