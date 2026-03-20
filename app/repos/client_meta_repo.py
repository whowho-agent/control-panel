import json
from pathlib import Path


class ClientMetaRepo:
    def __init__(self, meta_path: str) -> None:
        self.meta_path = Path(meta_path)

    def read(self) -> dict:
        if not self.meta_path.exists():
            return {"clients": {}}
        return json.loads(self.meta_path.read_text())

    def write(self, meta: dict) -> None:
        self.meta_path.write_text(json.dumps(meta, indent=2) + "\n")
