from habitat.memory.memory_manager import MemoryManager
from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()

class AgentArchitect:

    def __init__(self):

        self.memory = MemoryManager()

    def propose_agents(self, topics):

        proposals = []

        for t in topics:

            topic = t["topic"]

            proposal = f"""
Proposed New Habitat Agent

Agent Name:
{topic.capitalize()}ResearchAgent

Purpose:
Continuously research developments related to "{topic}"
and feed discoveries back into the Habitat knowledge system.

Capabilities:
- monitor new information
- identify emerging technologies
- track long-term research progress
"""

            proposals.append(proposal.strip())

        return proposals