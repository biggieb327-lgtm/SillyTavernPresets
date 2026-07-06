"""Set up a fixture environment so bot.py can be imported without a real instance."""
import json
import os
import sys
import tempfile
from pathlib import Path

# Create a minimal fixture directory BEFORE bot.py gets imported anywhere.
# bot.py runs heavy module-level init: reads .env, loads the character card,
# sets up logging. This must all succeed for the pure-function tests to work.

_fixture_dir = tempfile.mkdtemp(prefix="bot_test_")

# Minimal .env — just enough to pass the startup guards.
(Path(_fixture_dir) / ".env").write_text(
    "TELEGRAM_BOT_TOKEN=test:fake-token-for-pytest\n"
    "NANOGPT_API_KEY=test-fake-key-for-pytest\n"
    "CHARACTER_CARD=test_card.json\n"
    "BOT_TIMEZONE=America/New_York\n"
)

# Minimal SillyTavern v2 character card.
(Path(_fixture_dir) / "test_card.json").write_text(json.dumps({
    "spec": "chara_card_v2",
    "spec_version": "2.0",
    "data": {
        "name": "TestBot",
        "description": "A test character.",
        "personality": "Helpful.",
        "scenario": "",
        "first_mes": "Hello!",
        "mes_example": "",
        "system_prompt": "You are TestBot.",
        "post_history_instructions": "",
        "creator_notes": "",
        "character_book": {"entries": []},
    },
}))

# bot.py uses `sys.argv[1]` as the instance directory before checking BOT_HOME.
# pytest puts its own arguments in sys.argv, so we must override argv[1] to
# point at the fixture dir, then restore it after bot.py's module-level code runs.
_orig_argv = sys.argv[:]
sys.argv = [sys.argv[0], _fixture_dir]
os.environ["BOT_HOME"] = _fixture_dir

# Ensure the bot source directory is on sys.path so `import bot` works.
_bot_dir = str(Path(__file__).resolve().parent.parent)
if _bot_dir not in sys.path:
    sys.path.insert(0, _bot_dir)
