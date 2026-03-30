from habitat.memory.memory_manager import MemoryManager
from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()

class CuriosityAgent:

    def __init__(self):
        self.memory = MemoryManager()

    def generate_questions(self):

        # Correct function name
        memories = self.memory.get_recent_memories(10)

        questions = []

        for m in memories:

            text = str(m).lower()

            if "system" in text or "framework" in text:
                questions.append(
                    "What new tools or platforms could be built from this idea?"
                )

            if "ai" in text or "agent" in text:
                questions.append(
                    "What new AI agents could extend this capability?"
                )

            if "identity" in text or "reputation" in text:
                questions.append(
                    "How could this evolve into a global identity infrastructure?"
                )

            if "research" in text:
                questions.append(
                    "What unexplored areas remain within this topic?"
                )

        if not questions:
            questions.append(
                "What unexplored opportunities exist within the Habitat ecosystem?"
            )

        # Remove duplicates
        questions = list(set(questions))

        return questions