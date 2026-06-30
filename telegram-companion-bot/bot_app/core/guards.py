from dataclasses import dataclass


@dataclass
class GuardResult:
    ok: bool
    reason: str = ""


class GuardService:
    def __init__(self, is_allowed_fn=None, rate_ok_fn=None):
        self.is_allowed_fn = is_allowed_fn
        self.rate_ok_fn = rate_ok_fn

    def check_user(self, user_id: int, rate_limit: bool = True) -> GuardResult:
        if self.is_allowed_fn and not self.is_allowed_fn(user_id):
            return GuardResult(False, "unauthorized")
        # rate_ok_fn has a side effect (it records the request time), so only call it when this
        # call site actually rate-limits — auth-only handlers must not consume a rate slot.
        if rate_limit and self.rate_ok_fn and not self.rate_ok_fn(user_id):
            return GuardResult(False, "rate_limited")
        return GuardResult(True, "")
