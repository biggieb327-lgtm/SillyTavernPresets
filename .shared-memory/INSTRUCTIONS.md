# Project shared memory

This project uses `.shared-memory/` for project-local memory and edit coordination.

## Project shared memory

This repo has project-local shared memory in `.shared-memory/`.

- Use project memory for repo-specific facts, TODOs, decisions, and handoffs.
- Use global memory only for user-wide preferences or cross-project context.
- Never store API keys, tokens, passwords, cookies, private keys, `.env` values, authorization headers, or credential-bearing URLs. Save only environment-variable names or `[REDACTED]`, and never edit `memory.json` directly.
- Use the project activity board for edit coordination:
  - `shared-agent-memory claim <files> --as <agent> --note "<task>"`
  - `shared-agent-memory board`
  - `shared-agent-memory release --as <agent>`
- If your AI tool does not automatically read this file, ask it to read `.shared-memory/INSTRUCTIONS.md` before working in this repo.
