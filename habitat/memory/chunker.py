class Chunker:

    def chunk_text(self, text, size=500):

        chunks = []

        for i in range(0, len(text), size):

            chunk = text[i:i + size]

            chunks.append(chunk)

        return chunks