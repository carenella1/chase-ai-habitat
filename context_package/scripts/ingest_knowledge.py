import os
from habitat.memory.memory_manager import MemoryManager


KNOWLEDGE_DIR = "data/raw/knowledge"


def read_files():

    documents = []

    if not os.path.exists(KNOWLEDGE_DIR):
        print(f"Directory not found: {KNOWLEDGE_DIR}")
        return documents

    for filename in os.listdir(KNOWLEDGE_DIR):

        filepath = os.path.join(KNOWLEDGE_DIR, filename)

        if not os.path.isfile(filepath):
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()

        documents.append(text)

    return documents


def chunk_text(text, chunk_size=500):

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size
        chunk = text[start:end]

        chunks.append(chunk)

        start = end

    return chunks


def main():

    memory = MemoryManager()

    documents = read_files()

    if not documents:
        print("No knowledge files found.")
        return

    total_chunks = 0

    print(f"Archivist scanning: {KNOWLEDGE_DIR}")

    for doc in documents:

        chunks = chunk_text(doc)

        for chunk in chunks:
            memory.store_memory(chunk)
            total_chunks += 1

    print(f"Archivist stored {total_chunks} chunks")


if __name__ == "__main__":
    main()