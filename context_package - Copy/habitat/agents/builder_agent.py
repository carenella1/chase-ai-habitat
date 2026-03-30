from habitat.memory.memory_manager import MemoryManager
from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()


class BuilderAgent:

    def __init__(self):

        self.memory = MemoryManager()

    def generate_builds(self, strategies):

        builds = []

        for s in strategies:

            text = s.lower()

            if "reputation" in text or "identity" in text:
                builds.append("""
Build Idea:
Create an AI-managed digital reputation monitoring system.

Description:
A tool that continuously monitors search results, entity graphs, and online mentions for a person or brand, then suggests PBSA expansion strategies automatically.
""".strip())

            if "agent" in text or "autonomous" in text:
                builds.append("""
Build Idea:
Create a new specialized Habitat agent.

Description:
Design a new agent that performs automated long-term research on one topic cluster and periodically reports findings back to the Habitat memory system.
""".strip())

            if "framework" in text or "system" in text or "infrastructure" in text:
                builds.append("""
Build Idea:
Develop a reusable infrastructure module.

Description:
Turn this concept into a modular framework component that other Habitat agents can reuse.
""".strip())

        if not builds:
            builds.append("""
Build Idea:
Prototype experiment.

Description:
Create a small experimental prototype to explore the idea further.
""".strip())

        return list(dict.fromkeys(builds))