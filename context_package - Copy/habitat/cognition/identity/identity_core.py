import json
from pathlib import Path


IDENTITY_PATH = Path("data/identity/identity_core.json")


class IdentityCore:

    def __init__(self):
        self.identity = self.load_identity()

    def load_identity(self):

        if not IDENTITY_PATH.exists():
            raise FileNotFoundError(
                "Identity file missing: data/identity/identity_core.json"
            )

        with open(IDENTITY_PATH, "r") as f:
            return json.load(f)

    def mission(self):
        return self.identity["mission"]

    def north_star(self):
        return self.identity["north_star"]

    def creator(self):
        return self.identity["creator_name"]

    def alignment_weights(self):
        return self.identity.get("alignment_weights", {})

    def strategic_domains(self):
        return self.identity.get("strategic_domains", [])

    def creator_priorities(self):
        return self.identity.get("creator_priorities", [])

    def preferred_modes(self):
        return self.identity.get("preferred_modes", [])

    def disallowed_modes(self):
        return self.identity.get("disallowed_modes", [])

    def score_alignment(self, concept):

        score = 0
        domains = self.strategic_domains()

        for d in domains:
            if d.lower() in concept.lower():
                score += 2

        for p in self.creator_priorities():
            if any(word in concept.lower() for word in p.lower().split()):
                score += 1

        return score