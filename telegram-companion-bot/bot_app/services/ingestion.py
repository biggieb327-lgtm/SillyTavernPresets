import json


class IngestionService:
    def parse_json_bytes(self, raw_bytes: bytes):
        data = json.loads(raw_bytes.decode("utf-8"))
        return data

    def summarize_document(self, filename: str, data) -> str:
        return f"Imported JSON document: {filename}"
