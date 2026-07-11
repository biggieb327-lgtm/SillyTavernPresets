---
name: repo-validation-gate
description: Prove a change works with executed evidence before calling it done. Use before claiming completion of any change.
---

"Done" is a claim about the world; back it with the world's testimony.

Before reporting any change complete:

1. **Compile/parse gate.** Python: `python -m py_compile <file>`. JSON (character cards, settings): `python -m json.tool <file> > /dev/null`. Shell: `bash -n <file>`.
2. **Behavior gate.** Exercise the changed path, not just its syntax. If it can't be exercised here (phone-only behavior), say so explicitly and name what was verified instead.
3. **Regression gate.** Run `.claude/evals/run-evals.sh` — it pins this project's past incidents.
4. **Repo-rule gate** (bot changes only): `BOT_VERSION` bumped, `CHANGELOG.md` entry added with root cause. The delivery-gate hook blocks on this, but check before it has to.
5. Report with the actual output pasted, not a summary of what the output would be. A verification you didn't run is a guess wearing a lab coat.

If any gate fails: fix and re-run all gates. Never report partial verification as done.
