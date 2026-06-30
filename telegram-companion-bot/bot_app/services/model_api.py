from dataclasses import dataclass
from typing import List, Dict


@dataclass
class ModelReply:
    text: str
    action: dict


class ModelService:
    def build_messages(self, system_blocks: List[str], history: List[Dict], user_text: str) -> List[Dict]:
        messages = []
        for block in system_blocks:
            if block:
                messages.append({"role": "system", "content": block})
        for item in history[-12:]:
            messages.append({"role": item["role"], "content": item["content"]})
        messages.append({"role": "user", "content": user_text})
        return messages

    def request_reply(self, messages: List[Dict]) -> ModelReply:
        return ModelReply(
            text="Stub reply from migration starter.",
            action={"action": "none", "query": None},
        )
