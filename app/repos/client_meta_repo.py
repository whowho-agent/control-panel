import json
from pathlib import Path


class ClientMetaRepo:
    def __init__(self, meta_path: str) -> None:
        self.meta_path = Path(meta_path)

    def read(self) -> dict:
        if not self.meta_path.exists():
            return {"clients": {}}
        raw = self.meta_path.read_text()
        if not raw.strip():
            return {"clients": {}}
        if raw.endswith("\\n"):
            raw = raw[:-2] + "\n"
        return json.loads(raw)

    def write(self, meta: dict) -> None:
        self.meta_path.write_text(json.dumps(meta, indent=2) + "\n")
