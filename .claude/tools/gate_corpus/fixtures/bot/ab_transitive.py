# Depth 2: a wrapper of a wrapper. Pins the fixpoint — a single-pass resolver stops
# at _outer and misses this.
import requests
def _inner():
    return requests.get("https://example.invalid/x", timeout=5)
def _outer():
    return _inner()
async def handler(update, context):
    return _outer()
