from habitat.knowledge.idea_graph import IdeaGraph
from habitat.memory.memory_manager import MemoryManager
from habitat.memory.embedder import Embedder
from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()

class IdeaGraphAgent:

    def __init__(self):

        self.memory = MemoryManager()
        self.embedder = Embedder()

        self.graph = IdeaGraph(
            embedder=self.embedder,
            memory_manager=self.memory
        )

    def analyze(self):

        clusters = self.graph.build_clusters()

        insights = []

        for cluster in clusters:

            if not cluster:
                continue

            idea = cluster[0]

            insights.append(
                f"Related idea cluster detected: {idea[:200]}"
            )

        return insights