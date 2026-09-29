# Changelog

## 0.2.2 — Code writes the profile fields it knows; this repo becomes the canonical contract

- `build_profile` computed each file's label and word count but never used them: the
  model was asked to write `corpus` and `meta` itself, and the template showed
  `corpus.sources` as an empty list, so a model could omit `label` and fail validation
  on every retry (seen live in Author-Profile-Tool's port on 2026-09-29). The code now
  pre-fills `meta.author`, `meta.generated_at` and all of `corpus` in the template it
  sends, and overwrites them on the model's reply before validation.
- The profile prompt now states the exemplar minimums the schema enforces (3 signature
  sentences, 1 signature paragraph), which the empty template lists hid.
- `JUDGE_SYSTEM` used `{{ }}` although it is never passed through `str.format`, so the
  model saw doubled braces in its output format. Now single braces.
- The schema moved from a Python dict to `templates/voice_profile_schema.json` (loaded
  by `schemas.py`, same `VOICE_PROFILE_SCHEMA` object) so other tools can read it.
- README "Canonical source": prompts, template and schema here are the source of truth;
  Author-Profile-Tool vendors them.

## 0.2.1 — Clean API error reporting

- API connection failures, HTTP error statuses, and other OpenAI client errors
  now surface as one-line `Error: ...` messages instead of raw tracebacks
  (found during a live test: an unreachable endpoint dumped ~60 lines of
  httpx/openai traceback)

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
