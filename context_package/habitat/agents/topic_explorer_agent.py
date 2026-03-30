from habitat.memory.memory_manager import MemoryManager
from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()

class TopicExplorerAgent:

    def __init__(self):

        self.memory = MemoryManager()

    def select_topic(self, scored_topics=None):

        if scored_topics and len(scored_topics) > 0:
            return scored_topics[0]["topic"]

        memories = self.memory.get_recent_memories(10)

        if not memories:
            return "emerging intelligence systems"

        return memories[0]

    def generate_research_direction(self, topic):

        direction = f"""
Long-Term Research Thread:

Topic:
{topic}

Research Goal:
Explore this concept across multiple cognition cycles to uncover
deeper implications, tools, infrastructure opportunities, or new agent roles.

Potential Areas:
- technology applications
- system architecture
- autonomous implementations
- strategic leverage
"""

        return direction.strip()