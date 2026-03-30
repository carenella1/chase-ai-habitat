import json
from pathlib import Path


STATE_PATH = Path("data/research/research_programs.json")


def _normalize(value):
    try:
        import numpy as np

        if isinstance(value, np.integer):
            return int(value)

        if isinstance(value, np.floating):
            return float(value)

        if isinstance(value, np.ndarray):
            return [_normalize(v) for v in value.tolist()]

    except Exception:
        pass

    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_normalize(v) for v in value]

    if isinstance(value, tuple):
        return [_normalize(v) for v in value]

    return value


class ResearchManager:

    def __init__(self):

        self.programs = self.load_programs()

    def load_programs(self):

        if not STATE_PATH.exists():
            return []

        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_programs(self):

        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

        safe_programs = _normalize(self.programs)

        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(safe_programs, f, indent=2, ensure_ascii=False)

    def register_program(self, topic):

        topic = _normalize(topic)

        for p in self.programs:
            if p["topic"] == topic:
                return

        program = {
            "topic": topic,
            "updates": 0,
            "priority": 1
        }

        self.programs.append(program)
        self.save_programs()

    def update_program(self, topic):

        topic = _normalize(topic)

        for p in self.programs:
            if p["topic"] == topic:
                p["updates"] += 1

        self.save_programs()

    def choose_program(self):

        if not self.programs:
            return None

        sorted_programs = sorted(
            self.programs,
            key=lambda x: x["priority"] + x["updates"],
            reverse=True
        )

        return sorted_programs[0]["topic"]