import json
from pathlib import Path


STATE_PATH = Path("data/memory/memory_lifecycle_state.json")


class MemoryLifecycleManager:

    def __init__(self):
        self.state = self.load_state()

    def load_state(self):

        if not STATE_PATH.exists():
            return {
                "memory_scores": {},
                "tiers": {
                    "ephemeral": [],
                    "working": [],
                    "knowledge": [],
                    "core": []
                }
            }

        with open(STATE_PATH, "r") as f:
            return json.load(f)

    def save_state(self):

        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(STATE_PATH, "w") as f:
            json.dump(self.state, f, indent=2)

    def score_memory(self, text):

        score = len(text) // 40

        if "strategy" in text.lower():
            score += 3

        if "architecture" in text.lower():
            score += 3

        return score

    def classify_memory(self, text):

        score = self.score_memory(text)

        if score < 2:
            tier = "ephemeral"
        elif score < 5:
            tier = "working"
        elif score < 8:
            tier = "knowledge"
        else:
            tier = "core"

        self.state["tiers"][tier].append(text)

        self.save_state()

        return tier

    def memory_summary(self):

        return {
            tier: len(items)
            for tier, items in self.state["tiers"].items()
        }