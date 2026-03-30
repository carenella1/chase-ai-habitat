from habitat.cognition.cognition_logger import CognitionLogger

logger = CognitionLogger()
class WorldModelAgent:

    def __init__(self):
        self.world_model = []

    def update_world_model(self):

        # placeholder update
        self.world_model.append("system observation")

    def summarize_world_model(self):

        if not self.world_model:
            return "World model empty."

        return " | ".join(self.world_model[-5:])