import json
from pathlib import Path


STATE_PATH = Path("data/governance/governance_state.json")


class GovernanceEngine:

    def __init__(self):

        self.state = self.load_state()

    def load_state(self):

        if not STATE_PATH.exists():
            return {
                "memory_prune_threshold": 10000,
                "program_retention_limit": 50,
                "artifact_scores": {}
            }

        with open(STATE_PATH, "r") as f:
            return json.load(f)

    def save_state(self):

        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(STATE_PATH, "w") as f:
            json.dump(self.state, f, indent=2)

    def score_artifact(self, artifact):

        score = len(artifact) // 50

        return score

    def evaluate_memory(self, memory_items):

        if len(memory_items) > self.state["memory_prune_threshold"]:
            return "PRUNE_MEMORY"

        return "OK"

    def evaluate_programs(self, programs):

        if len(programs) > self.state["program_retention_limit"]:
            return "PRUNE_PROGRAMS"

        return "OK"