from collections import defaultdict


class IdeaGraph:

    def __init__(self, embedder, memory_manager):
        self.embedder = embedder
        self.memory = memory_manager

    def _memory_to_text(self, item):

        if isinstance(item, str):
            return item

        if isinstance(item, dict):
            content = item.get("content", "")
            summary = item.get("summary", "")

            if content and summary:
                return f"{summary}\n{content}"

            if content:
                return content

            if summary:
                return summary

            return str(item)

        return str(item)

    def build_clusters(self):

        memories = self.memory.get_recent_memories(limit=25)

        if not memories:
            return []

        memory_texts = []

        for item in memories:
            text = self._memory_to_text(item)

            if text and text.strip():
                memory_texts.append(text.strip())

        if not memory_texts:
            return []

        vectors = [self.embedder.embed(text) for text in memory_texts]

        clusters = defaultdict(list)

        for i, vector in enumerate(vectors):
            cluster_id = int(sum(vector[:5]) * 1000) % 5
            clusters[cluster_id].append(memory_texts[i])

        return list(clusters.values())