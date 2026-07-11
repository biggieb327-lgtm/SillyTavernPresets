# voicekit-starter — separate CLI project

Author-voice profiling CLI sharing the repo but none of the bot's rules: extracts
voice profiles from writing samples, generates voice-matched drafts, judges
fidelity ([raw/2026-07-11-voicekit.md]).

- src/ layout, entry point `voicekit`, deps openai + jsonschema, own CHANGELOG and
  version (0.1.0) ([raw/2026-07-11-voicekit.md]).
- Design center: schema-validated JSON output with validation-repair retries; the
  schema, template, and repair prompts form one contract in three files
  ([raw/2026-07-11-voicekit.md]).
- No test suite (verified 2026-07-11); verification is py_compile + CLI --help +
  template JSON parse ([raw/2026-07-11-voicekit.md]).
- Owner confirmed in scope for Claude work (2026-07-11 session Q&A).
