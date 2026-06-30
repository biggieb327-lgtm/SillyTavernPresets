from dataclasses import dataclass
from typing import Optional


# Allowlist of action types the model is permitted to request via inline tags. Anything outside
# this set is rejected before any side effect runs, so a stray/unknown tag can never be executed.
ALLOWED_ACTIONS = {"none", "react", "selfie", "search"}

# Per-action bounds. Generous on purpose — these catch anomalous/oversized model output, not
# legitimate requests, so a real reaction/selfie/search is never rejected.
MAX_SEARCH_QUERY = 200   # web-search query (chars)
MAX_SELFIE_HINT = 500    # selfie scene description (chars); empty string allowed (generic selfie)
MAX_REACT = 16           # a single emoji, possibly multi-codepoint (chars)


@dataclass
class ActionRequest:
    action: str = "none"
    query: Optional[str] = None

    def valid(self) -> bool:
        if self.action not in ALLOWED_ACTIONS:
            return False
        if self.action == "search":
            return bool(self.query) and len(self.query) <= MAX_SEARCH_QUERY
        if self.action == "selfie":
            return self.query is not None and len(self.query) <= MAX_SELFIE_HINT
        if self.action == "react":
            return bool(self.query) and len(self.query) <= MAX_REACT
        return True  # "none"
