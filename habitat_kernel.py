import random


class HabitatKernel:

    def __init__(self):

        self.cycle_count = 0

        self.agents = [
            "InsightAgent",
            "CuriosityAgent",
            "CuriosityEngineAgent",
            "ResearcherAgent",
            "ResearchThreadAgent",
            "WebResearchAgent",
            "ExplorerAgent",
            "CuratorAgent",
            "StrategistAgent",
            "BuilderAgent",
            "IdeaGraphAgent",
            "TopicExplorerAgent",
            "AgentArchitect",
            "HypothesisAgent",
            "ExperimentAgent",
            "CompressionAgent",
            "WorldModelAgent",
            "ArchivistAgent"
        ]

        self.research_topics = []
        self.idea_pool = []

        self.spawnable_agent_names = [
            "MarketResearchAgent",
            "MemoryGardenerAgent",
            "SignalMonitorAgent",
            "PatternHunterAgent",
            "NarrativeWeaverAgent",
            "OpportunityScoutAgent",
            "SynthesisAgent",
            "EnvironmentMapperAgent",
            "IdentityModelAgent",
            "TrendWatchAgent"
        ]

    def maybe_spawn_agent(self):
        """
        Occasionally create a new agent if one is available.
        """

        if not self.spawnable_agent_names:
            return None

        # Roughly every few cycles, try to spawn something new.
        # This keeps the habitat from exploding with agents too fast.
        spawn_roll = random.random()

        if spawn_roll < 0.22:
            new_agent = self.spawnable_agent_names.pop(0)
            self.agents.append(new_agent)
            return new_agent

        return None

    def run_cycle(self):

        self.cycle_count += 1

        print(f"\n=== HABITAT COGNITION CYCLE {self.cycle_count} ===")

        spawned_agent = self.maybe_spawn_agent()

        if spawned_agent:
            print(f"New agent spawned: {spawned_agent}")
            return {
                "cycle": self.cycle_count,
                "agent": spawned_agent,
                "action": "spawned_new_agent",
                "spawned": True
            }

        agent = random.choice(self.agents)

        action = random.choice([
            "exploring new idea",
            "researching topic",
            "connecting concepts",
            "generating hypothesis",
            "refining strategy"
        ])

        idea = random.choice([
            "adaptive cognition",
            "agent ecosystems",
            "knowledge clustering",
            "identity modeling",
            "research synthesis",
            "memory gardening",
            "signal interpretation",
            "tool building"
        ])

        self.idea_pool.append(idea)

        print(f"{agent} is {action}: {idea}")

        return {
            "cycle": self.cycle_count,
            "agent": agent,
            "action": action,
            "idea": idea,
            "spawned": False
        }


kernel = HabitatKernel()