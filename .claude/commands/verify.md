Run the full verification block: compile, pytest, evals, gate corpus, and
the advisory sweep.

```bash
bash .claude/tools/verify.sh
```

Use `--quick` to drop the advisory sweep (not sufficient for a release).
Report the output — never summarize over a red run.
