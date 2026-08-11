# Same shape with the runtime guard REMOVED. The exemption is now hiding a real
# violation, and the scanner must say so rather than stay quiet.
import requests
def triggered_memories(scan_text, query_vec=None):
    return requests.get("https://example.invalid/x", timeout=5)
def assemble_messages(chat_id, text):
    return triggered_memories(text)
async def handler(update, context):
    return assemble_messages(1, "x")
