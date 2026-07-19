# voicekit-starter

A CLI tool for extracting author voice profiles from writing samples, generating voice-matched drafts, and judging draft fidelity against a profile.

Uses structured JSON output with schema validation and automatic repair retries to produce reliable, machine-readable voice profiles from any writing corpus.

## Features

- **Profile extraction** from multiple files or an entire directory
- **Structured output** — profiles are validated JSON matching a strict schema
- **Validation-repair retries** — if the LLM output fails schema validation, the error is fed back as repair guidance and the model retries
- **Multi-file corpus support** — pass individual files, a directory, or both
- **Voice-matched generation** — produce drafts in a specific register using a profile
- **Draft judging** — score and revise drafts against a profile with actionable feedback

## Install

```bash
cd voicekit-starter
pip install -e .
```

Requires Python 3.10+ and an OpenAI-compatible API key:

```bash
export OPENAI_API_KEY="sk-..."
```

Optionally set a default model (falls back to `gpt-4.1-mini`):

```bash
export OPENAI_MODEL="gpt-4.1"
```

For local/alternative OpenAI-compatible servers (ollama, vLLM, LM Studio), set the base URL:

```bash
export OPENAI_BASE_URL="http://localhost:11434/v1"
```

## Usage

### Quick start

Point `build-profile` at your samples (files and/or directories) and give it an
author name — the profile lands in `<author>-profile.json`:

```bash
voicekit build-profile ./writing-samples/ --author "Jane Smith"
# Profile saved to jane-smith-profile.json
```

### Build a profile from multiple files

```bash
voicekit build-profile \
  --author "Jane Smith" \
  --samples essays/post1.md essays/post2.txt essays/post3.md \
  --out profiles/jane.json
```

### Build a profile from a directory

```bash
voicekit build-profile \
  --author "Jane Smith" \
  --samples-dir ./writing-samples/ \
  --out profiles/jane.json
```

### Increase retries for complex corpora

```bash
voicekit build-profile \
  --author "Jane Smith" \
  --samples-dir ./writing-samples/ \
  --out profiles/jane.json \
  --retries 5
```

### Add optional metadata

```bash
voicekit build-profile \
  --author "Jane Smith" \
  --samples-dir ./writing-samples/ \
  --out profiles/jane.json \
  --project-name "Blog Voice" \
  --source-type "blog posts" \
  --use-cases "newsletters, social threads"
```

### Generate a draft

```bash
voicekit generate \
  --profile profiles/jane.json \
  --task-file briefs/announcement.md \
  --facts-file briefs/facts.txt \
  --register email \
  --out drafts/announcement-email.md
```

`--facts-file` is optional — without it the draft uses only facts stated in the
task/brief. `--out` is optional too; omit it to print the draft to stdout:

```bash
voicekit generate --profile profiles/jane.json --task-file briefs/announcement.md --register email
```

### Judge a draft

```bash
voicekit judge \
  --profile profiles/jane.json \
  --draft-file drafts/announcement-email.md \
  --register email
```

Prints a score summary and top revision priorities, and saves the full
evaluation to `<draft>-eval.json` next to the draft (override with `--out`).

## How it works

1. **build-profile** reads your writing samples, builds a labeled corpus, and asks the LLM to fill a structured voice profile template. The output is validated against a JSON schema; failures trigger automatic repair retries with the validation error included in the prompt.

2. **generate** takes a profile, a task brief, a facts file, and a target register, then produces a voice-matched draft that prioritizes factual accuracy and deep voice traits over surface quirks.

3. **judge** scores a draft on rhythm, lexicon, stance, rhetoric, and constraint compliance, then produces a diagnosis, revision priorities, and a full revised draft.

## Supported file types

Sample files must have one of these extensions: `.txt`, `.md`, `.markdown`

## Project layout

```
voicekit-starter/
  pyproject.toml
  README.md
  src/
    voicekit/
      __init__.py
      cli.py        # CLI argument parsing
      core.py       # Runtime logic (API calls, validation, file I/O)
      prompts.py    # System and user prompt templates
      schemas.py    # JSON schema for profile validation
      templates/
        voice_profile_template.json
```

## License

MIT
