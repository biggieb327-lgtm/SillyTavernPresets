# Changelog

## 0.2.0 — Usability

All existing flags and invocations keep working; changes are additive.

- `build-profile` accepts positional paths (files and/or directories):
  `voicekit build-profile ./samples/ --author "Jane Smith"`
- `build-profile --out` is now optional (defaults to `<author>-profile.json`)
- `generate --facts-file` is now optional (drafts fall back to facts stated in the task/brief)
- `generate --out` is now optional (draft prints to stdout when omitted)
- `judge --out` is now optional (defaults to `<draft>-eval.json` next to the draft)
- `judge` prints a score summary and top revision priorities to the terminal
- Progress messages on stderr (corpus size, model + attempt counter, retry notices)
- A nonexistent `--samples-dir` is now a clear error instead of being silently ignored;
  directories with no supported files are reported
- Friendlier missing-`OPENAI_API_KEY` error with setup hint; input files are
  validated before the API key is required, so path typos surface first
- `voicekit --version`; `--help` epilogs show worked examples

## 0.1.0 — Initial release

- `build-profile` command: corpus ingestion, structured JSON extraction, schema validation, repair retries
- `generate` command: voice-matched draft generation with register targeting
- `judge` command: fidelity scoring, diagnosis, revision priorities, and revised draft output
- Multi-file and directory-based corpus support
- JSON schema validation with automatic repair retry loop
- Console script entry point (`voicekit`)
