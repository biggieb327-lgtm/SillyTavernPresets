Verification rules that apply to every change in this repo.

## Test command

```
pytest telegram-companion-bot/tests -q
```

Full verification (compile + pytest + evals + gate corpus + advisory sweep):

```
bash .claude/tools/verify.sh
```

Evals only: `bash .claude/evals/run-evals.sh`.

## Verification loop

After every change, run the test command and read its output. If any check
fails, fix the cause and re-run, because a fix can introduce a new failure.
Do not report done until the full suite is green. A second run after a fix
confirms it didn't break something else.

## Evidence standard

Paste the actual command and its actual output. "The code looks right" is
not evidence, because it conflates reading with running. A test you didn't
run is not a passing test.

Never summarize over a red run, because the specific failure output is what
the next person needs to diagnose the problem.
