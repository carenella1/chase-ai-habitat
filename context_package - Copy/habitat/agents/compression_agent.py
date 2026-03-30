from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()
class CompressionAgent:

    def compress(self, text):

        if not text:
            return ""

        text = text.strip()

        # Remove repetitive narrative phrases
        junk_phrases = [
            "Possible Insight:",
            "Observation:",
            "Research Topic:",
            "Preliminary Analysis:",
            "Possible Areas to Investigate:",
            "Further exploration recommended.",
            "These ideas appear semantically related",
            "The Habitat is showing recurring themes"
        ]

        for phrase in junk_phrases:
            text = text.replace(phrase, "")

        # keep first meaningful sentence
        sentences = [s.strip() for s in text.split("\n") if len(s.strip()) > 20]

        if sentences:
            return sentences[0]

        return text[:200]