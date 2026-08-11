# THE case the first draft of the scanner missed (2026-08-11): bot.py never calls a
# primitive from an async def — it calls a sync WRAPPER that does the I/O internally.
# A scanner matching only primitive names reports a confident 0 here.
import requests
def _fetch_thing():
    return requests.get("https://example.invalid/x", timeout=5)
async def handler(update, context):
    return _fetch_thing()
