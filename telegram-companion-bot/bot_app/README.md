# Bot refactor starter

This is a broader migration starter for replacing the single-file `bot.py` with a modular architecture.

## Goals
- Centralize auth, rate limiting, and error handling.
- Separate trusted memory, recent chat, and untrusted attachment-derived notes.
- Replace model-emitted regex actions with explicit allowlisted action requests.
- Isolate document/media ingestion from reply generation.
- Make handler-by-handler migration possible without keeping security-critical logic scattered.

## Suggested migration order
1. `core/config.py` and `core/guards.py`
2. `services/memory.py`
3. `services/model_api.py`
4. `services/action_schema.py`
5. `handlers/chat.py`
6. `handlers/documents.py`, `handlers/media.py`
7. Remaining commands migrated one by one

## Notes
- This starter is intentionally conservative: unsafe side effects are off by default.
- It is a migration base, not a drop-in replacement for every command from the original file.
