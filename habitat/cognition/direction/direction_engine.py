import json
from pathlib import Path


STATE_PATH = Path("data/direction/direction_state.json")


class DirectionEngine:

    def __init__(self, identity):

        self.identity = identity
        self.state = self.load_state()

    def load_state(self):

        if not STATE_PATH.exists():

            return {
                "priority_domains": self.identity.strategic_domains(),
                "active_focus": None,
                "cycle_count": 0
            }

        with open(STATE_PATH, "r") as f:
            return json.load(f)

    def save_state(self):

        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(STATE_PATH, "w") as f:
            json.dump(self.state, f, indent=2)

    def choose_focus(self):

        domains = self.state["priority_domains"]

        if not domains:
            return None

        index = self.state["cycle_count"] % len(domains)

        focus = domains[index]

        self.state["active_focus"] = focus
        self.state["cycle_count"] += 1

        self.save_state()

        return focus