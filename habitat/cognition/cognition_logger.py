import json
import os
from datetime import datetime


LOG_PATH = "knowledge/cognition_log.json"


class CognitionLogger:

    def __init__(self):

        os.makedirs("knowledge", exist_ok=True)

        if not os.path.exists(LOG_PATH):
            with open(LOG_PATH, "w") as f:
                json.dump([], f)

    def log(self, agent, thought_type, content, reasoning=None, confidence=None):

        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent": agent,
            "type": thought_type,
            "content": content,
            "reasoning": reasoning,
            "confidence": confidence
        }

        with open(LOG_PATH, "r") as f:
            data = json.load(f)

        data.append(entry)

        # keep log from exploding forever
        data = data[-500:]

        with open(LOG_PATH, "w") as f:
            json.dump(data, f, indent=2)

        print(f"[COGNITION] {agent} → {thought_type}")