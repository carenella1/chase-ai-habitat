from habitat.memory.memory_manager import MemoryManager
from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()

class HypothesisAgent:

    def __init__(self):

        self.memory = MemoryManager()

    def generate_hypotheses(self, graph_insights, curated):

        hypotheses = []

        source_material = graph_insights + curated

        for item in source_material:
            text = item.lower()

            if "identity" in text or "reputation" in text:
                hypotheses.append({
                    "hypothesis": "Autonomous digital identity infrastructure could become a major application area for multi-agent systems.",
                    "confidence": 4,
                    "evidence": item
                })

            if "agent" in text or "autonomous" in text:
                hypotheses.append({
                    "hypothesis": "Specialized long-running agents will outperform general-purpose agents for persistent research domains.",
                    "confidence": 4,
                    "evidence": item
                })

            if "framework" in text or "system" in text or "infrastructure" in text:
                hypotheses.append({
                    "hypothesis": "Reusable modular infrastructure will accelerate Habitat evolution more than one-off feature development.",
                    "confidence": 3,
                    "evidence": item
                })

        if not hypotheses:
            hypotheses.append({
                "hypothesis": "The Habitat may benefit from further exploration before strong hypotheses can be formed.",
                "confidence": 1,
                "evidence": "Insufficient strong signal in current cycle."
            })

        deduped = []
        seen = set()

        for h in hypotheses:
            if h["hypothesis"] not in seen:
                seen.add(h["hypothesis"])
                deduped.append(h)

        return deduped

    def store_hypotheses(self, hypotheses):

        for h in hypotheses:
            self.memory.upsert_hypothesis(
                hypothesis=h["hypothesis"],
                status="open",
                confidence=h["confidence"],
                evidence=h["evidence"]
            )

    def generate_tests(self, hypotheses):

        tests = []

        for h in hypotheses:
            tests.append(f"""
Hypothesis Test Proposal

Hypothesis:
{h['hypothesis']}

Suggested Test:
Design a focused experiment, prototype, or multi-cycle investigation to gather stronger evidence for or against this hypothesis.

Current Confidence:
{h['confidence']}
""".strip())

        return tests