# A blocking call with no async caller is not a violation — nothing is being blocked.
# Guards against the scanner flagging every sync helper in the file.
import requests
def _fetch_thing():
    return requests.get("https://example.invalid/x", timeout=5)
def caller():
    return _fetch_thing()
