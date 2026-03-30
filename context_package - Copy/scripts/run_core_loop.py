import time

from habitat.agents.insight_agent import InsightAgent
from habitat.agents.researcher_agent import ResearcherAgent
from habitat.agents.explorer_agent import ExplorerAgent
from habitat.memory.memory_manager import MemoryManager
from habitat.agents.curator_agent import CuratorAgent


class CoreLoop:

    def __init__(self):

        self.memory = MemoryManager()
        self.insight_agent = InsightAgent()
        self.researcher = ResearcherAgent()
        self.explorer = ExplorerAgent()
        self.curator = CuratorAgent()

    def run_cycle(self):

        print("\n=== HABITAT COGNITION CYCLE ===\n")

        insight = self.insight_agent.generate_insight()

        if not insight:
            print("No insights generated.")
            return

        print("Insight:")
        print(insight)

        question = self.researcher.generate_question(insight)

        print("\nExploration Question:")
        print(question)

        research = self.researcher.research(question)

        print("\nResearch Result:")
        print(research)

        self.memory.store_memory(research)

        explorations = self.explorer.explore(insight)

        print("\nExplorer Discoveries:")

        for e in explorations:
            print(e)

        promoted = self.curator.curate(explorations)

        print("\nCurator Promoted Discoveries:")

        for p in promoted:

            print(p)

            self.memory.store_memory(p)

    def run(self):

        while True:

            self.run_cycle()

            print("\nSleeping before next cognition cycle...\n")

            time.sleep(120)


def main():

    loop = CoreLoop()
    loop.run()


if __name__ == "__main__":
    main()