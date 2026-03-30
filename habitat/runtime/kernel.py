import json
import os
import time
import traceback
import hashlib

from habitat.agents.insight_agent import InsightAgent
from habitat.agents.curiosity_agent import CuriosityAgent
from habitat.agents.curiosity_engine_agent import CuriosityEngineAgent
from habitat.agents.researcher_agent import ResearcherAgent
from habitat.agents.research_thread_agent import ResearchThreadAgent
from habitat.agents.web_research_agent import WebResearchAgent
from habitat.agents.explorer_agent import ExplorerAgent
from habitat.agents.curator_agent import CuratorAgent
from habitat.agents.strategist_agent import StrategistAgent
from habitat.agents.builder_agent import BuilderAgent
from habitat.agents.idea_graph_agent import IdeaGraphAgent
from habitat.agents.topic_explorer_agent import TopicExplorerAgent
from habitat.agents.agent_architect import AgentArchitect
from habitat.agents.hypothesis_agent import HypothesisAgent
from habitat.agents.experiment_agent import ExperimentAgent
from habitat.agents.compression_agent import CompressionAgent
from habitat.agents.world_model_agent import WorldModelAgent
from habitat.agents.archivist_agent import ArchivistAgent

from habitat.memory.memory_manager import MemoryManager
from habitat.cognition.cognition_logger import CognitionLogger


class HabitatKernel:

    def __init__(self):

        self.memory = MemoryManager()
        self.cognition_logger = CognitionLogger()

        self.insight_agent = InsightAgent()
        self.curiosity_agent = CuriosityAgent()
        self.curiosity_engine = CuriosityEngineAgent()

        self.researcher = ResearcherAgent()
        self.thread_agent = ResearchThreadAgent()
        self.web_research = WebResearchAgent()

        self.explorer = ExplorerAgent()
        self.curator = CuratorAgent()

        self.idea_graph = IdeaGraphAgent()
        self.topic_explorer = TopicExplorerAgent()

        self.strategist = StrategistAgent()
        self.builder = BuilderAgent()

        self.agent_architect = AgentArchitect()
        self.hypothesis_agent = HypothesisAgent()
        self.experiment_agent = ExperimentAgent()

        self.compressor = CompressionAgent()
        self.world_model_agent = WorldModelAgent()

        self.archivist_agent = ArchivistAgent()

        self.cycle_count = 0

        # 🔐 Persistent memory guard
        self.seen_file = os.path.join("data", "seen_hashes.json")
        self.seen_hashes = self.load_seen_hashes()

    # =============================
    # SEEN HASHES
    # =============================
    def load_seen_hashes(self):
        if os.path.exists(self.seen_file):
            with open(self.seen_file, "r") as f:
                return set(json.load(f))
        return set()

    def save_seen_hashes(self):
        os.makedirs("data", exist_ok=True)
        with open(self.seen_file, "w") as f:
            json.dump(list(self.seen_hashes), f)

    def hash_text(self, text):
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    # =============================
    # STORAGE
    # =============================
    def store(self, content, summary, source):

        compressed = self.compressor.compress(content)

        self.memory.store_memory(
            content=compressed,
            summary=summary,
            source=source
        )

    # =============================
    # CHATGPT ASSIMILATION (FIXED)
    # =============================
    def assimilate_chatgpt_files(self):

        try:
            base_path = os.path.join("knowledge_sources", "chatgpt_history")

            if not os.path.exists(base_path):
                print("[Assimilation] folder not found")
                return

            files = [f for f in os.listdir(base_path) if f.endswith(".json")]

            if not files:
                print("[Assimilation] no files found")
                return

            print("\n[Assimilation] Running...")

            files = files[:1]  # 🔥 throttle

            processed = 0
            limit_per_cycle = 20  # 🔥 HARD LIMIT

            for file in files:

                path = os.path.join(base_path, file)

                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                for convo in data:

                    mapping = convo.get("mapping", {})

                    for node in mapping.values():

                        message = node.get("message")
                        if not message:
                            continue

                        content = message.get("content", {})
                        parts = content.get("parts", [])

                        if not parts:
                            continue

                        text = parts[0]

                        if not text or len(text) < 40:
                            continue

                        text_hash = self.hash_text(text)

                        # 🔐 SKIP IF ALREADY SEEN
                        if text_hash in self.seen_hashes:
                            continue

                        self.seen_hashes.add(text_hash)

                        # Generate insight
                        if hasattr(self.insight_agent, "generate_insight_from_text"):
                            insight = self.insight_agent.generate_insight_from_text(text)
                        else:
                            insight = f"Memory pattern: {text[:200]}"

                        print("\n[Assimilated]")
                        print(insight[:200])

                        self.cognition_logger.log(
                            agent="AssimilationEngine",
                            thought_type="chatgpt_memory_analysis",
                            content=insight
                        )

                        self.store(
                            insight,
                            "derived from ChatGPT history",
                            "chatgpt_assimilation"
                        )

                        processed += 1

                        # 🔥 LIMIT PER CYCLE
                        if processed >= limit_per_cycle:
                            self.save_seen_hashes()
                            return

            self.save_seen_hashes()

        except Exception as e:
            print("[Assimilation Error]", e)

    # =============================
    # MAIN CYCLE
    # =============================
    def run_cycle(self):

        self.cycle_count += 1

        print(f"\n=== HABITAT COGNITION CYCLE {self.cycle_count} ===\n")

        try:

            # 🔥 Assimilation FIRST
            self.assimilate_chatgpt_files()

            insight = self.insight_agent.generate_insight()

            self.cognition_logger.log(
                agent="InsightAgent",
                thought_type="insight",
                content=insight
            )

            self.store(insight, "habitat insight", "insight_agent")

            questions = self.curiosity_agent.generate_questions()
            question = questions[0]

            research_result = self.researcher.research(question)
            self.store(research_result, "research result", "researcher_agent")

            discoveries = self.explorer.explore(research_result)
            curated = self.curator.curate(discoveries)

            for c in curated:
                self.store(c, "curated discovery", "curator_agent")

            graph_insights = self.idea_graph.analyze()

            for g in graph_insights:
                self.store(g, "idea graph discovery", "idea_graph_agent")

            strategies = self.strategist.generate_strategies(
                curated + graph_insights
            )

            builds = self.builder.generate_builds(strategies)

            for b in builds:
                self.store(b, "builder proposal", "builder_agent")

            print("\nCycle complete.")

        except Exception:
            print("\nCognition cycle crashed:")
            traceback.print_exc()

    # =============================
    # SAFE RUNTIME LOOP
    # =============================
    def run_forever(self, interval_seconds=300):

        print("\nHabitat runtime started.\n")

        max_cycles = 500
        cycles_run = 0

        while True:

            try:
                start_time = time.time()

                self.run_cycle()
                cycles_run += 1

                if cycles_run >= max_cycles:
                    print("\n[Safety] Max cycles reached. Shutdown.")
                    break

                elapsed = time.time() - start_time
                sleep_time = max(interval_seconds - elapsed, 5)

                print(f"\nSleeping {sleep_time:.2f}s...\n")

                time.sleep(sleep_time)

            except KeyboardInterrupt:
                print("\n[Shutdown] Manual stop.")
                break

            except Exception as e:
                print("\n[Runtime Error]", e)
                time.sleep(10)