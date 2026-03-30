import json
from pathlib import Path


STATE_PATH = Path("data/reflection/reflection_state.json")


class ReflectionEngine:

    def __init__(self):

        self.state = self.load_state()

    def load_state(self):

        if not STATE_PATH.exists():
            return {
                "cycle_count": 0,
                "observations": []
            }

        with open(STATE_PATH, "r") as f:
            return json.load(f)

    def save_state(self):

        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(STATE_PATH, "w") as f:
            json.dump(self.state, f, indent=2)

    def record_cycle(self, focus, discoveries):

        observation = {
            "focus": focus,
            "discoveries": len(discoveries)
        }

        self.state["observations"].append(observation)
        self.state["cycle_count"] += 1

        self.save_state()

    def analyze_system(self):

        if self.state["cycle_count"] < 5:
            return []

        suggestions = []

        total_discoveries = sum(
            o["discoveries"] for o in self.state["observations"]
        )

        avg_discoveries = total_discoveries / len(self.state["observations"])

        if avg_discoveries < 2:
            suggestions.append(
                "Explorer agent may need improved discovery heuristics."
            )

        if avg_discoveries > 8:
            suggestions.append(
                "Curator filtering may need tightening due to discovery volume."
            )

        return suggestions