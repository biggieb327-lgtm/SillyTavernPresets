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

## Verification trace — what does this check actually measure?

This is the repo's two highest-seen constraints in one place: C8 ("ask what a
reading actually measures before concluding from it") and C13 ("a verification
command that cannot fail is not verification"). Before trusting any command in the
gates above, trace it backward from its output to what it actually checks:

1. **What does this command measure?** Not what it claims to measure — trace the
   actual code path. `py_compile` parses syntax; it does not import the module or
   run a line of it.
2. **Can this command fail for the reason I care about?** A `py_compile` cannot
   catch a `NameError`. A `grep` for a string cannot tell you whether the string
   does what the docs say it does. If the failure mode you're worried about can't
   flip this command's exit code, this command isn't checking for it.
3. **What would this command look like if the thing I care about were broken?** If
   the honest answer is "identical to what I'm looking at right now," the command
   is not a discriminator — it's decoration.

Two from this repo's own history:

- 12 of 15 evals reported PASS against a dead parser, because they captured stdout
  only and empty stdout satisfied the check — the parser had stopped producing
  output entirely (C13 occurrence 9).
- `py_compile` reported "ok" on a module that could not actually import, because
  `_env_int` was called 120 lines above its own definition — a syntax-valid,
  import-broken file (C13 occurrence 7).

When a check can't discriminate between working and broken, don't report it as
verification of the thing you care about. Either fix the check so it can fail for
that reason, or say explicitly in your report what it does NOT cover.

If any gate fails: fix and re-run all gates. Never report partial verification as done.
