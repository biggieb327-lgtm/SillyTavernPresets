# The wrapper, correctly off-loop. Must stay clean, or the scanner flags every real
# call site in bot.py and becomes noise nobody reads.
import asyncio, requests
def _fetch_thing():
    return requests.get("https://example.invalid/x", timeout=5)
async def handler(update, context):
    return await asyncio.to_thread(_fetch_thing)
