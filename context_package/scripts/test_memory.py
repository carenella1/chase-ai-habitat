from habitat.memory.memory_manager import MemoryManager


def main():
    memory = MemoryManager()
    items = memory.fetch_recent()

    print("\nRecent Habitat Memories:\n")

    if not items:
        print("No memories found.")
        return

    for m in items:
        preview = m[:120].replace("\n", " ")
        print(f"- {preview}...\n")


if __name__ == "__main__":
    main()