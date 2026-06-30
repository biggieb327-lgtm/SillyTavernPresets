from dataclasses import dataclass
from typing import Optional


ALLOWED_ACTIONS = {"none", "search"}


@dataclass
class ActionRequest:
    action: str = "none"
    query: Optional[str] = None

    def valid(self) -> bool:
        if self.action not in ALLOWED_ACTIONS:
            return False
        if self.action == "search":
            return bool(self.query and len(self.query) <= 160)
        return True
