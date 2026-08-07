# gate_corpus — the guards, guarded

`sweep.py`'s scanners and `delivery-gate.sh`'s handler-coverage check are pattern
matchers. A pattern matcher nobody has run against input designed to slip past it is not
a guard; it is a hope with a regex in it. This is that input.

Run it:

```bash
python3 .claude/tools/gate_corpus/run.py        # all cases
python3 .claude/tools/gate_corpus/run.py -v     # show passing cases too
python3 .claude/tools/gate_corpus/run.py constraints-drift
```

Exit 1 on any deviation. `run-evals.sh` runs it as the `gate-corpus` eval, so CI fails
when a guard stops guarding — including when `sweep.py` stops parsing.

## What a case is

One case pins one **pattern-matching assumption** to an exact outcome:

- `expect="hit"` — the scanner must report a finding containing `match`
- `expect="clean"` — the scanner must report nothing

Every case names the assumption it probes in its `probes=` field. If you cannot say
which assumption a case tests, it is not a case, it is a mood.

Scanners run in a **subprocess** with `SWEEP_BOT` / `SWEEP_TESTS` / `SWEEP_CONSTRAINTS` /
`SWEEP_ENV` / `SWEEP_TODAY` pointed at fixtures — `sweep.py` resolves those at import
time, so in-process runs would leak the first case's paths into every later one. The
delivery gate runs **end to end** against a throwaway git repo, because its input is a
real `git diff`.

## Adding a case

1. Write the fixture under `fixtures/<kind>/`. Bot fixtures must parse as Python.
2. Add a `dict(...)` to `CASES` (or `GATE_CASES` / `DIFF_CASES`) naming the assumption.
3. Run it and watch it **fail** before you fix anything. A case that passes against the
   unfixed scanner is measuring nothing — two of the first batch did exactly that, and
   both turned up real defects once rewritten to discriminate.

## What this found on 2026-08-02

14 of the first 34 cases deviated. The two that mattered most:

- **The delivery gate failed open.** Check 4 piped stderr to `/dev/null` and ignored the
  exit status, so anything that made `sweep` raise — an unparseable `bot.py` or test
  file, a missing path — produced an empty result indistinguishable from "no unexercised
  handlers". It now reports the check as *unmet*.
- **`constraints-drift` invented entries.** The `## Minor` split was not line-anchored,
  so prose naming the heading mid-sentence turned dated bullets inside constraint bodies
  into Minor-log entries; a second unanchored read let prose quoting an old date
  manufacture a 14-entry backlog.

The rest were escapes (single-quoted `parse_mode`, f-strings built more than seven lines
above their call, `{n:>3}` format specs, multi-line `__file__` assignments,
`from bot import x`, `os.environ.get`, hints split across string literals, `*` bullets)
and false positives (`str.replace()` read as `Path.replace()`, two-character env names,
the `_pkg_hint` definition flagged as a hardcoded hint).

Five further mutations were invented **after** those fixes to check for overfitting.
Four passed; `sw-tuple-target` did not, and `CODE_DIR, VERSION = Path(__file__).parent, "1"`
turned out to define a shared name the fixed scanner still could not see.
