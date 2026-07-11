# Raw capture: GROUP_CHAT_DESIGN.md

Source: `telegram-companion-bot/GROUP_CHAT_DESIGN.md` @ commit `d76dcdf`.

Section map: §0 platform constraint · §1 message flow/shared ledger · §2 turn-taking
· §3 loop prevention · §4 cost · §5 memory semantics · §6 safety/access control ·
§7 prompt/delivery changes · §8 configuration · §9 out of scope for v1 ·
§10 rollout/acceptance · §11 monitoring · §12 durable enforcement.

Core constraint (§0): Telegram never delivers one bot's messages to another bot —
bot-to-bot conversation runs on a shared flock'd ledger + atomic claim files on the
same filesystem.

Config posture (from CLAUDE.md summary of §6/§8): fleet-wide default is groups
ignored (only `/chatid` answers); enable per-instance with `GROUP_MODE=1` +
`GROUP_ALLOWED_CHATS` (fail closed) + `GROUP_PEERS`; loop caps
`GROUP_BOT_CHAIN_MAX=2`, `GROUP_DAILY_BOT_BUDGET=30`. Pilot pair: priya + jules.
One-time on-device check: `python bot.py ~/priya-bot --claim-test` (two PASS lines).

History: design revised through four adversarial review rounds (commits 6a14caf →
f64573e); rounds 1–2 each found a flat-file write path a hand-kept inventory missed.
