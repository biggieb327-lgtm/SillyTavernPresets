# baseline: the same call, correctly off-loop. Must stay clean.
import asyncio, requests
async def handler(update, context):
    r = await asyncio.to_thread(requests.get, "https://example.invalid/x")
    return r
