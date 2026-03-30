from habitat.memory.memory_manager import MemoryManager
from habitat.agents.compression_agent import CompressionAgent
from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()

class CuratorAgent:

    def __init__(self):

        self.memory = MemoryManager()
        self.compressor = CompressionAgent()

    def evaluate(self, text):

        keywords = [
            "ai",
            "autonomous",
            "identity",
            "architecture",
            "system",
            "discovery",
            "agent",
            "infrastructure",
            "reputation",
            "metadata",
            "entity",
            "monitoring",
            "automation",
            "research"
        ]

        score = 0

        lowered = text.lower()

        for k in keywords:
            if k in lowered:
                score += 1

        return score

    def curate(self, discoveries):

        promoted = []
        seen = set()

        for d in discoveries:

            score = self.evaluate(d)

            if score < 2:
                continue

            compressed = self.compressor.compress(d).strip()

            if not compressed:
                continue

            if compressed in seen:
                continue

            seen.add(compressed)
            promoted.append(compressed)

        return promoted