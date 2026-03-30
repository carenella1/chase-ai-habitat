from habitat.agents.researcher_agent import ResearcherAgent
from habitat.memory.memory_manager import MemoryManager


class ResearchLoop:

    def __init__(self):
        self.researcher = ResearcherAgent()
        self.memory = MemoryManager()

    def run(self):

        questions = [
            "What are emerging trends in autonomous AI agents?",
            "What problems do personal AI systems need to solve?",
            "What are risks of autonomous AI ecosystems?"
        ]

        print("\nRunning research loop...\n")

        for q in questions:

            print("Researching:", q)

            result = self.researcher.run(q)

            self.memory.store_memory(
                content=result,
                summary="research_loop",
                source="research_loop"
            )

            print("Stored research result.\n")