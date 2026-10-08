#!/usr/bin/env bash
# shell-semantics-guard.sh — PreToolUse(Bash). Constraint C23: the shell evaluated
# something the command text does not show.
#
# Two shapes, both seen the same day, both mechanically visible:
#
#   1. A `||` fallback whose left side ends in a PIPE. `||` tests the exit status of the
#      LAST stage, so `grep X f | cut -d= -f2- || echo '(absent)'` tests `cut` — which
#      returns 0 whether or not grep matched. The fallback can never fire, and "absent"
#      renders identically to "empty". Shipped three times on 2026-08-10, twice into
#      command blocks handed to the owner, once after the corrected form had already been
#      written and explained.
#
#   2. `git commit -m` carrying a backtick or `$(`. Inside double quotes both execute.
#      On 2026-08-10 a commit message containing `git show HEAD:` ran it and pasted a repo
#      directory listing into the commit body; several backticked identifiers vanished.
#      `-F <file>` had been adopted as the fix four commits earlier.
#
#   3. `git push|commit|merge` after `&&` on a PIPELINE (`run-evals.sh | tail -1 && git
#      push`). The gate tests the last stage, so a failing check still pushes. Reached
#      main on 2026-09-29 (C23 occurrence 8). Blocking; a final `grep` stage or
#      `set -o pipefail` is honest and allowed. Cases: the `shell-semantics-cases` eval.
#
# NOT guarded, deliberately: relative paths under a stale `cd` (C23's third shape). A
# relative path is correct far more often than not, and a hook that fired on every one
# would be switched off within a day. That half stays prose, inside C13.
#
# Advisory by design for shape 1 (a `|| true` after a pipe is a legitimate idiom) and
# blocking for shape 2 (there is no reason to want command substitution in a commit
# message). Escape hatch for both: `# shell-ok`.
set -u

payload=$(cat)
cmd=$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
print((d.get("tool_input") or {}).get("command", ""))
' 2>/dev/null) || exit 0

[ -n "${cmd}" ] || exit 0
printf '%s' "$cmd" | grep -q '# *shell-ok' && exit 0

# --- shape 2: command substitution inside a -m message (blocking) ---------------------
if printf '%s' "$cmd" | grep -qE 'git +commit[^|;]*-m +"' \
   && printf '%s' "$cmd" | grep -qE 'git +commit[^|;]*-m +"[^"]*(`|\$\()'; then
  cat >&2 <<'MSG'
[shell-semantics] BLOCKED: constraint C23 — `git commit -m "…"` containing a backtick or $(…).

Inside double quotes the shell EXECUTES those before git ever sees them. On 2026-08-10
this ran `git show HEAD:` and pasted a repo directory listing into the commit message.

Use a file instead — it cannot interpolate:
    git commit -F - <<'MSG'
    subject line

    body with `backticks` and $(parens) intact
    MSG

Add `# shell-ok` if the substitution is genuinely intended.
MSG
  exit 2
fi

# --- shape 3: a commit/push/merge gated on a pipeline's status (blocking) ---------------
# `run-evals.sh | tail -1 && git push` gates the push on `tail`, which returns 0 whatever
# the evals did. On 2026-09-29 a failing eval did not stop exactly that chain and red
# reached main (C23 occurrence 8). A pipeline ending in `grep` is honest — grep's status
# says whether it matched — and `set -o pipefail` makes any pipeline honest.
gate=$(printf '%s' "$cmd" | python3 -c '
import re, sys
cmd = sys.stdin.read()
if "pipefail" in cmd:
    sys.exit(0)
# Heredoc bodies and quoted strings are data, not commands.
lines, out, end = cmd.split("\n"), [], None
for ln in lines:
    if end is not None:
        if ln.strip() == end:
            end = None
        continue
    m = re.search(r"<<-?\s*[\x27\"]?(\w+)[\x27\"]?", ln)
    if m:
        end = m.group(1)
    out.append(ln)
text = "\n".join(out)
text = re.sub(r"\x27[^\x27]*\x27|\"(?:\\.|[^\"\\])*\"", " ", text)
text = re.sub(r"(\||&&|\\)[ \t]*\n", r"\1 ", text)          # line continuations
ACTION = re.compile(r"^(?:\S+=\S*\s+)*git\s+(push|commit|merge)\b")
for line in text.split("\n"):
    tainted, stages = False, []
    for tok in re.split(r"(\|\||&&|;|\||\bdo\b|\bthen\b)", line):
        t = tok.strip()
        if t == "|":
            continue
        if t in ("||", ";", "do", "then"):
            tainted, stages = False, []
            continue
        if t == "&&":
            if len(stages) >= 2 and not re.match(r"^grep\b", stages[-1]):
                tainted = True
            stages = []
            continue
        if not t:
            continue
        m = ACTION.match(t)
        if tainted and m:
            print(m.group(1)); sys.exit(0)
        stages.append(t)
' 2>/dev/null)
if [ -n "$gate" ]; then
  cat >&2 <<MSG
[shell-semantics] BLOCKED: constraint C23 — \`git $gate\` is gated on a PIPELINE.

\`A | tail -1 && git $gate\` tests \`tail\`, which exits 0 whatever A did. On 2026-09-29
\`run-evals.sh | tail -1 && git push origin HEAD:main\` pushed a red eval run to main.

Make the gate test the command you mean:
    bash .claude/evals/run-evals.sh | grep -q 'failed, 0' && git $gate ...   # grep is the test
    set -o pipefail; bash .claude/evals/run-evals.sh | tail -1 && git $gate ...
or run the check, read it, and $gate in a separate step.
Add \`# shell-ok\` if the pipeline's status genuinely does not matter.
MSG
  exit 2
fi

# --- shape 1: a `||` fallback after a pipe (advisory) ---------------------------------
if printf '%s' "$cmd" | grep -qE '\|[^|]+\|\|'; then
  cat >&2 <<'MSG'
[shell-semantics] WARNING: constraint C23 — a `||` fallback after a pipe tests the LAST
stage of the pipeline, not the command you probably mean.

  grep X f | cut -d= -f2- || echo '(absent)'      # tests `cut`, which returns 0 either
                                                  # way — the fallback can never fire

Put the test on the command you mean:
  if grep -q X f; then grep X f | cut -d= -f2-; else echo '(absent)'; fi

Shipped three times on 2026-08-10, twice inside command blocks handed to the owner.
Advisory only — `| … || true` is a legitimate idiom. Add `# shell-ok` to silence.
MSG
fi
exit 0
