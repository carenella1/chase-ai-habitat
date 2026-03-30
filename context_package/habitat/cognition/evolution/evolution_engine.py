import json
from pathlib import Path


STATE_PATH = Path("data/evolution/evolution_state.json")


class EvolutionEngine:

    def __init__(self):
        self.state = self.load_state()

    def load_state(self):

        if not STATE_PATH.exists():
            return {
                "proposal_count": 0,
                "proposals": []
            }

        with open(STATE_PATH, "r") as f:
            return json.load(f)

    def save_state(self):

        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(STATE_PATH, "w") as f:
            json.dump(self.state, f, indent=2)

    def build_proposals(self, suggestions):

        new_proposals = []

        for suggestion in suggestions:
            proposal = {
                "id": self.state["proposal_count"] + 1,
                "source": "reflection_engine",
                "suggestion": suggestion,
                "status": "proposed"
            }

            self.state["proposal_count"] += 1
            self.state["proposals"].append(proposal)
            new_proposals.append(proposal)

        self.save_state()
        return new_proposals

    def get_active_proposals(self):

        return [
            p for p in self.state["proposals"]
            if p["status"] == "proposed"
        ]

    def mark_in_progress(self, proposal_id):

        for proposal in self.state["proposals"]:
            if proposal["id"] == proposal_id:
                proposal["status"] = "in_progress"

        self.save_state()

    def mark_completed(self, proposal_id):

        for proposal in self.state["proposals"]:
            if proposal["id"] == proposal_id:
                proposal["status"] = "completed"

        self.save_state()