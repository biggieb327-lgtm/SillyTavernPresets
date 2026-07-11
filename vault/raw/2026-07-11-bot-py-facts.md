# Raw capture: bot.py measured facts

Source: `telegram-companion-bot/bot.py` @ commit `d76dcdf`, measured with tools
2026-07-11 (not recalled).

- 9,494 lines (`wc -l`); `BOT_VERSION = "2026-07-11.6"` at line 84.
- Takes the instance directory as `sys.argv[1]`; heavy module-level init (reads
  .env, loads card) — tests need the conftest fixture to import it.
- Output choke point: `_do_request` applies `_strip_thinking` +
  `_strip_native_tool_calls` + `_fix_mojibake`; force-reads `resp.content` before
  `raise_for_status()` on streams.
- `audit_cmd` (line 8891 at capture) reports version, uptime, errors, state-file
  path, PID, memory review queue, LLM usage, config warnings, group budgets.
- Tests: `tests/test_pure.py`, 162 test functions; `tests/conftest.py` builds a
  temp fixture instance (fake .env + minimal chara_card_v2) before `import bot`.
- Model slots (.env): NANOGPT_MODEL `zai-org/glm-5:thinking`; SUMMARY/REACTION
  `glm-4.7-flash`; FALLBACK must be roleplay-capable (`anthracite-org/magnum-v4-72b`
  recommended); DOCUMENT must be instruction (`deepseek/deepseek-v4-flash`);
  VISION must be multimodal (`zai-org/glm-4.6v`). STREAM_TIMEOUT 90s,
  REQUEST_TIMEOUT 120s.
