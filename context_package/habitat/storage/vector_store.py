from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import uuid

# Global shared client
_qdrant_client = None


class VectorStore:

    def __init__(self):

        global _qdrant_client

        if _qdrant_client is None:
            _qdrant_client = QdrantClient(path="data/vector_store")

        self.client = _qdrant_client

        self.collection_name = "habitat_memory"

        self._ensure_collection()

    def _ensure_collection(self):

        collections = [c.name for c in self.client.get_collections().collections]

        if self.collection_name not in collections:

            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=384,
                    distance=Distance.COSINE
                )
            )

    def store(self, vector, content):

        point = PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={"content": content}
        )

        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )

    def search(self, vector, limit=5):

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=vector,
            limit=limit
        )

        return [r.payload["content"] for r in results]