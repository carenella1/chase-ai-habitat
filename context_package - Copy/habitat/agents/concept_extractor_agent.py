from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()
class ConceptExtractorAgent:

    def __init__(self):
        pass

    def extract_concepts(self, text):

        # very simple placeholder concept extraction
        words = text.split()

        concepts = []

        for w in words:
            w = w.strip(".,!?()[]{}").lower()

            if len(w) > 6 and w not in concepts:
                concepts.append(w)

        return concepts[:10]