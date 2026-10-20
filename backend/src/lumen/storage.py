"""Original uploaded files, kept on local disk and named by document id."""

import uuid
from pathlib import Path


class FileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def path_for(self, document_id: uuid.UUID) -> Path:
        # The id is a UUID, so user input never reaches the file system path.
        return self.root / str(document_id)

    def save(self, document_id: uuid.UUID, data: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path_for(document_id).write_bytes(data)

    def read(self, document_id: uuid.UUID) -> bytes:
        return self.path_for(document_id).read_bytes()

    def delete(self, document_id: uuid.UUID) -> None:
        self.path_for(document_id).unlink(missing_ok=True)
