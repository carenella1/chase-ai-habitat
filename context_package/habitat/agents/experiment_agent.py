from habitat.memory.memory_manager import MemoryManager
from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()

class ExperimentAgent:

    def __init__(self):

        self.memory = MemoryManager()

    def generate_experiments(self):

        hypotheses = self.memory.get_open_hypotheses(5)

        experiments = []

        for h in hypotheses:

            hypothesis = h["hypothesis"]

            experiment = f"""
Experiment Proposal

Hypothesis:
{hypothesis}

Experiment Design:
Create a small prototype, test system, or research cycle specifically designed to evaluate whether this hypothesis produces measurable outcomes.

Possible Experiment Types:
- prototype tool
- automated research task
- architecture simulation
- agent deployment test
"""

            experiments.append({
                "hypothesis": hypothesis,
                "experiment": experiment
            })

        return experiments

    def evaluate_experiment(self, experiment):

        result = {
            "outcome": "inconclusive",
            "confidence_change": 0
        }

        text = experiment.lower()

        if "identity" in text:
            result["confidence_change"] = 1

        if "agent" in text:
            result["confidence_change"] = 1

        return result

    def update_hypothesis(self, hypothesis, confidence_change):

        hypotheses = self.memory.get_open_hypotheses(10)

        for h in hypotheses:

            if h["hypothesis"] == hypothesis:

                new_confidence = h["confidence"] + confidence_change

                if new_confidence < 1:
                    new_confidence = 1

                if new_confidence > 10:
                    new_confidence = 10

                self.memory.upsert_hypothesis(
                    hypothesis=hypothesis,
                    status="open",
                    confidence=new_confidence,
                    evidence="experiment update"
                )