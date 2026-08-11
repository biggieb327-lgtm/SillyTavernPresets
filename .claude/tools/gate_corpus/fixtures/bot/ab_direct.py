# baseline: a blocking primitive called straight from an async def.
import requests
async def handler(update, context):
    r = requests.get("https://example.invalid/x", timeout=5)
    return r
