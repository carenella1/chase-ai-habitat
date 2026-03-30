from habitat.agents.chatgpt_history_importer import ChatGPTHistoryImporter

SOURCE_DIR = "knowledge_sources/chatgpt_history"


def main():

    print("Starting ChatGPT history import...\n")

    importer = ChatGPTHistoryImporter()

    imported = importer.import_directory(SOURCE_DIR)

    print("\n=================================")
    print("ChatGPT history import complete.")
    print("Total entries imported:", imported)
    print("=================================")


if __name__ == "__main__":
    main()