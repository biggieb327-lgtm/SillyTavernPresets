"""JSON schema for voice profile validation.

The schema lives in templates/voice_profile_schema.json, next to the template it
describes, so tools in other languages can read the same file (Author-Profile-Tool
vendors it; see README "Canonical source").
"""

import importlib.resources
import json

VOICE_PROFILE_SCHEMA = json.loads(
    importlib.resources.files("voicekit")
    .joinpath("templates/voice_profile_schema.json")
    .read_text(encoding="utf-8")
)
