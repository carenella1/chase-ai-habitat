from pathlib import Path


class FileReader:

    SUPPORTED_TYPES = [".txt", ".md", ".py", ".json"]

    def read_directory(self, directory):

        directory = Path(directory)

        documents = []

        for file in directory.rglob("*"):

            if file.suffix.lower() in self.SUPPORTED_TYPES:

                try:

                    content = file.read_text(encoding="utf-8")

                    documents.append(
                        {
                            "path": str(file),
                            "content": content
                        }
                    )

                except Exception:
                    pass

        return documents