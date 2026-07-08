# Contributing

Contributions are welcome. Keep changes focused and minimal.

## Setup

```bash
cd voicekit-starter
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Guidelines

- Keep code readable and compact
- Use `pathlib` for file operations
- No unnecessary frameworks or dependencies
- All LLM output must be schema-validated before saving
- Preserve the modular layout: CLI in `cli.py`, logic in `core.py`, prompts in `prompts.py`, schemas in `schemas.py`

## Pull requests

- One logical change per PR
- Include a clear description of what and why
- Verify the CLI still works end-to-end before submitting
