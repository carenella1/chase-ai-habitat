import json
from pathlib import Path

from habitat.runtime.kernel import HabitatKernel


CHAT_HISTORY_PATH = Path("data/system/chat_history.json")


class ChatService:

    def __init__(self, kernel):
        self.kernel = kernel
        self.history = self.load_history()

    def load_history(self):

        if not CHAT_HISTORY_PATH.exists():
            return []

        with open(CHAT_HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_history(self):

        CHAT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(CHAT_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(self.history, f, indent=2, ensure_ascii=False)

    def get_history(self):
        return self.history

    def send_message(self, message):

        user_message = {
            "role": "user",
            "content": message
        }
        self.history.append(user_message)

        try:
            response = self.kernel.chat(message)
        except Exception as e:
            response = f"Chat pipeline error: {str(e)}"

        assistant_message = {
            "role": "assistant",
            "content": response
        }
        self.history.append(assistant_message)

        self.save_history()

        return assistant_message

    def clear_history(self):
        self.history = []
        self.save_history()