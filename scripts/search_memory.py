from habitat.memory.memory_manager import MemoryManager


def main():

    memory = MemoryManager()

    results = memory.search_memory("PBSA")

    print("\nSemantic Memory Results:\n")

    if not results:
        print("No results found.")
        return

    for r in results:
        preview = r[:120].replace("\n", " ")
        print(f"- {preview}...\n")


if __name__ == "__main__":
    main()