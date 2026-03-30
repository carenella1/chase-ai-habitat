import json
from pathlib import Path


STATE_PATH = Path("data/system/habitat_state.json")


class HabitatMonitor:

    def __init__(self):
        self.state = self.load_state()

    def load_state(self):

        if not STATE_PATH.exists():
            return {
                "cycles": 0,
                "last_focus": None,
                "research_programs": 0,
                "memory_tiers": {},
                "evolution_queue": 0
            }

        with open(STATE_PATH, "r") as f:
            return json.load(f)

    def save_state(self):

        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(STATE_PATH, "w") as f:
            json.dump(self.state, f, indent=2)

    def update_cycle(self, focus):

        self.state["cycles"] += 1
        self.state["last_focus"] = focus

        self.save_state()

    def update_memory(self, memory_summary):

        self.state["memory_tiers"] = memory_summary

        self.save_state()

    def update_research(self, count):

        self.state["research_programs"] = count

        self.save_state()

    def update_evolution(self, count):

        self.state["evolution_queue"] = count

        self.save_state()

    def snapshot(self):
        return self.state