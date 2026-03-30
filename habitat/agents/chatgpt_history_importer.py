import json
import os

from habitat.agents.compression_agent import CompressionAgent
from habitat.memory.memory_manager import MemoryManager


class ChatGPTHistoryImporter:

    def __init__(self):

        self.memory = MemoryManager()
        self.compressor = CompressionAgent()

    def import_directory(self, directory):

        total_imported = 0

        if not os.path.exists(directory):
            print(f"Directory not found: {directory}")
            return 0

        files = os.listdir(directory)

        conversation_files = [
            f for f in files if f.startswith("conversations") and f.endswith(".json")
        ]

        if not conversation_files:
            print("No conversation files found.")
            return 0

        for file in sorted(conversation_files):

            filepath = os.path.join(directory, file)

            print(f"\nProcessing {file}...")

            count = self.import_conversations_file(filepath)

            print(f"Imported {count} memory entries from {file}")

            total_imported += count

        return total_imported

    def import_conversations_file(self, filepath):

        if not os.path.exists(filepath):
            print(f"Import file not found: {filepath}")
            return 0

        with open(filepath, "r", encoding="utf-8") as f:
            conversations = json.load(f)

        imported = 0

        for convo in conversations:

            mapping = convo.get("mapping", {})

            for node_id, node in mapping.items():

                message = node.get("message")

                if not message:
                    continue

                author = message.get("author", {}).get("role", "")
                content = message.get("content", {})
                parts = content.get("parts", [])

                if not parts:
                    continue

                text_parts = [p for p in parts if isinstance(p, str)]

                if not text_parts:
                    continue

                raw_text = "\n".join(text_parts).strip()

                if not raw_text:
                    continue

                compressed = self.compressor.compress(raw_text)

                if not compressed:
                    continue

                source = f"chatgpt_history_{author}"

                # force persistent memory
                stored = self.memory.store_memory(
                    content=compressed,
                    summary="chatgpt history import",
                    source=source,
                    tier="long_term"
                )

                imported += 1

        return imported