import json
from pathlib import Path
from datetime import datetime


STATE_PATH = Path("data/system/agent_activity.json")


class AgentTelemetry:

    def __init__(self):
        self.state = self.load_state()

    def load_state(self):

        if not STATE_PATH.exists():
            return {"events": []}

        with open(STATE_PATH, "r") as f:
            return json.load(f)

    def save_state(self):

        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(STATE_PATH, "w") as f:
            json.dump(self.state, f, indent=2)

    def record(self, agent, action, count=1):

        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent": agent,
            "action": action,
            "count": count
        }

        self.state["events"].append(event)

        # keep log from growing forever
        self.state["events"] = self.state["events"][-500:]

        self.save_state()

    def recent_events(self, limit=10):
        return self.state["events"][-limit:]