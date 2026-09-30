# Changelog

## 0.4.0 — Voice kept apart from subject matter

- A profile built from two short stories (Author-Profile-Tool, 2026-09-30) put the
  stories' theme into `constraints.hard_rules` ("Focus on the psychological interplay
  between jealousy and arousal"). Nothing in the builder told the model to separate
  how an author writes from what the samples were about, so the generator would pull
  every draft back to that theme and the judge would mark down an on-voice draft about
  something else.
- New optional `subject_matter` block (`themes`, `notes`) in the template and schema.
  `PROFILE_BUILDER_SYSTEM` now says the voice sections must hold for any topic and that
  themes, recurring situations, settings and character types go only in
  `subject_matter`. Optional in the schema, so profiles built before 0.4.0 still
  validate.
- `voice_only()` drops `subject_matter` from the profile sent to the judge and the
  reviser (always), and to the generator unless `generate --themes`
  (`use_subject_matter=True`). `JUDGE_SYSTEM` adds: judge the voice, not the topic.

## 0.3.0 — Separate judge model; the rewrite is its own step

- `JUDGE_SYSTEM` asked for scores, a diagnosis, priorities and a full rewrite in one
  JSON reply. Live (Author-Profile-Tool, 2026-09-29) the rewrite of an 8.7/10 essay
  applied almost none of the judge's own three priorities: it added two "and"s and a
  dash. The judge no longer writes a rewrite. `REVISER_SYSTEM` / `REVISER_USER` are a
  separate call that takes the diagnosis and numbered priorities and must apply each
  one visibly. `judge --revise` runs it (temperature 0.7, on `OPENAI_MODEL`) and stores
  the result as `revised_draft`. **Behavior change:** without `--revise` the
  evaluation has no `revised_draft`.
- The judge ran on the same model as the writer, which tends to rate its own drafts
  high. `VOICEKIT_JUDGE_MODEL` (via `get_judge_model`) sets a separate judge model;
  `judge --model` still overrides it. The evaluation records `judge_model`, and the
  CLI prints it.

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
