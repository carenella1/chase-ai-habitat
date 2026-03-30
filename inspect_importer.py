from habitat.agents.chatgpt_history_importer import ChatGPTHistoryImporter

print("Methods on ChatGPTHistoryImporter:\n")

for attr in dir(ChatGPTHistoryImporter):
    if not attr.startswith("__"):
        print(attr)