from habitat.memory.memory_manager import MemoryManager
from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()

class StrategistAgent:

    def __init__(self):
        self.memory = MemoryManager()

    def generate_strategies(self, discoveries):

        strategies = []

        for d in discoveries:

            text = d.lower()

            if "identity" in text or "reputation" in text:
                strategies.append("""
Strategy Recommendation:
Develop autonomous PBSA expansion tools.

Idea:
Create a system that automatically generates satellite sites,
entity metadata, and knowledge graphs to reinforce a digital identity.
""".strip())

            elif "agent" in text or "ai" in text:
                strategies.append("""
Strategy Recommendation:
Expand the Habitat agent ecosystem.

Idea:
Design new agents specialized in research, analysis, or automation
that can operate within the Habitat and contribute discoveries.
""".strip())

            elif "infrastructure" in text or "system" in text:
                strategies.append("""
Strategy Recommendation:
Create reusable digital infrastructure frameworks.

Idea:
Convert this concept into modular infrastructure components
that can be reused across projects or deployed at scale.
""".strip())

            else:
                strategies.append("""
Strategy Recommendation:
Run exploratory experiments.

Idea:
Prototype small tools or experiments to test the potential of this idea
before committing to a full build.
""".strip())

        return list(dict.fromkeys(strategies))