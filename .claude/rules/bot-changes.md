Rules for changes under `telegram-companion-bot/`.

## Change requirements

Every `bot.py` change requires all three, because the delivery gate hook blocks
the turn otherwise:

1. **`BOT_VERSION` bump** — so `/audit` proves a deploy landed.
2. **`CHANGELOG.md` entry** (root cause first) — so the next session knows what was
   tried and why.
3. **Compile evidence** (`python3 -m py_compile bot.py`) — so syntax errors never
   reach the fleet.

Read `CHANGELOG.md` before editing `bot.py`, because it records root causes of
every shipped fix. Skip only for pure content edits.

## Testing

Test command: `pytest telegram-companion-bot/tests -q`

A test must call any `*_cmd` handler the diff touches, because asserting on source
text is not a test — the `/features` `ValueError` of 2026-08-02 shipped past two
rounds of such tests.

## Deployment

Deploy via `deploy/vps-sync.sh <instance>`, because the repo is private and raw
URLs 404. The `deploy-and-verify-fleet` skill has the full procedure.

## Architecture constraints

- `bot.py` stays a single file, because the deploy model depends on it.
- `preset.txt` feeds all seven bots — editing it is a fleet-wide change.
- Emily runs `zai-org/glm-4.7:thinking` deliberately, not glm-5.
