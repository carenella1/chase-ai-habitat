from habitat.agents.researcher_agent import ResearcherAgent
from habitat.agents.archivist_agent import ArchivistAgent
from habitat.orchestration.research_loop import ResearchLoop
from habitat.memory.memory_manager import MemoryManager


class Steward:

    def __init__(self):

        self.researcher = ResearcherAgent()
        self.archivist = ArchivistAgent()
        self.memory = MemoryManager()
        self.research_loop = ResearchLoop()

    def boot(self):

        print("Steward booting habitat")

        # ingest files
        self.archivist.ingest("data/raw/knowledge")

        # run research loop
        self.research_loop.run()

        question = "What are the biggest opportunities in autonomous AI systems?"

        result = self.researcher.run(question)

        print("\nResearch Result:")
        print(result)

        self.memory.store_memory(
            content=result,
            summary="research",
            source="researcher"
        )

        print("\nMemory stored.")