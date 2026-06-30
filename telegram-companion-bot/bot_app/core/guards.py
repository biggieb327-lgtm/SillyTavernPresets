from dataclasses import dataclass


@dataclass
class GuardResult:
    ok: bool
    reason: str = ""


class GuardService:
    def __init__(self, is_allowed_fn=None, rate_ok_fn=None):
        self.is_allowed_fn = is_allowed_fn
        self.rate_ok_fn = rate_ok_fn

    def check_user(self, user_id: int) -> GuardResult:
        if self.is_allowed_fn and not self.is_allowed_fn(user_id):
            return GuardResult(False, "unauthorized")
        if self.rate_ok_fn and not self.rate_ok_fn(user_id):
            return GuardResult(False, "rate_limited")
        return GuardResult(True, "")
