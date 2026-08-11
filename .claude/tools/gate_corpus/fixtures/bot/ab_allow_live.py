# The allowlisted shape, with its guard intact: triggered_memories checks the running
# loop before the blocking branch, so the async caller is safe. Must stay clean.
import asyncio, requests
def triggered_memories(scan_text, query_vec=None):
    if query_vec:
        return []
    try:
        asyncio.get_running_loop()
        return []            # on the loop: skip the blocking embed
    except RuntimeError:
        return requests.get("https://example.invalid/x", timeout=5)
def assemble_messages(chat_id, text):
    return triggered_memories(text)
async def handler(update, context):
    return assemble_messages(1, "x")
