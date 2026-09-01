#!/usr/bin/env bash
# Regression evals — each one pins a real incident from this project's history so it
# fails loudly if the mistake is ever reintroduced. See README.md for the discipline.
# Usage: bash .claude/evals/run-evals.sh   (exit 0 = all PASS, exit 1 = any FAIL)
set -u
cd "$(dirname "$0")/../.." || exit 1

pass=0; fail=0; skipped=0
ok()  { echo "PASS  $1"; pass=$((pass+1)); }
bad() { echo "FAIL  $1 — $2"; fail=$((fail+1)); }
# skip = the check could not run in THIS environment (never in CI, which installs
# deps first). Doesn't fail the suite, but says so loudly instead of lying either way.
skip() { echo "SKIP  $1 — $2"; skipped=$((skipped+1)); }

BOT=telegram-companion-bot/bot.py

# Incident: streaming 400s arrived with an empty body and were undiagnosable (cost 3 fix
# rounds). The error body must be force-read before raise_for_status().
if grep -q '_ = resp.content' "$BOT"; then
  ok "streaming-error-body: response body force-read before raise_for_status"
else
  bad "streaming-error-body" "'_ = resp.content' missing from bot.py — streamed error bodies will be empty again"
fi

# Incident v2026-07-05.8: PTB's run_polling() silently overrides signal.signal() handlers;
# shutdown logging must be wired via post_shutdown, not a plain signal handler.
if grep -q '\.post_shutdown(_on_shutdown)' "$BOT"; then
  ok "graceful-shutdown: post_shutdown hook wired"
else
  bad "graceful-shutdown" ".post_shutdown(_on_shutdown) missing — SIGTERM diagnostics (phantom-killer triage) are lost"
fi

# The two launch invariants, on the live artifact. Phone-era history: bare `python` in a
# launcher crash-looped bots with ModuleNotFoundError when the venv wasn't on PATH, and on
# 2026-07-05 the phone watchdog restart-stormed a frozen fleet. Both now live in the systemd
# unit file `bot@.service` — the actual launch/restart path since the 2026-07-29 cutover;
# the phone's run-bot.sh and watchdog.sh manage nothing. This replaces the retired
# venv-explicit-python and heartbeat-alive evals, which pinned those dead phone files while
# bot@.service itself was guarded by nothing (coverage-inversion fix, 2026-08-24).
SERVICE=telegram-companion-bot/deploy/bot-selector@.service
svc_problems=""
grep -q 'ExecStart=/opt/telegram-bots/selectors/%i/current/venv/bin/python' "$SERVICE" \
  || svc_problems="ExecStart is not the explicit venv interpreter — bare python crash-loops with ModuleNotFoundError"
grep -q '^Restart=always' "$SERVICE" \
  || svc_problems="${svc_problems:+$svc_problems; }Restart=always missing — a crashed bot would not be resupervised (systemd is the supervisor now, not the phone watchdog)"
if [ -z "$svc_problems" ]; then
  ok "deploy-service-launch: bot@.service launches via the venv interpreter and Restart=always"
else
  bad "deploy-service-launch" "$svc_problems"
fi

# A mutable shared venv let CI and the VPS resolve different dependency versions, and
# code-only swaps left no durable release identity. The checker owns the whole class:
# exact hashed lock, one CI/VPS install contract, git-SHA code releases, atomic pointers,
# preserved writable shared paths, and a rollback route.
if release_contract=$(python3 telegram-companion-bot/tools/check_release_contract.py 2>&1); then
  ok "immutable-release-contract: $release_contract"
else
  bad "immutable-release-contract" "$release_contract"
fi
if selector_behavior=$(bash telegram-companion-bot/tools/test_release_selectors.sh 2>&1); then
  ok "release-selector-behavior: $selector_behavior"
else
  bad "release-selector-behavior" "$selector_behavior"
fi

# Incident v2026-07-05.5: missing tzdata made ZoneInfo silently fall back, then a
# tz-aware reminder vs naive now() TypeError killed bots at startup. Keep it pinned.
if grep -q '^tzdata' telegram-companion-bot/requirements.txt; then
  ok "tzdata-pinned: tzdata present in requirements.txt"
else
  bad "tzdata-pinned" "tzdata missing from requirements.txt — Termux has no system tz database"
fi

# Tokens must never land in the repo. The risk-guard hook blocks `git add .env`, but a
# secret pasted into a card, a doc, or a committed backup file would slip past it — the
# repo is PUBLIC again (2026-08-31), so anything committed is world-readable the instant
# it lands. Broadened 2026-08-31 (security pass after the repo went public) beyond the
# original three shapes to the credential prefixes most likely to appear in this stack —
# a full tree+history scan the same day was clean, so this pins that clean state forward.
# Shapes: Telegram bot token (digits:35-char), OpenAI sk- key, Anthropic sk-ant- key,
# AWS AKIA key id, PEM PRIVATE KEY block, Google/Gemini AIza key, GitHub gh?_/github_pat_
# token, xAI xai- key, Stripe sk_live_ key, and Slack/Discord webhook URLs. NanoGPT keys
# have no fixed shape and cannot be regex-matched; that .env is gitignored and risk-guard
# blocks `git add .env` is that key's real defense.
leaks=$(git grep -InE '[0-9]{8,10}:[A-Za-z0-9_-]{35}([^A-Za-z0-9_-]|$)|\bsk-ant-[A-Za-z0-9_-]{40,}|\bsk-[A-Za-z0-9]{32,}|\bAKIA[0-9A-Z]{16}\b|BEGIN [A-Z ]*PRIVATE KEY|\bAIza[0-9A-Za-z_-]{35}|\bgh[posu]_[A-Za-z0-9]{36,}|\bgithub_pat_[A-Za-z0-9_]{40,}|\bxai-[A-Za-z0-9]{40,}|\bsk_live_[A-Za-z0-9]{24,}|hooks\.slack\.com/services/[A-Za-z0-9/]{20,}|discord(app)?\.com/api/webhooks/[0-9]{5,}/[A-Za-z0-9_-]{20,}' -- . ':!.claude/evals/run-evals.sh' 2>/dev/null || true)
if [ -z "$leaks" ]; then
  ok "secret-scan: no token-shaped strings in tracked files"
else
  bad "secret-scan" "possible credential committed (rotate it AND purge from git history — the repo is public): $(echo "$leaks" | head -3 | tr '\n' ' ')"
fi

# The delivery gate checks that BOT_VERSION and CHANGELOG.md both changed, but not that
# they AGREE. Convention: release entries are titled '## v<version>' and must match
# bot.py's BOT_VERSION; non-release entries (docs, ops tooling) use '## YYYY-MM-DD — ...'
# headings, which this check ignores.
bv=$(grep -m1 '^BOT_VERSION' "$BOT" | cut -d'"' -f2)
top=$(grep -m1 -oE '^## v[0-9][^ ]*' telegram-companion-bot/CHANGELOG.md | sed 's/^## v//')
if [ -n "$bv" ] && [ "$bv" = "$top" ]; then
  ok "version-changelog-sync: BOT_VERSION $bv matches newest release entry"
else
  bad "version-changelog-sync" "BOT_VERSION is '$bv' but newest '## v' changelog entry is '$top' — bumped one, forgot the other"
fi

# Character cards and instance seeds are hand-edited JSON; a syntax slip bricks a bot at load.
json_bad=""
for f in telegram-companion-bot/*.json; do
  python3 -m json.tool "$f" >/dev/null 2>&1 || json_bad="$json_bad $f"
done
if [ -z "$json_bad" ]; then
  ok "cards-valid-json: all telegram-companion-bot/*.json parse"
else
  bad "cards-valid-json" "invalid JSON:$json_bad"
fi

# bot.py must always compile — /update refuses to install a non-compiling bot.py, but
# catching it here is one deploy cycle cheaper.
if python3 -m py_compile "$BOT" 2>/dev/null; then
  ok "bot-compiles: python3 -m py_compile bot.py"
else
  bad "bot-compiles" "bot.py does not compile"
fi

# Incident v2026-07-11: _retag_legacy_day_facts and helpers were defined AFTER
# load_state() called them at module level — NameError crash-looped every bot for a day.
# py_compile can't catch this (it checks syntax, not runtime name resolution).
# Amended 2026-07-18: the check used to hide stderr and blame EVERY failure on that
# NameError incident — in one session two pure environment breaks (Pillow not
# installed; broken system cryptography) were misreported as bot.py defects. It now
# surfaces the real exception line, and a missing third-party dependency SKIPs
# instead of failing (CI installs requirements first, so it can never skip there).
import_err=$(python3 -c "
import sys, os, tempfile, json; from pathlib import Path
d = tempfile.mkdtemp()
(Path(d)/'.env').write_text('TELEGRAM_BOT_TOKEN=t:f\nNANOGPT_API_KEY=k\nCHARACTER_CARD=c.json\nBOT_TIMEZONE=UTC\n')
(Path(d)/'c.json').write_text(json.dumps({'spec':'chara_card_v2','spec_version':'2.0','data':{'name':'T','description':'','personality':'','scenario':'','first_mes':'H','mes_example':'','system_prompt':'T','post_history_instructions':'','creator_notes':'','character_book':{'entries':[]}}}))
sys.argv=[sys.argv[0],d]; os.environ['BOT_HOME']=d
sys.path.insert(0,'telegram-companion-bot')
import bot
" 2>&1 >/dev/null); import_rc=$?
if [ "$import_rc" -eq 0 ]; then
  ok "bot-imports: bot.py imports cleanly"
else
  # Last "SomeError: ..." line of the traceback; fall back to the raw last line.
  import_exc=$(printf '%s\n' "$import_err" | grep -E '^[A-Za-z_][A-Za-z_0-9.]*(Error|Exception|Warning|Exit)[A-Za-z]*:' | tail -1)
  [ -n "$import_exc" ] || import_exc=$(printf '%s\n' "$import_err" | tail -1)
  if printf '%s' "$import_exc" | grep -q '^ModuleNotFoundError'; then
    skip "bot-imports" "dependency missing in this environment ($import_exc). Install telegram-companion-bot/requirements.lock with --require-hashes to make this check runnable — this is NOT a bot.py defect"
  else
    bad "bot-imports" "bot.py crashes on import: $import_exc — if the traceback points into bot.py, this is the v2026-07-11 class (a name used at module level before it's defined); if it points into site-packages/dist-packages, the environment's packages are broken, not bot.py"
  fi
fi

# v2026-07-20.1: reasoning models leaked raw chain-of-thought when `content` came back
# empty and the code fell back to `reasoning_content` (no <think> tags, so _strip_thinking
# couldn't clean it) — Priya sent her planning monologue as a reply. _extract_content must
# never read reasoning_content, and the streaming path must not join reasoning as the reply.
if grep -q 'msg.get("reasoning_content")' "$BOT" || grep -q 'text = "".join(reasoning_parts)' "$BOT"; then
  bad "no-reasoning-content-leak" "reasoning_content is being used as reply text again — raw chain-of-thought will leak to users (see v2026-07-20.1)"
else
  ok "no-reasoning-content-leak: reasoning_content is never delivered as the reply"
fi

# v2026-07-20.2: WSDOT fetch errors logged the raw requests exception, whose string
# carries the URL with the AccessCode query param — the key leaked into errors.log. The
# WSDOT fetches must log a classified reason (_wsdot_err_reason), never the raw exception.
if grep -qE '(alerts|travel times) fetch failed: %s", *e\b' "$BOT"; then
  bad "wsdot-key-not-logged" "a WSDOT fetch logs the raw exception (%s\", e) — str(e) carries the AccessCode URL and leaks the key into errors.log (see v2026-07-20.2)"
else
  ok "wsdot-key-not-logged: WSDOT fetch errors log a key-free reason, not the raw exception"
fi

# v2026-08-03.1: glm-5.1:thinking wrote its ENTIRE deliberation into ordinary content —
# no <think> tags, non-empty, no bracket syntax — so _strip_thinking, the v2026-07-20.1
# empty-content path, and _strip_directive_lines all passed it, and priya sent a
# ~12k-char planning essay as four chunked Telegram messages. Third variant of the
# chain-of-thought leak class. The guard must stay wired end to end: detector defined,
# consulted on the completion inside call_nanogpt, kill switch present. (Behavior — the
# re-roll, the fallback, generate_reply marking calls user-facing — is pinned by
# TestReasoningLeakGuard in tests/test_pure.py.)
if grep -q 'def _looks_like_reasoning_leak' "$BOT" \
   && grep -q '_looks_like_reasoning_leak(result' "$BOT" \
   && grep -q 'REASONING_LEAK_GUARD' "$BOT"; then
  ok "reasoning-leak-guard: reasoning-shaped completions are refused and re-rolled"
else
  bad "reasoning-leak-guard" "the reasoning-leak guard is unwired (detector, call_nanogpt check, or REASONING_LEAK_GUARD kill switch missing) — a thinking model's deliberation will ship as the reply again (see v2026-08-03.1)"
fi

# Same release, the other half: pre-merge review found that an honest character-card
# review — a flow the repo supports via character-review/ — trips every marker the
# guard looks for, and the DOCUMENT_MODEL sites pass no fallback, so a trip surfaces
# to the owner as "❌ something broke on my end". Every DOCUMENT_MODEL reply site must
# therefore opt out. Counted, not grepped for presence: a fourth site added without
# the opt-out is exactly the regression this pins.
# Parsed, not grepped: the first version of this check counted a trailing-comma line
# that only exists when the call is already wrapped, so deleting an opt-out collapsed
# the call to one line and dropped BOTH counts — it passed on the very regression it
# pins (C13, caught by the break-test). Walk the AST instead.
if ! doc_unguarded=$(python3 - "$BOT" 2>&1 <<'PYEOF'
import ast, sys
src = open(sys.argv[1], encoding="utf-8").read()
bad = []
for node in ast.walk(ast.parse(src)):
    if not isinstance(node, ast.Call):
        continue
    fn = node.func
    if getattr(fn, "id", getattr(fn, "attr", None)) != "reply_with_typing":
        continue
    kw = {k.arg: k.value for k in node.keywords}
    model = kw.get("model")
    if not (isinstance(model, ast.Name) and model.id == "DOCUMENT_MODEL"):
        continue
    opt = kw.get("leak_guard")
    if not (isinstance(opt, ast.Constant) and opt.value is False):
        bad.append(str(node.lineno))
print(",".join(bad))
PYEOF
); then
  doc_unguarded="the parser itself exited non-zero: ${doc_unguarded:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$doc_unguarded" ]; then
  ok "document-reply-leak-guard-optout: every DOCUMENT_MODEL reply site opts out of the reasoning-leak guard"
else
  bad "document-reply-leak-guard-optout" "reply_with_typing(model=DOCUMENT_MODEL) without leak_guard=False at line(s) $doc_unguarded — a card review trips every reasoning-leak marker, and DOCUMENT_MODEL passes no fallback, so the owner gets '❌ something broke on my end' instead of the review (see v2026-08-03.1)"
fi

# The operating machinery itself: hooks must parse, settings.json must be valid JSON.
hook_bad=""
for h in .claude/hooks/*.sh .claude/tools/*.sh telegram-companion-bot/*.sh; do
  bash -n "$h" 2>/dev/null || hook_bad="$hook_bad $h"
done
if [ -z "$hook_bad" ]; then
  ok "shell-scripts-parse: all hook, tool + bot shell scripts pass bash -n"
else
  bad "shell-scripts-parse" "syntax errors in:$hook_bad"
fi

# The other half of the guard layer: the Python files the hook wrappers invoke. bot.py
# has bot-compiles, sweep.py is import-checked by gate-corpus, and oplog-search.py /
# fleet-config-check.py are run by their own evals — but the five guard .py under
# .claude/hooks/ (host_guard, claim_guard, handoff_guard, theory_guard, agent-authorization)
# were checked by nothing. A wrapper ends `python3 <guard>.py`, so a SyntaxError makes it
# exit non-zero WITHOUT the guard's block path ever running: the guard fails OPEN, stops
# enforcing, and ships green (CI runs .sh through bash -n only). That is C13's "inert looks
# like working" applied to the guards themselves. Scoped to hooks/ deliberately — the
# gate_corpus fixtures under tools/ are crafted to be malformed and must not be compiled.
pyhook_bad=""
for p in .claude/hooks/*.py; do
  [ -e "$p" ] || continue
  python3 -m py_compile "$p" 2>/dev/null || pyhook_bad="$pyhook_bad $p"
done
if [ -z "$pyhook_bad" ]; then
  ok "hook-python-compiles: every .claude/hooks/*.py compiles (a broken guard fails open, unnoticed)"
else
  bad "hook-python-compiles" "python syntax error(s) in:$pyhook_bad — the guard(s) fail open and stop enforcing while shipping green"
fi

# The companion to the compile check: a wrapper invokes a sibling file — `python3 .../<guard>.py`
# or `bash .../<tool>.sh` — so if that file is renamed or deleted without updating the wrapper,
# the interpreter exits non-zero on a missing path and the hook fails (open, for an advisory
# guard) exactly as a syntax error would. py_compile and bash -n glob only files that exist, so
# neither can see an absence; hooks-wired checks the .sh are registered, not the files they name.
# Pulls every .claude/{hooks,tools}/*.{py,sh} path out of the wrappers and asserts each exists.
ref_missing=""
for r in $(grep -hoE '\.claude/(hooks|tools)/[A-Za-z0-9_./-]+\.(py|sh)' .claude/hooks/*.sh 2>/dev/null | sort -u); do
  [ -f "$r" ] || ref_missing="$ref_missing $r"
done
if [ -z "$ref_missing" ]; then
  ok "hook-refs-exist: every .py/.sh a hook wrapper invokes is present"
else
  bad "hook-refs-exist" "hook wrapper(s) invoke missing file(s):$ref_missing — the interpreter runs on a nonexistent path, exits nonzero, and the hook fails open"
fi

# --- prompt-rewrite-gate ---------------------------------------------------------------
# prompt-rewrite.py's whole value is its gate (should_rewrite): fire on short/under-specified
# task prompts, skip operational responses and already-specified ones. A gutted gate (always
# False = never nudge, or always True = nudge every "yes") passes hook-python-compiles while
# doing nothing useful or spamming every turn. Its --selftest pins both directions against
# fixtures and exits nonzero on any miss; run it here so a regression goes red in CI, not live.
if [ -f .claude/hooks/prompt-rewrite.py ]; then
  if pr_out=$(python3 .claude/hooks/prompt-rewrite.py --selftest 2>&1); then
    ok "prompt-rewrite-gate: should_rewrite fires/skips per fixtures (${pr_out##*ok })"
  else
    bad "prompt-rewrite-gate" "$pr_out"
  fi
fi

# --- stop-guards-behavioral ------------------------------------------------------------
# hook-python-compiles proves the four Python Stop-guards COMPILE; nothing exercised them.
# All four fail OPEN (a broken guard returns 0/allow), so a gutted regex passes every other
# check while blocking nothing at runtime — the class gate_corpus/ solves for sweep.py,
# left unapplied to the guards until the 2026-08-24 functions audit (H2). This drives each
# guard through its REAL path — a fixture transcript on stdin — and asserts it BLOCKS (exit
# 2) a payload it must catch and ALLOWS (exit 0) a payload it must not. A guard that stops
# blocking its block-fixture turns this red. Fixtures mirror each guard's own incident:
# host (unattributed VPS command), theory (named-function claim, unhedged), claim (identity
# on metadata alone), handoff (cd then a relative path).
if ! stop_guards=$(python3 - 2>&1 <<'PYEOF'
import json, subprocess, sys, tempfile, os
from pathlib import Path

hooks = Path(".claude/hooks")

def run_guard(guard, txt):
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as tf:
        tf.write(json.dumps({"type": "assistant",
                             "message": {"role": "assistant", "content": txt}}) + "\n")
        tpath = tf.name
    try:
        p = subprocess.run([sys.executable, str(hooks / guard)],
                           input=json.dumps({"transcript_path": tpath}),
                           capture_output=True, text=True, timeout=20)
        return p.returncode
    finally:
        os.unlink(tpath)

# (guard, must-BLOCK fixture -> exit 2, must-ALLOW fixture -> exit 0)
CASES = [
    ("host_guard.py",
     "Run this:\n```\nsystemctl restart bot@nora\n```\n",
     "On the VPS, run:\n```\n# host: vps\nsystemctl restart bot@nora\n```\n"),
    ("theory_guard.py",
     "The function _group_deliver() returns None when the shared ledger is empty.",
     "The function _group_deliver() probably returns None when the ledger is empty."),
    ("claim_guard.py",
     "Priya: confirmed - the upload is identical to her reference, both 1024x1024 progressive JPEG.",
     "Priya: the upload is consistent with her reference, both 1024x1024 progressive JPEG."),
    ("handoff_guard.py",
     "```\n# host: vps\ncd /opt/telegram-bots/.repo\nbash telegram-companion-bot/deploy/vps-sync.sh nora\n```",
     "```\n# host: vps\ncd /opt/telegram-bots/.repo\nbash /opt/telegram-bots/.repo/telegram-companion-bot/deploy/vps-sync.sh nora\n```"),
]

problems = []
for guard, block_txt, allow_txt in CASES:
    if not (hooks / guard).is_file():
        problems.append(f"{guard} is missing")
        continue
    rc_block = run_guard(guard, block_txt)
    rc_allow = run_guard(guard, allow_txt)
    if rc_block != 2:
        problems.append(f"{guard} did NOT block its block-fixture (exit {rc_block}, want 2) "
                        f"— the guard is failing OPEN / gutted")
    if rc_allow != 0:
        problems.append(f"{guard} blocked its allow-fixture (exit {rc_allow}, want 0) "
                        f"— false positive")

print(" | ".join(problems))
PYEOF
); then
  stop_guards="the harness itself exited non-zero: ${stop_guards:-(no output)} — a check that goes green when its own harness dies is not a check"
fi
if [ -z "$stop_guards" ]; then
  ok "stop-guards-behavioral: all four Python Stop-guards block their block-fixture and allow their allow-fixture"
else
  bad "stop-guards-behavioral" "$stop_guards"
fi

if [ -f .claude/settings.json ]; then
  if python3 -m json.tool .claude/settings.json >/dev/null 2>&1; then
    ok "settings-valid-json: .claude/settings.json parses"
  else
    bad "settings-valid-json" ".claude/settings.json is invalid JSON — every hook silently dies"
  fi
fi

# Docs are where deploy commands get copied from, so a curl-piped raw-URL install is a
# trap: the sanctioned deploy reads the whole locked release from the git checkout via
# vps-sync.sh, never a single raw file. Original trigger, 2026-07-29: a runnable
# `curl -fsSL <raw-base>/deploy/vps-sync.sh` was handed to the operator straight out of
# CLAUDE.md's Deployment block and failed twice over — once on the literal placeholder,
# once because the repo was private and the URL 404'd. The repo is public again as of
# 2026-08-31, so such a URL now RESOLVES — which makes it more dangerous, not less: it
# runs and silently bypasses the immutable-release/locked-venv model. The check is
# unchanged; only its rationale moved from "these 404" to "these bypass the deploy".
# Runnable = the line starts with curl/wget or assigns a BASE/REPO var. Annotated
# history is fine: mark the block DEAD, Historical, or Superseded within 3 lines above.
if ! raw_stale=$(python3 - 2>&1 <<'PY'
import pathlib, re
bad = []
skip = ("CHANGELOG.md", "constraints.md", "operational-log.md")
for p in sorted(pathlib.Path(".").rglob("*.md")):
    s = str(p)
    if any(k in s for k in skip) or "/vault/" in s or "/node_modules/" in s:
        continue
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    marker = r'DEAD|[Hh]istorical|[Ss]uperseded|404|do not run'
    # A whole file can be retired with an EXPLICIT pragma in its first 25 lines
    # (SETUP_GUIDE.md is entirely phone-era). The pragma is a literal token, not the
    # loose marker set: the first draft accepted any marker word up top, which exempted
    # all of CHEATSHEET.md because its header *explains* that raw URLs 404 — the check
    # passed a re-injected defect in the one file it most needed to guard. An opt-out
    # has to be unambiguous or it silently becomes an opt-out for everything.
    if "evals: raw-urls-historical" in " ".join(lines[:25]):
        continue
    for i, ln in enumerate(lines):
        if "raw.githubusercontent" not in ln:
            continue
        if not re.match(r'\s*(curl|wget|(export\s+)?(BASE|REPO|RAW\w*)=)', ln):
            continue          # prose or a comment explaining the 404 — not runnable
        # 6 lines, not 3: an annotation usually sits above the ```bash fence and any
        # intervening prose, not immediately above the command.
        window = " ".join(lines[max(0, i - 6):i + 1])
        if re.search(marker, window):
            continue          # annotated as dead on purpose
        bad.append(f"{s}:{i+1}")
print(" ".join(bad))
PY
); then
  raw_stale="the parser itself exited non-zero: ${raw_stale:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$raw_stale" ]; then
  ok "no-live-raw-urls: no runnable raw.githubusercontent command left unannotated"
else
  bad "no-live-raw-urls" "a curl-piped raw-URL install bypasses the vps-sync/locked-release deploy; these read as runnable: $raw_stale"
fi

# Nora's instance dir drifted twice (table drift 2026-07-11; launch/sync scripts still
# pointing at $BOT_SRC 2026-07-20). Her instance dir is ~/nora-bot; ~/telegram-bot is the
# shared CODE dir. The scripts must not pass ~/telegram-bot (or bare $BOT_SRC) as Nora's
# INSTANCE dir, or a full redeploy / post-crash relaunch brings her up from the wrong dir.
nid_bad=""
if grep -Eq 'run-bot\.sh" +"\$BOT_SRC" +nora' telegram-companion-bot/update-all.sh; then
  nid_bad="$nid_bad update-all.sh"
fi
if grep -q '"telegram-bot:nora' telegram-companion-bot/sync-cards.sh; then
  nid_bad="$nid_bad sync-cards.sh"
fi
if grep -Eq 'check_instance +"\$BOT_SRC"' telegram-companion-bot/watchdog.sh; then
  nid_bad="$nid_bad watchdog.sh"
fi
if [ -z "$nid_bad" ]; then
  ok "nora-instance-dir: launch/sync scripts use ~/nora-bot, not the code dir, for Nora"
else
  bad "nora-instance-dir" "these pass the code dir as Nora's instance dir:$nid_bad — redeploy/relaunch would load the wrong .env/state (see CLAUDE.md §Bot instances)"
fi

# Group chat boundary (GROUP_CHAT_DESIGN.md §12). Two adversarial-review rounds each
# found a flat-file write path a hand-kept list had missed, so the boundary is pinned
# here as class-level checks, not left to memory.
# (a) _group_deliver must stay allowlist-BUILT: none of the DM tail's side effects may
# appear in its body — those write per-instance flat files that leak into private DMs.
if grep -q 'async def _group_deliver' "$BOT"; then
  gd_body=$(awk '/^async def _group_deliver/{f=1; next} f && /^(async def |def )/{exit} f' "$BOT")
  gd_bad=""
  for banned in post_reply_analysis _check_joke_used send_selfie send_meme _send_voice_reply _append_user_note _append_memory; do
    echo "$gd_body" | grep -q "$banned" && gd_bad="$gd_bad $banned"
  done
  if [ -z "$gd_bad" ]; then
    ok "group-deliver-clean: _group_deliver contains no DM-tail side effects"
  else
    bad "group-deliver-clean" "banned call(s) in _group_deliver:$gd_bad — group replies would write private flat files"
  fi
else
  bad "group-deliver-clean" "_group_deliver missing from bot.py"
fi
# (b) The group command allowlist must stay exactly {"chatid"} — widening it is a
# reviewed act (edit this eval in the same commit), never a drive-by.
if grep -qE 'GROUP_ALLOWED_COMMANDS = \{"chatid"\}' "$BOT"; then
  ok "group-cmd-allowlist: GROUP_ALLOWED_COMMANDS pinned to {\"chatid\"}"
else
  bad "group-cmd-allowlist" "GROUP_ALLOWED_COMMANDS changed — group chats may now execute commands that write private state"
fi

# Ownership boundary (v2026-07-13.1). /start once rewrote the owner file on every
# call — any stranger who found the bot's username could capture heartbeats and
# follow-ups. Claim-once in set_owner and the private-chat gate are pinned here.
so_body=$(awk '/^def set_owner/{f=1; next} f && /^(async def |def )/{exit} f' "$BOT")
if echo "$so_body" | grep -q 'get_owner() is None'; then
  ok "owner-claim-once: set_owner cannot reassign an existing owner"
else
  bad "owner-claim-once" "set_owner lost its claim-once guard — any /start can steal ownership again"
fi
if grep -q 'TypeHandler(Update, _private_gate), group=-1' "$BOT"; then
  ok "private-gate-registered: ALLOWED_USERS enforced at one choke point (group -1)"
else
  bad "private-gate-registered" "_private_gate not registered in handler group -1 — per-handler checks drift (that is how /start was missed)"
fi

# v2026-07-19.2, third generation of the provenance-leak class (2026-07-10 memories,
# v2026-07-12.4 note grounding): quote-grounding is a topic gate, not an ownership
# gate — the character's own events entered user_notes via the USER's lines ("good
# luck at the scrimmage") and note_followup_job then asked the owner how the
# character's event went. Both ends of the ownership fix are pinned here.
if grep -q "not a user_note" "$BOT" && grep -q "not whose message mentioned it" "$BOT"; then
  ok "note-ownership-extraction: user_note requires the event to belong to the user's own life"
else
  bad "note-ownership-extraction" "ownership clause missing from post_reply_analysis — her events will re-enter user_notes through the user's lines"
fi
if grep -q "how it went for her instead" "$BOT"; then
  ok "note-ownership-followup: follow-up backstop for character-owned notes present"
else
  bad "note-ownership-followup" "note_followup_job backstop missing — polluted notes will again be asked back at the owner as their own"
fi

# v2026-07-23.2: anti-hallucination confidence gating for notes, parallel to the
# memory_confidence + MEMORY_AUTOCONF defense that's been in place since v2026-07-10.2.
# The analysis prompt must request user_note_confidence and the processing code must
# gate on NOTE_AUTOCONF — without both, plausible-but-wrong notes bypass the grounding
# check and enter user_notes.txt as fact.
if grep -q 'user_note_confidence' "$BOT" && grep -q 'NOTE_AUTOCONF' "$BOT" && grep -q 'note_low_confidence' "$BOT"; then
  ok "note-confidence-gate: user_note_confidence requested + NOTE_AUTOCONF enforced + rejection counted"
else
  bad "note-confidence-gate" "note confidence gating missing — plausible-but-wrong notes will be stored as fact (the memory system has this; notes must too)"
fi

# The analysis prompt must include the null-over-guess instruction: the model should
# prefer null over a plausible extraction when evidence is ambiguous. This is the
# instruction-level defense; confidence gating is the deterministic backstop.
if grep -q 'do not fill gaps with a' "$BOT"; then
  ok "null-over-guess: analysis prompt includes null-over-plausible-guess instruction"
else
  bad "null-over-guess" "null-over-guess instruction missing from analysis prompt — the model will fabricate plausible notes/memories when unsure"
fi

# v2026-07-26.5: requests does NOT raise on 4xx/5xx, so the healthcheck ping treated a
# REJECTED ping as success and logged nothing. Five of six instances ran for weeks on a
# doubled URL (hc-ping returned 400 every time) while every audit line read OK — a dead
# man's switch that reports success while unreachable is worse than none.
hc_body=$(awk '/Dead man.s switch/{f=1} f{print} f && /healthcheck ping failed/{exit}' "$BOT")
if echo "$hc_body" | grep -qE 'if[^=]*status_code[[:space:]]*>=[[:space:]]*400'; then
  ok "healthcheck-status-checked: a rejected healthcheck ping is detected, not silently passed"
else
  bad "healthcheck-status-checked" "the healthcheck ping no longer inspects resp.status_code — a 4xx/5xx ping will silently report OK and the dead man's switch dies quietly"
fi

# v2026-07-13.2: raw exception text was interpolated into chat messages — leaks
# internals, and on_error would post them into the pilot GROUP chat.
if grep -qE '\{type\(err\)|❌[^"]*\{e' "$BOT"; then
  bad "no-exception-leak" "a user-facing ❌ message interpolates a raw exception again — internals leak to chat (and to groups via on_error)"
else
  ok "no-exception-leak: user-facing errors are generic; details stay in the log"
fi

# v2026-07-25.7: /audit interpolates arbitrary diagnostic strings — card field names
# (system_prompt, mes_example), prompt block headings ([VOICEPRINT PRESET …]), config
# warnings naming env vars. Under parse_mode="Markdown" a stray '_' or unmatched '['
# makes Telegram reject the whole message, so the command that exists to diagnose the
# bot silently failed fleet-wide. Pinned because the regression is invisible in code
# review and only shows up as "audit isn't working".
# NB: a plain awk range (/^async def audit_cmd/,/^async def /) collapses to ONE line,
# because the opening line matches the end pattern too — that version of this check could
# never fail. Flag-based scan instead, and it was break-tested red before being trusted.
audit_send=$(awk '
  /^async def audit_cmd/ { inblk = 1; next }
  inblk && /^async def / { inblk = 0 }
  inblk && $0 !~ /^[[:space:]]*#/ && /parse_mode/ { c++ }
  END { print c + 0 }
' "$BOT")
if [ "${audit_send:-0}" -eq 0 ]; then
  ok "audit-plain-text: /audit sends plain text (cannot be broken by what it reports)"
else
  bad "audit-plain-text" "/audit uses parse_mode again — a card field name or prompt heading with '_' or '[' will make Telegram reject the message and /audit will silently stop working (see CHANGELOG v2026-07-25.7)"
fi

# 2026-08-02: the selfie-base status was added to gather_audit_data() and the STARTUP
# AUDIT log line, and the owner was told /audit would show it. audit_cmd builds its own
# lines and never rendered it. A key that reaches the data dict but no user-facing
# surface is invisible in exactly the situation it was added for. Every key must be
# either rendered by audit_cmd or listed as API-only below.
api_only='away_users config_warnings llm_stats card_fields preset_override token_calibration memory_review_pending'
if ! unrendered=$(python3 - "$BOT" "$api_only" 2>&1 <<'PYEOF'
import re, sys, pathlib
src = pathlib.Path(sys.argv[1]).read_text()
allowed = set(sys.argv[2].split())
gather = re.search(r'def gather_audit_data.*?\n    return \{(.*?)\n    \}', src, re.S)
cmd = re.search(r'async def audit_cmd.*?(?=\nasync def |\ndef )', src, re.S)
if not gather or not cmd:
    print("PARSE-FAIL")
else:
    keys = set(re.findall(r'^\s*"([a-z_]+)":', gather.group(1), re.M))
    body = cmd.group(0)
    missing = sorted(k for k in keys - allowed if k not in body)
    print(" ".join(missing))
PYEOF
); then
  unrendered="the parser itself exited non-zero: ${unrendered:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ "$unrendered" = "PARSE-FAIL" ]; then
  bad "audit-keys-rendered" "could not locate gather_audit_data/audit_cmd — the eval needs updating, not the code"
elif [ -z "$unrendered" ]; then
  ok "audit-keys-rendered: every /audit data key reaches the rendered output (or is API-only)"
else
  bad "audit-keys-rendered" "gather_audit_data keys never rendered by /audit:$unrendered — add a line to audit_cmd or list the key as API-only in this eval (2026-08-02: selfie_base was added to the data and the log line but not /audit, and the owner was told otherwise)"
fi

# 2026-07-25 config audit: .env.example had drifted badly from bot.py in BOTH directions
# — 7 variables documented that nothing read (setting NUDGE_MAX looked like it capped
# proactive messages and did nothing), and 65 read that were undocumented, including
# BOT_TIMEZONE, which was documented as THE timezone setting while the clock actually
# came from TIMEZONE. Every var bot.py reads must now be either documented as settable
# (`NAME=` line) or named in the "Internal knobs" section.
if ! env_drift=$(python3 - "$BOT" "$(dirname "$BOT")/.env.example" 2>&1 <<'PYEOF'
import re, sys, pathlib
bot = pathlib.Path(sys.argv[1]).read_text()
env = pathlib.Path(sys.argv[2]).read_text()
used = set(re.findall(r'os\.getenv\(\s*["\']([A-Z][A-Z0-9_]*)["\']', bot))
# `bool` joined int|float on 2026-08-10 (v2026-08-10.8), when MAP_INTENT and
# FOOD_SUGGESTIONS moved from hand-rolled `os.getenv(...) in (...)` to `_env_bool`.
# This widens what counts as a read; it does not weaken the check. A var routed through
# a config helper is still read, and the eval reported both as "documented but never
# read" purely because the helper's name was not in this list.
# sweep.py's env-drift scanner already listed `bool` here before the helper existed —
# this copy had drifted from it, which is why the eval failed and the sweep did not.
used |= set(re.findall(r'_env_(?:int|float|bool)\(\s*["\']([A-Z][A-Z0-9_]*)["\']', bot))
documented = set(re.findall(r'^#?\s*([A-Z][A-Z0-9_]{2,})=', env, re.M))
mentioned = set(re.findall(r'\b([A-Z][A-Z0-9_]{2,})\b', env))
dead = sorted(documented - used)
missing = sorted(used - mentioned)
out = []
if dead:    out.append("documented but never read: " + ", ".join(dead))
if missing: out.append("read but undocumented: " + ", ".join(missing))
print(" | ".join(out))
PYEOF
); then
  env_drift="the parser itself exited non-zero: ${env_drift:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$env_drift" ]; then
  ok "env-vars-documented: .env.example accounts for every var bot.py reads"
else
  bad "env-vars-documented" "$env_drift"
fi

# --- skill-index-integrity -------------------------------------------------------------
# Pins the 2026-07-30 scaffolding audit's recurring class: skill-router describing a
# reality that isn't there. Three instances in one pass — (1) it claimed
# artifact-first-delivery and repo-validation-gate were "preloaded always (do not
# re-load)", suppressing the two most broadly applicable skills; (2) it advertised
# `grill-me` as a live alias for a stub that sets disable-model-invocation and cannot be
# invoked at all; (3) CLAUDE.md carried a divergent 8-row copy that omitted seven skills
# including verify-external-audit. An index nobody can trust routes worse than no index.
#
# Checks BOTH directions, because they fail differently: a skill missing from the table is
# invisible tomorrow, and a table row pointing at nothing sends a session somewhere empty.
# Scoped to the LAST cell of table rows only — the file's own prose explains the grill-me
# incident by name and must stay legal (C14: a scanner cannot tell "does the bad thing"
# from "explains it").
if ! skill_index=$(python3 - 2>&1 <<'PYEOF'
import re
from pathlib import Path

router = Path(".claude/skills/skill-router/SKILL.md")
skills_dir = Path(".claude/skills")
problems = []

if not router.exists():
    print("skill-router/SKILL.md is missing — the routing table is the index")
    raise SystemExit(0)

# Names referenced in the Load (last) column of a table row. Skill dirs are
# lowercase-hyphen, which excludes tool names like ListSkills/SearchSkills.
named = set()
for line in router.read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if not s.startswith("|") or set(s) <= set("|- :"):
        continue
    cells = [c.strip() for c in s.strip("|").split("|")]
    if len(cells) < 2 or cells[0].lower() == "trigger":
        continue
    for m in re.findall(r"`([a-z][a-z0-9-]*)`", cells[-1]):
        named.add(m)

on_disk = {}
for d in sorted(skills_dir.iterdir()) if skills_dir.exists() else []:
    if not d.is_dir() or d.name.startswith("_"):
        continue
    f = d / "SKILL.md"
    if not f.is_file():
        problems.append(f"{d.name}/ has no SKILL.md")
        continue
    head = f.read_text(encoding="utf-8")[:600]
    on_disk[d.name] = bool(
        re.search(r"^disable-model-invocation:\s*true", head, re.M))

for name in sorted(set(on_disk) - named - {"skill-router"}):
    problems.append(
        f"{name} exists but is not in skill-router's table — register it there in the "
        f"same change or it is invisible tomorrow")

for name in sorted(named - set(on_disk)):
    problems.append(
        f"skill-router names {name} but .claude/skills/{name}/ does not exist — "
        f"delete the row or create the skill (the grill-me class)")

for name in sorted(n for n in named if on_disk.get(n)):
    problems.append(
        f"skill-router names {name}, which sets disable-model-invocation and therefore "
        f"cannot be invoked — delete the row or drop that frontmatter")

if re.search(r"[Pp]reloaded always", router.read_text(encoding="utf-8")):
    problems.append(
        "skill-router claims something is 'preloaded always' — nothing is; that claim "
        "suppressed loading of artifact-first-delivery and repo-validation-gate")

# Instance (3) of the 2026-07-30 audit, the one left unmechanised: CLAUDE.md carried a
# divergent 8-row copy of the routing table. It was deleted and replaced with a prose rule
# — "Do not re-add a 'quick reference' copy of that table here" — which the same paragraph
# admits "no check catches". This is that check.
#
# The discriminator is the FIRST cell, not the presence of skill names. CLAUDE.md
# legitimately has a table (the sanctioned-shorthand vocabulary table) whose cells cite
# owning skills, so "no skill names in a CLAUDE.md table" would flag it immediately — the
# C14 trap this file has hit twice. A routing table is keyed BY skill; the vocabulary table
# is keyed by term ("the fleet", "break-test"). Measured 2026-08-21: 18 table rows, zero
# first-cell collisions with the 24 skill directories.
claude_md = Path("CLAUDE.md")
if claude_md.is_file():
    for n, line in enumerate(claude_md.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s.startswith("|") or set(s) <= set("|- :"):
            continue
        first = re.sub(r"[`*_]", "", s.strip("|").split("|")[0]).strip()
        if first in on_disk:
            problems.append(
                f"CLAUDE.md:{n} has a table row keyed by the skill `{first}` — that is a "
                f"routing table, and the last one drifted, omitted seven skills and "
                f"misrouted a session (2026-07-30). skill-router is the index; CLAUDE.md "
                f"points at it")

print(" | ".join(problems))
PYEOF
); then
  skill_index="the parser itself exited non-zero: ${skill_index:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$skill_index" ]; then
  ok "skill-index-integrity: skill-router's table and .claude/skills/ agree, both directions"
else
  bad "skill-index-integrity" "$skill_index"
fi

# --- skill-body-current ----------------------------------------------------------------
# skill-index-integrity proves a skill EXISTS and is registered; it never reads a skill
# body. The 2026-08-24 functions audit found four skills whose bodies still described the
# empty Termux phone as the live system — including repo-debugging-playbook (loaded when a
# bot is down) and artifact-first-delivery (loaded on every deliverable). This catches a
# skill body naming the retired phone platform in live-command terms without marking it
# historical. It is a prose scan, so deliberately coarse (C14): the escape hatch is a
# historical/phone-era marker in the same body, plus ALLOWLIST for a skill that must name a
# phone token for a reason the marker does not cover. It would have failed on all four.
if ! skill_body=$(python3 - 2>&1 <<'PYEOF'
import re
from pathlib import Path

skills = Path(".claude/skills")
# Tokens that signal phone-era LIVE commands/paths, not merely the word "phone".
STALE = re.compile(r'Termux|~/telegram-bot|run-bot\.sh|watchdog\.sh|\btmux\b|raw\.githubusercontent|\badb ', re.I)
# A body carrying one of these acknowledges the phone is retired — that is not drift.
MARKER = re.compile(r'historical|phone-era|retired|no longer|manages nothing|phone is (gone|empty)|migration complete', re.I)
# name -> reason: a skill that must name a phone token for a reason the marker cannot cover.
ALLOWLIST = {}

problems = []
scanned = 0
for d in sorted(skills.iterdir()) if skills.exists() else []:
    f = d / "SKILL.md"
    if not f.is_file() or d.name in ALLOWLIST:
        continue
    scanned += 1
    body = f.read_text(encoding="utf-8")
    tok = STALE.search(body)
    if tok and not MARKER.search(body):
        problems.append(
            f"{d.name}/SKILL.md names phone-era token '{tok.group(0).strip()}' with no "
            f"historical/phone-era marker — the fleet is VPS/systemd; mark it historical, "
            f"correct it, or add it to ALLOWLIST with a reason")

if scanned == 0:
    problems.append("scanned no skill bodies — the detector is broken (a scan that scans nothing is not a check)")

print(" | ".join(problems))
PYEOF
); then
  skill_body="the parser itself exited non-zero: ${skill_body:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$skill_body" ]; then
  ok "skill-body-current: no skill body describes the retired phone as the live system"
else
  bad "skill-body-current" "$skill_body"
fi

# --- reviewer-stance-present -----------------------------------------------------------
# Owner rule (2026-08-24): every reviewer agent — one that judges an artifact it did not
# write against a standard — must carry the shared reviewer stance verbatim: judge only
# against the standard, and list every shortfall before saying anything positive. A model
# that grades its own output finds reasons to pass; a separate reviewer is the fix, and
# that stance lived only in a chat prompt until this check pinned it into the contracts.
#
# "Reviewer agent" is decided from the frontmatter description's verb (review/verify/
# critique), the self-maintaining direction skill-index-integrity uses: a NEW agent whose
# description says it reviews or verifies is required to carry the stance, so the rule
# reaches agents that don't exist yet — which is what "any reviewer agent" means. EXEMPT
# lists description-verb matches that are not artifact-against-standard reviewers, each
# with a reason; it is empty today. ALWAYS lists agents the owner classified as reviewers
# whose description does not trip the verb (context-librarian reviews docs against reality,
# owner call 2026-08-24) — without it the stance there could be stripped unnoticed.
if ! reviewer_stance=$(python3 - 2>&1 <<'PYEOF'
import re
from pathlib import Path

agents_dir = Path(".claude/agents")
# Whitespace-normalized anchors that must BOTH appear in a reviewer agent's body. Two
# lines, not one, so stripping half the stance still trips the check.
ANCHORS = [
    "You did not write the thing you are reviewing.",
    "List every place it falls short before you say anything positive.",
]
# name (file stem) -> reason. Add here only when a new agent's description trips the verb
# but the agent does not judge someone else's work product against a standard.
EXEMPT = {}
# Agents the owner classified as reviewers whose description carries no review verb.
ALWAYS = {"context-librarian"}

problems = []
reviewers = []
for f in sorted(agents_dir.glob("*.md")) if agents_dir.exists() else []:
    text = f.read_text(encoding="utf-8")
    m = re.search(r"^description:\s*(.+)$", text, re.M)
    desc = m.group(1) if m else ""
    is_reviewer = f.stem in ALWAYS or bool(re.search(r"\b(review|verif|critiqu)", desc, re.I))
    if not is_reviewer or f.stem in EXEMPT:
        continue
    reviewers.append(f.stem)
    norm = re.sub(r"\s+", " ", text)
    missing = [a for a in ANCHORS if a not in norm]
    if missing:
        joined = " / ".join(missing)
        problems.append(
            f"{f.name} reads as a reviewer agent but is missing the reviewer stance "
            f"({joined}) — add the shared stance block or list it in EXEMPT with a reason")

# A stance check that guards nothing is not a check (C14): if the detector matches no
# agent, it is broken or every reviewer was renamed out from under it — fail loudly.
if not reviewers:
    problems.append(
        "no reviewer agent matched (verb review/verif/critiqu, or the ALWAYS set) — the "
        "detector is broken; it guarded 4 agents when written (adversarial-critic, "
        "qa-engineer, character-reviewer, context-librarian)")

print(" | ".join(problems))
PYEOF
); then
  reviewer_stance="the parser itself exited non-zero: ${reviewer_stance:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$reviewer_stance" ]; then
  ok "reviewer-stance-present: every reviewer agent carries the judge-against-standard / shortfalls-first stance"
else
  bad "reviewer-stance-present" "$reviewer_stance"
fi

# --- runtime-version-pinned ------------------------------------------------------------
# Second occurrence of one class: CI testing a Python the fleet doesn't run. It was pinned
# to 3.13 while the phone ran 3.14 (fixed 2026-07-26), then left at 3.14 after the VPS
# cutover made the real runtime 3.12 — found 2026-07-31 by an audit, not by a check. The
# comment on the pin warned about exactly this failure and still went stale, which is the
# argument for a check instead of a comment.
#
# Both sides are single declared values, so this is decidable without reading prose (C14):
# CLAUDE.md's Stack bullet vs. the workflow's python-version. A MISSING anchor fails too —
# a check that silently passes when it can't find what it measures is not a check (C13).
if ! runtime_pin=$(python3 - 2>&1 <<'PYEOF'
import re
from pathlib import Path

problems = []
claude = Path("CLAUDE.md")
wf = Path(".github/workflows/evals.yml")

declared = ci = None
if not claude.exists():
    problems.append("CLAUDE.md is missing")
else:
    m = re.search(r"^- Python \*\*(\d+\.\d+)\*\* on the VPS", claude.read_text(encoding="utf-8"), re.M)
    if not m:
        problems.append(
            "CLAUDE.md's Stack section no longer declares the runtime in the form "
            "'- Python **X.Y** on the VPS' — this check can't compare what it can't find")
    else:
        declared = m.group(1)

if not wf.exists():
    problems.append(".github/workflows/evals.yml is missing")
else:
    pins = re.findall(r'^\s*python-version:\s*"?(\d+\.\d+)"?\s*$', wf.read_text(encoding="utf-8"), re.M)
    if len(pins) != 1:
        problems.append(f"expected exactly one python-version pin in evals.yml, found {len(pins)}")
    else:
        ci = pins[0]

if declared and ci and declared != ci:
    problems.append(
        f"CLAUDE.md says the fleet runs Python {declared}, CI tests {ci} — "
        f"CI is exercising a runtime nothing runs. Change both together")

print(" | ".join(problems))
PYEOF
); then
  runtime_pin="the parser itself exited non-zero: ${runtime_pin:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$runtime_pin" ]; then
  ok "runtime-version-pinned: CI's Python matches the runtime CLAUDE.md declares"
else
  bad "runtime-version-pinned" "$runtime_pin"
fi

# --- claude-md-refs-resolve ------------------------------------------------------------
# CLAUDE.md is loaded into every session, so a path it names that no longer exists sends
# every future session somewhere empty. This is the mechanically-checkable half of the
# 2026-07-31 audit's class ("the always-loaded doc describes a system that moved"): the
# prose half isn't decidable, but "does this file exist" is.
#
# Two paths are deliberately absent and exempt — CLAUDE.md names them precisely to say
# they are gone or must never be committed. That exemption list is this check's C14 escape
# hatch: a scanner cannot tell "references a dead file" from "documents that it died", so
# the distinction is made by hand, here, where it is visible.
if ! md_refs=$(python3 - 2>&1 <<'PYEOF'
import re
from pathlib import Path

EXEMPT = {
    ".supervise.sh",        # phone-era supervisor; CLAUDE.md names it to say it manages nothing
    ".claude/.runtime/",    # gitignored by design — "never commit it, never add it back"
}
ROOTS = ["", "telegram-companion-bot", "telegram-companion-bot/deploy",
         ".claude/tools", ".claude/hooks", ".claude/evals", ".github/workflows"]
EXTS = "md|sh|py|json|txt|yml|yaml|html|service|example"

# Strip fenced blocks BEFORE pairing inline backticks. A ``` fence is three backticks,
# so a naive `([^`]+)` scan pairs one fence delimiter against the next and desynchronizes
# for the whole rest of the file — which silently blinded this check to everything below
# the Deployment section's code fence. Caught 2026-07-31 by break-test mode 5 failing to
# go red, not by review. Fenced content is skipped deliberately: it holds shell commands
# with placeholders (`<instance>`) and VPS absolute paths, neither of which is a repo path.
text = re.sub(r"^```.*?^```", "", Path("CLAUDE.md").read_text(encoding="utf-8"), flags=re.S | re.M)
missing = []
for tok in sorted(set(re.findall(r"`([^`]+)`", text))):
    if tok.startswith(("/", "~", "http")) or tok in EXEMPT:
        continue  # absolute/remote paths point off this repo; exemptions are documented above
    if tok.endswith("/"):
        cand = tok.rstrip("/")
        if not re.fullmatch(r"[.A-Za-z0-9_][A-Za-z0-9_./@-]*", cand):
            continue
    elif re.fullmatch(rf"[.A-Za-z0-9_@][A-Za-z0-9_./@-]*\.({EXTS})", tok):
        cand = tok
    else:
        continue  # not a path-shaped token (globs, commands, env vars, version strings)
    if not any((Path(r) / cand).exists() for r in ROOTS):
        missing.append(tok)

if missing:
    print("CLAUDE.md names paths that do not exist: " + ", ".join(missing) +
          " — rename, delete the reference, or add it to EXEMPT if the doc's point is "
          "that the file is gone")
PYEOF
); then
  md_refs="the parser itself exited non-zero: ${md_refs:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$md_refs" ]; then
  ok "claude-md-refs-resolve: every repo path CLAUDE.md names still exists"
else
  bad "claude-md-refs-resolve" "$md_refs"
fi

# --- roadmap-claims-current ---------------------------------------------------------------
# A skill saying "ROADMAP 1.6 (unshipped)" about an item ROADMAP.md marks ✅ is a stale
# claim that reads as a live constraint. On 2026-08-02 that exact sentence — written before
# the flock shipped on 2026-08-01 — was copied into three deploy handoffs as a current
# hazard, and then into a NEW skill written the same day, propagating it further. C12's
# second occurrence: prose about the system is a claim about when it was written.
# Decidable half only: a doc naming a ROADMAP item AND a staleness word near it, where
# ROADMAP.md's heading for that item is struck through or ticked.
if ! roadmap_stale=$(python3 - 2>&1 <<'PYEOF'
import re
from pathlib import Path

roadmap = Path("telegram-companion-bot/ROADMAP.md")
if not roadmap.exists():
    print("ROADMAP.md is missing — this check reads it as the source of truth")
    raise SystemExit
text = roadmap.read_text(encoding="utf-8")
shipped = set()
for m in re.finditer(r'^#{2,4}\s+(\d+\.\d+)(.*)$', text, re.M):
    head = m.group(2)
    if "✅" in head or "~~" in head or re.search(r'\b(shipped|done|closed)\b', head, re.I):
        shipped.add(m.group(1))

STALE = re.compile(r'unshipped|not yet shipped|no lock exists yet|no flock|yet —\s*ROADMAP'
                   r'|until it ships|tracks adding', re.I)
problems = []
docs = [Path("CLAUDE.md")] + sorted(Path(".claude").rglob("*.md"))
for f in docs:
    body = f.read_text(encoding="utf-8")
    for m in re.finditer(r'ROADMAP\s+(\d+\.\d+)', body):
        item = m.group(1)
        if item not in shipped:
            continue
        window = body[max(0, m.start() - 220):m.end() + 220]
        # C14 escape hatch, made by hand and visible — same shape as `sweep-ok`. The
        # constraints entry RECORDING this incident necessarily quotes the stale
        # sentence, and this check cannot tell a live claim from its own post-mortem.
        # Put `roadmap-ok:` plus the reason near the quote.
        if "roadmap-ok" in window:
            continue
        if STALE.search(window):
            problems.append(f"{f}: calls ROADMAP {item} unshipped, but ROADMAP.md marks it done")
if problems:
    print("\n".join(sorted(set(problems))) +
          "\n  — the doc describes the system as it was when written; re-read the thing "
          "that executes it and correct the claim")
PYEOF
); then
  roadmap_stale="the parser itself exited non-zero: ${roadmap_stale:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$roadmap_stale" ]; then
  ok "roadmap-claims-current: no doc calls a shipped ROADMAP item unshipped"
else
  bad "roadmap-claims-current" "$roadmap_stale"
fi

# --- verify-steps-covered -----------------------------------------------------------------
# C13 (seen 7): "a verification command that cannot fail is not verification". Every
# required step in verify.sh must be proved able to go red by verify-can-fail.sh — on
# 2026-08-10 one of them could not, and printed `ok  compile  bot.py` on a module that
# would not import for eight days before anyone asked.
# verify-can-fail.sh itself is far too slow for this suite (it runs the full block four
# times). This is the cheap half: it fails when verify.sh grows a step that nothing
# exercises, which is the drift that would let a decorative step back in unnoticed.
declare -a vsteps vcases
mapfile -t vsteps < <(grep -oE '^step "[^"]+"' .claude/tools/verify.sh | sed 's/^step "//;s/"$//' | awk '{print $1}')
mapfile -t vcases < <(grep -oE '^case_ "[0-9]+/[0-9]+ +[a-z_]+' .claude/tools/verify-can-fail.sh | awk '{print $NF}')
uncovered=""
for st in "${vsteps[@]}"; do
  found=0
  for c in "${vcases[@]}"; do [ "$st" = "$c" ] && found=1; done
  [ "$found" -eq 1 ] || uncovered="$uncovered $st"
done
if [ -z "$uncovered" ] && [ "${#vsteps[@]}" -gt 0 ]; then
  ok "verify-steps-covered: all ${#vsteps[@]} verify.sh step(s) exercised by verify-can-fail.sh"
elif [ "${#vsteps[@]}" -eq 0 ]; then
  bad "verify-steps-covered" "parsed 0 steps out of verify.sh — the parser broke, which is exactly the silent-green shape this check exists for"
else
  bad "verify-steps-covered" "verify.sh step(s) nothing proves can fail:$uncovered — add a case_ to .claude/tools/verify-can-fail.sh"
fi

# --- skill-refs-resolve ------------------------------------------------------------------
# Sibling of claude-md-refs-resolve, one level out. `skill-index-integrity` already proves
# the router and .claude/skills/ agree — but nothing checked the paths INSIDE a skill body,
# and a skill is loaded precisely when someone is about to act on what it says. A skill
# that sends the next session to a renamed tool is worse than no skill.
#
# Deliberately NARROWER than the CLAUDE.md check: only tokens containing a "/" count. A
# bare filename in prose (`atlas.txt`, `core.py`) is a mention, not a path claim, and
# resolving those against a list of candidate roots produced 16 false positives on the
# first run — a check that noisy on day one gets switched off. 35 real path claims are
# checked; requiring the slash is what makes the signal trustworthy.
#
# Found on its first run: voicekit-work cited `templates/voice_profile_template.json`,
# which lives at voicekit-starter/src/voicekit/templates/. Fixed in the same commit.
if ! skill_refs=$(python3 - 2>&1 <<'PYEOF'
import re
from pathlib import Path
ROOTS = ["", "telegram-companion-bot", ".claude", "voicekit-starter"]
EXTS = "md|sh|py|json|txt|yml|yaml|html|service|example|jsonl"
skills = sorted(Path(".claude/skills").glob("*/SKILL.md"))
missing = []
for sk in skills:
    # Strip fences first — same desync lesson as claude-md-refs-resolve (2026-07-31).
    text = re.sub(r"^```.*?^```", "", sk.read_text(encoding="utf-8"), flags=re.S | re.M)
    for tok in sorted(set(re.findall(r"`([^`]+)`", text))):
        if tok.startswith(("/", "~", "http")) or "/" not in tok:
            continue
        if tok.endswith("/"):
            cand = tok.rstrip("/")
            if not re.fullmatch(r"[.A-Za-z0-9_][A-Za-z0-9_./@-]*", cand):
                continue
        elif re.fullmatch(rf"[.A-Za-z0-9_@][A-Za-z0-9_./@-]*\.({EXTS})", tok):
            cand = tok
        else:
            continue
        if not any((Path(r) / cand).exists() for r in ROOTS):
            missing.append(f"{sk.parent.name}:{tok}")
if not skills:
    print("PARSE-FAIL: no SKILL.md files found — the glob broke, which is the silent-green "
          "shape this check exists to avoid")
elif missing:
    print("skills name paths that do not exist: " + ", ".join(missing))
PYEOF
); then
  skill_refs="the parser itself exited non-zero: ${skill_refs:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$skill_refs" ]; then
  ok "skill-refs-resolve: every repo path a SKILL.md names still exists"
else
  bad "skill-refs-resolve" "$skill_refs"
fi

# --- break-tester ------------------------------------------------------------------------
# `break-test.sh` edits a source file in place and restores it, so its failure mode is
# destroying source code — and its first version did. `mktemp` creates the snapshot file,
# so the EXIT trap's `[ -f "$SNAP" ]` guard was true BEFORE the snapshot was taken, and any
# early exit (a 0-match anchor, the exact 2026-08-10 failure the tool exists to catch)
# copied zero bytes over the target. bot.py was truncated to nothing by the very run that
# was checking the tool's own failure modes.
# The selftest drives all six paths on temp files and asserts the one invariant that was
# violated: whatever happens, the target is byte-identical afterwards.
selftest=$(bash .claude/tools/break-test-selftest.sh 2>&1)
if [ $? -eq 0 ]; then
  ok "break-tester: $(printf '%s' "$selftest" | tail -1)"
else
  bad "break-tester" "$(printf '%s' "$selftest" | tail -15)"
fi

# --- gate-corpus ------------------------------------------------------------------------
# The guards are themselves guarded. Every scanner in sweep.py and the delivery gate's
# handler-coverage check run against fixtures built to slip past a naive implementation —
# anchor slips, line-window escapes, substring collisions, deletion-only diff hunks, and a
# deliberately unparseable input that must make the gate fail CLOSED. 14 of the first 34
# cases deviated when this was written (2026-08-02), including the gate silently passing
# whenever sweep raised. It also fails if sweep.py stops parsing, which is how three
# docstring-boundary slips in one session would have been caught.
corpus=$(python3 .claude/tools/gate_corpus/run.py 2>&1)
if [ $? -eq 0 ]; then
  ok "gate-corpus: $(printf '%s' "$corpus" | tail -1)"
else
  bad "gate-corpus" "$(printf '%s' "$corpus" | tail -25)"
fi

# --- handlers-exercised -----------------------------------------------------------------
# The handlers whose defects reached the fleet BECAUSE their only tests read their source.
# `/features <name> on|off` raised ValueError on every invocation for four releases while
# two tests "covering" it stayed green (v2026-08-02.14). The delivery gate enforces this for
# handlers a diff touches; this pins the ones already paid for, so deleting the behavioural
# tests reds CI instead of quietly restoring the blind spot.
if ! exercised=$(python3 - 2>&1 <<'PYEOF'
import sys
sys.path.insert(0, ".claude/tools")
import sweep

REQUIRED = {
    "features_cmd": "v2026-08-02.14 — ValueError on every invocation, 4 releases, tests read the source",
    "setbase_cmd":  "v2026-08-02.4 + .14 — dispatch never fired, then a false backup claim",
    "dupefacts_cmd": "already driven end-to-end; keeps at least one worked example in the suite",
}
_, called = sweep._handler_coverage()
missing = [f"{n} ({why})" for n, why in REQUIRED.items() if n not in called]
if missing:
    print("no test CALLS these handlers: " + "; ".join(missing) +
          " — a test that reads a handler's source cannot fail for the reason the "
          "handler exists; drive it with fake Telegram objects instead")
PYEOF
); then
  exercised="the parser itself exited non-zero: ${exercised:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$exercised" ]; then
  ok "handlers-exercised: the handlers that shipped broken are driven by tests, not grepped"
else
  bad "handlers-exercised" "$exercised"
fi

# --- hooks-wired --------------------------------------------------------------------------
# A hook file that is not registered in settings.json is inert, and inert looks exactly like
# working: the file is present, readable, obviously intentional, and never runs. Nothing in
# the repo would say so. The same shape has already been paid for twice at a different
# layer — three Routine checks silently un-runnable (2026-07-29), eleven agent contracts
# gone dormant (2026-07-27) — both found by someone happening to look.
#
# Checks both directions, since either is a real defect:
#   a hook on disk that no event fires  ->  a guard everyone believes is on
#   a settings.json entry with no file  ->  a Stop chain that errors every turn
#
# Only *.sh count as entry points. The .py siblings (claim_guard.py, handoff_guard.py,
# host_guard.py) are called BY their wrappers and are correctly absent from settings.
if ! hooks_wired=$(python3 - 2>&1 <<'PYEOF'
import json, re
from pathlib import Path
settings = json.loads(Path(".claude/settings.json").read_text(encoding="utf-8"))
registered = set()
for event, matchers in (settings.get("hooks") or {}).items():
    for m in matchers:
        for h in m.get("hooks", []):
            for name in re.findall(r'([A-Za-z0-9_.-]+\.(?:sh|py))', h.get("command", "")):
                registered.add(name)
on_disk = {p.name for p in Path(".claude/hooks").glob("*.sh")}
problems = []
orphaned = sorted(on_disk - registered)
if orphaned:
    problems.append("hook file(s) on disk that settings.json never fires: " +
                    ", ".join(orphaned) + " — wire it into the right event, or delete it; "
                    "an unregistered hook is a guard everyone believes is on")
missing = sorted(n for n in registered
                 if n.endswith((".sh", ".py")) and not (Path(".claude/hooks") / n).exists())
if missing:
    problems.append("settings.json fires hook(s) that do not exist: " + ", ".join(missing))
if not on_disk:
    problems.append("found 0 hook files — the scan looked in the wrong place, which is not "
                    "the same as a clean result")
print("; ".join(problems))
PYEOF
); then
  hooks_wired="the parser itself exited non-zero: ${hooks_wired:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$hooks_wired" ]; then
  ok "hooks-wired: every .claude/hooks/*.sh is registered in settings.json, and every registered hook exists"
else
  bad "hooks-wired" "$hooks_wired"
fi

# --- oplog-search-works --------------------------------------------------------------------
# A search tool nobody notices has broken is worse than no search tool: an empty result
# reads as "we have never hit this" rather than "the parser is broken". This repo has paid
# for the dormancy shape three times (11 agent contracts 2026-07-27, three Routine checks
# 2026-07-29, the session-debrief skill 2026-08-11) and every one was found by someone
# happening to look.
#
# Two assertions: the tool still returns a known row for a known query (so a log-format
# change that breaks the row parser reds CI), and it exits NON-ZERO on a corpus it cannot
# parse rather than printing nothing and exiting 0.
if ! oplogsearch=$(python3 - 2>&1 <<'PYEOF'
import subprocess, sys, tempfile, os
from pathlib import Path
TOOL = ".claude/tools/oplog-search.py"
if not Path(TOOL).is_file():
    print(f"{TOOL} is missing — repo-debugging-playbook points sessions at it"); raise SystemExit(0)
problems = []

# 1. a known query still finds its row. The 2026-07-19 jules double-poller incident is one
#    of the oldest rows and its wording has been stable since it was written.
r = subprocess.run([sys.executable, TOOL, "duplicate process fighting over the same telegram token"],
                   capture_output=True, text=True)
if r.returncode != 0:
    problems.append(f"tool exited {r.returncode} on a normal query: {r.stderr.strip()[:200]}")
elif "2026-07-19" not in r.stdout:
    problems.append("the double-poller row no longer ranks in the top 5 for its own symptom "
                    "— either the row was reworded or the ranker broke; re-run "
                    ".claude/experiments/2026-08-21-oplog-retrieval/ before loosening this")

# 2. an unparseable corpus must FAIL, not return empty. Run in a temp cwd with a log the
#    row parser cannot read.
with tempfile.TemporaryDirectory() as d:
    (Path(d) / ".claude/memory").mkdir(parents=True)
    (Path(d) / ".claude/memory/operational-log.md").write_text("# no rows here\n", encoding="utf-8")
    r2 = subprocess.run([sys.executable, os.path.abspath(TOOL), "anything at all"],
                        capture_output=True, text=True, cwd=d)
    if r2.returncode == 0:
        problems.append("tool exited 0 on a log it could not parse — an empty result then "
                        "reads as 'never happened' instead of 'the parser is broken'")
print("; ".join(problems))
PYEOF
); then
  oplogsearch="the parser itself exited non-zero: ${oplogsearch:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$oplogsearch" ]; then
  ok "oplog-search-works: finds a known row for a known symptom, and fails loudly on a corpus it cannot parse"
else
  bad "oplog-search-works" "$oplogsearch"
fi

# --- constraints-mechanism-marked ----------------------------------------------------------
# session-audit.sh selects what it shows at startup by reading this file's graduation
# markers. That makes a prose file load-bearing for a hook, and prose drifts: reword one
# note and a constraint silently changes category. The dangerous direction is a prose-only
# constraint reading as guarded, because it then vanishes from the one line that surfaces it
# — a filter that quietly selects nothing, which is C13's shape at the startup layer.
#
# Written after the loose version of this parse got it wrong: `"graduat" in body` matches
# **Not graduated.** and counted C9/C10/C11/C20 as mechanised when they say the opposite.
# The rule is line-anchored and the two markers are mutually exclusive.
#
# Sibling of `claude-md-no-routing-table` in skill-index-integrity: both guard a prose file
# that something reads to decide what a session is handed, where drift has no symptom.
if ! cmark=$(python3 - 2>&1 <<'PYEOF'
import re
from pathlib import Path
txt = Path(".claude/memory/constraints.md").read_text(encoding="utf-8")
blocks = re.split(r'\n### (C\d+) — ', txt)
GUARD   = re.compile(r'^\*\*Graduated', re.M)
NOGUARD = re.compile(r'^\*\*Not graduated', re.M)
unmarked, ambiguous, total = [], [], 0
for i in range(1, len(blocks), 2):
    cid, body = blocks[i], blocks[i + 1].split("\n### ")[0]
    total += 1
    g, n = bool(GUARD.search(body)), bool(NOGUARD.search(body))
    if g and n:      ambiguous.append(cid)
    elif not g and not n: unmarked.append(cid)
problems = []
if total == 0:
    problems.append("parsed 0 constraints — the split pattern broke, and session-audit.sh "
                    "would show an empty list rather than fail")
if unmarked:
    problems.append("constraint(s) with neither marker: " + ", ".join(unmarked) +
                    " — every constraint needs a line starting `**Graduated` (naming the "
                    "hook/eval/scanner) or `**Not graduated` (saying why nothing mechanical "
                    "would see it); session-audit.sh cannot categorise an unmarked one")
if ambiguous:
    problems.append("constraint(s) with BOTH markers: " + ", ".join(ambiguous) +
                    " — they are mutually exclusive; the startup line would report it twice")

# The startup line TRUSTS a `**Graduated` marker: claiming one takes a constraint off the
# list of things a session must read. So the claim has to be true. A mechanism deleted
# along with its settings.json entry passes `hooks-wired` and leaves this claim standing,
# which silently hides an unguarded constraint — the exact direction that matters.
#
# Only tokens containing "/" count, the same narrowing `skill-refs-resolve` uses: a bare
# name in prose (`grep-c-fallback`, `roadmap-claims-current`) is an eval's name, not a path
# claim, and resolving those against candidate roots is how that check got 16 false
# positives on its first run.
for i in range(1, len(blocks), 2):
    cid, body = blocks[i], blocks[i + 1].split("\n### ")[0]
    for line in GUARD.findall(body) and [l for l in body.splitlines()
                                         if l.startswith("**Graduated")]:
        for tok in re.findall(r"`([^`]+)`", line):
            if "/" not in tok:
                continue
            if not Path(tok.strip().rstrip(".,;:")).exists():
                problems.append(
                    f"{cid} claims it graduated to `{tok}`, which does not exist — either "
                    f"the mechanism was deleted (so the constraint is unguarded and must "
                    f"go back on the startup line) or the path is wrong")
print("; ".join(problems))
PYEOF
); then
  cmark="the parser itself exited non-zero: ${cmark:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$cmark" ]; then
  ok "constraints-mechanism-marked: every constraint states whether a mechanism guards it"
else
  bad "constraints-mechanism-marked" "$cmark"
fi

# --- eval-parsers-fail-loudly -------------------------------------------------------------
# Most checks in this file are a shell capture of a python heredoc, where an empty result
# means PASS. If the parser dies, its traceback goes to stderr, the captured string is
# empty, and the check reports PASS — against whatever it was supposed to catch.
#
# Found 2026-08-21 by grepping for a mistake made three times in one session: **12 of the
# 15 captures in this file had it**, every one of them reporting PASS on a dead parser.
# Demonstrated, not assumed — a `raise` injected at the top of `claude-md-refs-resolve`'s
# parser printed `PASS  claude-md-refs-resolve: every repo path CLAUDE.md names still
# exists`. That is C13's exact shape (a verification that cannot fail is not verification)
# multiplied across most of the suite, and the gate-corpus finding — the delivery gate
# passing silently whenever sweep.py raised — arrived at from the opposite direction.
#
# Required shape, both halves:
#   if ! var=$(python3 - … 2>&1 <<'PYEOF'   ->  stderr captured AND exit status tested
#   ); then var="…parser died…"; fi
#
# Matches the shell construct, never prose, so a comment explaining the trap cannot trip
# it (C14 — which this session hit twice writing other scanners).
if ! parsers=$(python3 - 2>&1 <<'PYEOF'
import re
from pathlib import Path
lines = Path(".claude/evals/run-evals.sh").read_text(encoding="utf-8").split("\n")
CAP = re.compile(r"^\s*(if ! )?(\w+)=\$\(python3 - ?(.*?)<<'\w+'\s*$")
bad = []
total = 0
for n, line in enumerate(lines, 1):
    m = CAP.match(line)
    if not m:
        continue
    total += 1
    guarded, name, args = m.group(1), m.group(2), m.group(3)
    missing = []
    if "2>&1" not in args:
        missing.append("no 2>&1 (stderr discarded)")
    if not guarded:
        missing.append("no `if !` (exit status untested)")
    if missing:
        bad.append(f"line {n} ({name}): " + " and ".join(missing))
if total == 0:
    print("found 0 python-heredoc captures — the scan matched nothing, which is not the "
          "same as a clean result")
elif bad:
    print(f"{len(bad)} of {total} check(s) report PASS when their own parser dies: " +
          "; ".join(bad) + " — wrap as `if ! var=$(python3 - … 2>&1 <<'PYEOF'` and set "
          "var to a failure message in the `; then` branch")
PYEOF
); then
  parsers="the parser itself exited non-zero: ${parsers:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$parsers" ]; then
  ok "eval-parsers-fail-loudly: every python-heredoc check captures stderr and tests its parser's exit status"
else
  bad "eval-parsers-fail-loudly" "$parsers"
fi

# --- oplog-rows-are-index ---------------------------------------------------------------
# operational-log.md says of itself: "Format is fixed... nothing else. No narration, no
# diary... this file is the index of what the system learned." It had stopped being that.
# Nine rows had grown past 3,000 characters, the largest 7,724, because a live
# investigation kept appending to the row — and one of them was being reprinted in full
# into every session's startup context. The appended corrections were the valuable part;
# they now live in incidents/<date>-<slug>.md and the row links to them.
#
# Two things are checked, because the row shape has two ways to go wrong:
#   1. length — a row over the cap is an investigation that should have been archived
#   2. cell count — pipes inside inline code must be escaped `\|`, or markdown reads them
#      as separators. Three rows rendered with 7, 7 and 11 cells for weeks; nothing noticed
#      because a malformed table row still displays, just wrongly.
#
# 2>&1 and the exit-status test are not decoration: C13's eighth occurrence, hours before
# this check was written, was a sibling eval that captured only stdout and so reported PASS
# whenever its own parser died.
CAP=3000
if ! oplog=$(python3 - "$CAP" 2>&1 <<'PYEOF'
import re, sys
cap = int(sys.argv[1])
path = ".claude/memory/operational-log.md"
SPLIT = re.compile(r'(?<!\\)\|')          # a separator is a pipe that is not escaped
rows, long_rows, malformed = 0, [], []
for n, line in enumerate(open(path, encoding="utf-8"), 1):
    line = line.rstrip("\n")
    if not line.startswith("| 20"):
        continue
    rows += 1
    date = line[2:12]
    if len(line) > cap:
        long_rows.append(f"line {n} ({date}): {len(line)} chars")
    parts = [p for p in SPLIT.split(line)]
    if parts and parts[0].strip() == "": parts = parts[1:]
    if parts and parts[-1].strip() == "": parts = parts[:-1]
    if len(parts) != 6:
        malformed.append(f"line {n} ({date}): {len(parts)} cells")
if rows == 0:
    print("parsed 0 rows out of the log — the parser broke, which is the silent-green "
          "shape this check exists for")
elif malformed:
    print("row(s) not splitting into 6 cells: " + "; ".join(malformed) +
          " — escape pipes inside inline code as '\\|'; markdown reads a bare one as a "
          "column separator")
elif long_rows:
    print(f"row(s) over {cap} chars: " + "; ".join(long_rows) +
          " — move the full record to .claude/memory/incidents/<date>-<slug>.md and leave "
          "an index row linking to it (see the header of operational-log.md)")
PYEOF
); then
  oplog="the parser itself exited non-zero: ${oplog:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$oplog" ]; then
  ok "oplog-rows-are-index: every operational-log row is 6 cells and under ${CAP} chars"
else
  bad "oplog-rows-are-index" "$oplog"
fi

# --- grep-c-fallback --------------------------------------------------------------------
# C23, fourth occurrence. `grep -c` prints "0" AND exits 1 when there are no matches, so
# `x=$(grep -c … || echo 0)` stacks a second line onto output that already succeeded — x
# becomes "0\n0". It reads perfectly well, which is why it keeps coming back: written into
# debrief-check.sh 2026-08-11 (caught, fixed, left as a comment), then into session-audit.sh
# and this eval file, where it shipped a hook that announced "MYCELIUM: 0\n0 open message(s)"
# precisely when nothing was waiting.
#
# A comment in one file could not stop it recurring in three others. This is that comment,
# made mechanical. Correct form: `x=$(grep -c … 2>/dev/null); x=${x:-0}`.
#
# C14, twice over: the check must not flag the comments explaining the trap, nor its own
# error message quoting it. Comment lines are skipped, and the match requires a command
# substitution — the defect only exists when the stray line is being CAPTURED. Prose that
# names the pattern has no `$(`.
#
# The `$(` requirement also fixed a false negative found the same minute: an earlier
# `[^|]*` between `-c` and `||` could not cross the pipe inside `grep -c '| status: open$'`,
# so the exact line that shipped the bug would have passed. `.*` crosses it.
if ! gcf=$(python3 - 2>&1 <<'PYEOF'
import re, subprocess
from pathlib import Path
# Same shape via `|| true` counts too — it leaves the stray "0" line just as surely.
BAD = re.compile(r"grep\s+-c\b.*\|\|\s*(echo|true)")
hits = []
files = subprocess.run(["git", "ls-files", "*.sh", "*.bash"],
                       capture_output=True, text=True).stdout.split()
for f in files:
    for n, line in enumerate(Path(f).read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if line.lstrip().startswith("#") or "$(" not in line:
            continue
        if BAD.search(line):
            hits.append(f"{f}:{n}")
if not files:
    print("git ls-files matched no shell scripts — the scan found nothing because it "
          "looked nowhere, which is not the same as a clean result")
elif hits:
    print("`grep -c … || echo/true` at " + ", ".join(hits) +
          " — grep -c already prints 0 on no matches and exits 1, so the fallback appends "
          "a second line; use `x=$(grep -c … 2>/dev/null); x=${x:-0}`")
PYEOF
); then
  gcf="the parser itself exited non-zero: ${gcf:-(no output)} — a check that goes green when its own parser dies is not a check"
fi
if [ -z "$gcf" ]; then
  ok "grep-c-fallback: no shell script stacks a fallback onto grep -c (C23)"
else
  bad "grep-c-fallback" "$gcf"
fi

# --- mycelium-format --------------------------------------------------------------------
# session-audit.sh tells each new session how many mycelium messages are waiting, by
# grepping the entry header. A drifted header — renamed status, trailing space, missing
# field — does not error. It drops out of the count, and the next session is told nothing
# is waiting. That is the C13 shape: a reading that cannot report a problem is not a
# reading, and this one fails toward silence.
#
# The check parses every header independently and compares against the hook's own grep.
# Disagreement fails, whichever side drifted — the file's format or the hook that reads it.
myc=.claude/memory/mycelium.md
if [ ! -f "$myc" ]; then
  bad "mycelium-format" "$myc missing — session-audit.sh will silently stop reporting cross-session messages"
else
  # The hook's counter, character-for-character as session-audit.sh runs it.
  # NOT `|| echo 0` — grep -c prints "0" and exits 1 on no matches, so the fallback stacks
  # a second line and the parser below dies on int("0\n0"). Which it did, silently: with
  # only stdout captured, a crashing parser produced an empty error string and this check
  # reported PASS against a real violation. That is the gate-corpus finding (the delivery
  # gate passed whenever sweep.py raised) reproduced inside a new check, and it is why the
  # python call below is invoked with 2>&1 and its exit status tested.
  hook_open=$(grep '^### 20' "$myc" 2>/dev/null | grep -c '| status: open$'); hook_open=${hook_open:-0}
  if ! myc_err=$(python3 - "$myc" "$hook_open" 2>&1 <<'PYEOF'
import re, sys
path, hook_open = sys.argv[1], int(sys.argv[2])
HEADER = re.compile(
    r"^### 20\d{2}-\d{2}-\d{2} \| from: .+ \| to: .+ \| status: (open|ack|done)$")
bad_headers, statuses, in_fence = [], [], False
for n, line in enumerate(open(path, encoding="utf-8"), 1):
    line = line.rstrip("\n")
    # C14: a scanner cannot tell "this file does the bad thing" from "this file explains
    # it". The Entry format section documents the header shape inside a fence, and that
    # example is not an entry. Caught on this check's first run.
    if line.startswith("```"):
        in_fence = not in_fence
        continue
    if in_fence:
        continue
    # Outside a fence, every header line starts "### " — including a malformed one, which
    # is the case that must not pass silently.
    if not line.startswith("### "):
        continue
    m = HEADER.match(line)
    if m:
        statuses.append(m.group(1))
    else:
        bad_headers.append(f"line {n}: {line[:90]}")
if bad_headers:
    print("entry header(s) session-audit.sh cannot count: " + "; ".join(bad_headers) +
          " — required shape: '### YYYY-MM-DD | from: X | to: Y | status: open|ack|done'")
elif not statuses:
    print("parsed 0 entries out of the file — the parser broke, which is exactly the "
          "silent-green shape this check exists for")
else:
    parsed_open = statuses.count("open")
    if parsed_open != hook_open:
        print(f"the hook counts {hook_open} open entr(ies), an independent parse finds "
              f"{parsed_open} — session-audit.sh and {path} disagree about the format")
PYEOF
  ); then
    myc_err="the parser itself exited non-zero: ${myc_err:-(no output)} — a check that goes green when its own parser dies is not a check"
  fi
  if [ -z "$myc_err" ]; then
    ok "mycelium-format: every entry header is countable, and the hook's count matches an independent parse"
  else
    bad "mycelium-format" "$myc_err"
  fi
fi

# --- decisions-format -------------------------------------------------------------------
# The decision log (.claude/memory/decisions.md, 2026-08-25) records what we chose, what
# over, and why. Its entry header carries a status the file's own header promises is one of
# a fixed set — `current` or `superseded`. A drifted header (renamed status, trailing
# space, wrong date shape) does not error; it just reads as a non-entry and the log quietly
# loses that row's status. Same C13/silence shape as mycelium-format, minus the hook count
# (nothing surfaces a decisions count at startup — a decision does not age out, so there is
# no open queue to report). The check parses every non-fenced `### ` header and fails on any
# that is not the promised shape, and it is invoked with 2>&1 + exit-status test so a broken
# parser fails loud instead of green (the gate-corpus finding).
dec=.claude/memory/decisions.md
if [ ! -f "$dec" ]; then
  bad "decisions-format" "$dec missing — the decision log CLAUDE.md #9 and log-decision point at is gone"
else
  if ! dec_err=$(python3 - "$dec" 2>&1 <<'PYEOF'
import re, sys
path = sys.argv[1]
HEADER = re.compile(r"^### 20\d{2}-\d{2}-\d{2} \| .+ \| status: (current|superseded)$")
bad_headers, statuses, in_fence = [], [], False
for n, line in enumerate(open(path, encoding="utf-8"), 1):
    line = line.rstrip("\n")
    # C14: the Entry format section documents the header shape inside a fence, and the
    # seed entries use a "(seed)" prefix instead of a date — both are legal non-entries.
    if line.startswith("```"):
        in_fence = not in_fence
        continue
    if in_fence:
        continue
    if not line.startswith("### 20"):
        continue
    m = HEADER.match(line)
    if m:
        statuses.append(m.group(1))
    else:
        bad_headers.append(f"line {n}: {line[:90]}")
if bad_headers:
    print("decision header(s) not in the promised shape: " + "; ".join(bad_headers) +
          " — required: '### YYYY-MM-DD | <title> | status: current|superseded'")
elif not statuses:
    print("parsed 0 dated entries out of the file — the parser broke, which is exactly "
          "the silent-green shape this check exists for")
PYEOF
  ); then
    dec_err="the parser itself exited non-zero: ${dec_err:-(no output)} — a check that goes green when its own parser dies is not a check"
  fi
  if [ -z "$dec_err" ]; then
    ok "decisions-format: every dated decision header is well-formed"
  else
    bad "decisions-format" "$dec_err"
  fi
fi

# --- skill-impact-format ----------------------------------------------------------------
# session-audit.sh tells each new session how many interventions are still `pending` — the
# class-targeting changes whose efficacy is unconfirmed — by grepping the entry header. A
# drifted header (renamed status, trailing space, missing field) does not error; it drops
# out of the count and the next session is told nothing is waiting. Identical C13/silence
# shape to mycelium-format, so it is guarded identically: parse every non-fenced header
# independently, compare `pending` against the hook's own grep, and run the parser with
# 2>&1 + exit-status test so a broken parser fails loud, not green (the gate-corpus finding).
si=.claude/memory/skill-impact.md
if [ ! -f "$si" ]; then
  bad "skill-impact-format" "$si missing — session-audit.sh will silently stop reporting pending interventions"
else
  hook_pending=$(grep '^### 20' "$si" 2>/dev/null | grep -c '| status: pending$'); hook_pending=${hook_pending:-0}
  if ! si_err=$(python3 - "$si" "$hook_pending" 2>&1 <<'PYEOF'
import re, sys
path, hook_pending = sys.argv[1], int(sys.argv[2])
HEADER = re.compile(
    r"^### 20\d{2}-\d{2}-\d{2} \| intervention: .+ \| class: .+ \| status: (pending|holding|recurred)$")
bad_headers, statuses, in_fence = [], [], False
for n, line in enumerate(open(path, encoding="utf-8"), 1):
    line = line.rstrip("\n")
    # C14: the Entry format section documents the header shape inside a fence; that example
    # is not a row and must not be counted.
    if line.startswith("```"):
        in_fence = not in_fence
        continue
    if in_fence:
        continue
    if not line.startswith("### 20"):
        continue
    m = HEADER.match(line)
    if m:
        statuses.append(m.group(1))
    else:
        bad_headers.append(f"line {n}: {line[:90]}")
if bad_headers:
    print("row header(s) session-audit.sh cannot count: " + "; ".join(bad_headers) +
          " — required shape: '### YYYY-MM-DD | intervention: X | class: Y | status: pending|holding|recurred'")
elif not statuses:
    print("parsed 0 rows out of the file — the parser broke, which is exactly the "
          "silent-green shape this check exists for")
else:
    parsed_pending = statuses.count("pending")
    if parsed_pending != hook_pending:
        print(f"the hook counts {hook_pending} pending row(s), an independent parse finds "
              f"{parsed_pending} — session-audit.sh and {path} disagree about the format")
PYEOF
  ); then
    si_err="the parser itself exited non-zero: ${si_err:-(no output)} — a check that goes green when its own parser dies is not a check"
  fi
  if [ -z "$si_err" ]; then
    ok "skill-impact-format: every row header is countable, and the hook's pending count matches an independent parse"
  else
    bad "skill-impact-format" "$si_err"
  fi
fi

# --- mycelium-startup-routing -----------------------------------------------------------
# 2026-08-24: Mycelium was wired into Claude Code's SessionStart hook, but the Codex
# entrypoint only described the repo's context system in general. A new Codex session
# could therefore start non-trivial work without reading the open cross-session messages.
# Pin both always-loaded instruction files: CLAUDE.md owns the all-harness rule, while
# AGENTS.md tells harnesses without the Claude hook (including Codex) to inspect directly.
if ! myc_route_err=$(python3 - AGENTS.md CLAUDE.md 2>&1 <<'PYEOF'
import re, sys
from pathlib import Path

requirements = {
    "AGENTS.md": (
        r"mycelium\.md` — every session:.*status: open.*before non-trivial work.*including Codex",
        "put .claude/memory/mycelium.md in the every-session read order, including the "
        "direct Codex fallback",
    ),
    "CLAUDE.md": (
        r"Session continuity — every harness:.*before non-trivial work.*mycelium\.md.*"
        r"status: open.*Codex.*inspect the file directly",
        "restore the all-harness Mycelium rule and the direct Codex fallback under "
        "CLAUDE.md's Operating rule",
    ),
}
problems = []
for path in sys.argv[1:]:
    text = " ".join(Path(path).read_text(encoding="utf-8").split())
    pattern, remedy = requirements[path]
    if not re.search(pattern, text):
        problems.append(f"{path}: {remedy}")
print("; ".join(problems))
PYEOF
); then
  myc_route_err="the parser itself exited non-zero: ${myc_route_err:-(no output)} — a startup check that dies green leaves new sessions uninformed"
fi
if [ -z "$myc_route_err" ]; then
  ok "mycelium-startup-routing: Claude and Codex entrypoints require reading open messages before non-trivial work"
else
  bad "mycelium-startup-routing" "$myc_route_err"
fi

# --- mechanism-recurrence-surfaced ------------------------------------------------------
# The learning layer graduates a repeated mistake into a guard (constraints.md rule 4), but
# for months nothing asked the next question — did the mistake keep happening AFTER the guard
# shipped? C8 sat at seen 8 while counted among the guarded constraints, and only a chance
# substring-bug fix surfaced it (mycelium 2026-08-21). session-audit.sh now prints a
# MECHANISM REVIEW line for any guard whose newest seen date postdates its earliest dated
# graduation — a prompt to read the prose, deliberately NOT a verdict that the guard failed
# (most guards state a half they cannot cover, and a later occurrence there is the guard
# working as designed; hubris rule 1).
#
# This pins that the surfacing still works and stays honest: it exercises the REAL hook
# (a re-implementation here would test the eval, not the startup code — C8/C22) against a
# fixture with one flaggable case and two that must not flag, and fails toward LOUD — a dead
# parser prints no constraints line, which this reads as failure, not as "nothing to review".
sa=.claude/hooks/session-audit.sh
if [ ! -f "$sa" ]; then
  bad "mechanism-recurrence-surfaced" "$sa missing — the startup 'is each guard still earning its place' review is gone"
else
  mrs_abs="$PWD/$sa"
  mrs_tmp=$(mktemp -d)
  mkdir -p "$mrs_tmp/.claude/memory"
  # ' — ' below is an em dash: the header-split regex requires it, same as the real file.
  cat > "$mrs_tmp/.claude/memory/constraints.md" <<'FIX'
# constraints fixture

### C81 — recurred after a dated guard (must flag)
**seen: 3** (2026-01-01, 2026-03-01)
**Graduated 2026-02-01:** guard.sh — a Stop hook.

### C82 — recurred only before its dated guard (must not flag)
**seen: 2** (2026-01-01, 2026-01-15)
**Graduated 2026-02-01:** guard.sh — a Stop hook.

### C83 — recurred, but graduation is undated so timing is undecidable (must not flag)
**seen: 2** (2026-01-01, 2026-03-01)
**Graduated:** guard.sh — a Stop hook.

### C84 — recurred after its guard but BEFORE the last debrief (reviewed; must NOT be in MECHANISM REVIEW)
**seen: 2** (2026-01-01, 2026-02-10)
**Graduated 2026-02-01:** guard.sh — a Stop hook.
FIX
  # A last-debrief date makes the recurrence check a FRESHNESS check: C81's newest date
  # (2026-03-01) postdates this, so it is unreviewed and stays loud; C84's (2026-02-10)
  # predates it, so it was already triaged and must demote to the reviewed count.
  cat > "$mrs_tmp/.claude/memory/debrief-log.md" <<'DBRF'
# debrief log
| 2026-02-15 | abc1234 | a session |
DBRF
  # 2>&1 so a parser death lands in the captured text; the git/mycelium/debrief lines of the
  # hook noop harmlessly in a bare temp dir.
  mrs_out=$(CLAUDE_PROJECT_DIR="$mrs_tmp" bash "$mrs_abs" 2>&1)
  rm -rf "$mrs_tmp"
  mrs_review=$(printf '%s\n' "$mrs_out" | grep 'MECHANISM REVIEW' || true)
  mrs_undated=$(printf '%s\n' "$mrs_out" | grep 'UNDATED GRADUATION' || true)
  if ! printf '%s\n' "$mrs_out" | grep -q 'constraints (.claude/memory/constraints.md)'; then
    bad "mechanism-recurrence-surfaced" "the hook printed no constraints line for the fixture — its parser died and the review fails toward silence (C13)"
  elif ! printf '%s' "$mrs_review" | grep -q 'C81'; then
    bad "mechanism-recurrence-surfaced" "C81 recurred after its dated guard yet MECHANISM REVIEW did not name it — the post-graduation-recurrence check is dead or its timing compare is broken"
  elif printf '%s' "$mrs_review" | grep -qE 'C82|C83'; then
    bad "mechanism-recurrence-surfaced" "MECHANISM REVIEW named C82 (recurred only before its guard) or C83 (undated guard) — flagging a case whose timing is not after a dated mechanism is a false accusation (hubris rule 1)"
  elif printf '%s' "$mrs_review" | grep -q 'C84'; then
    bad "mechanism-recurrence-surfaced" "C84 recurred after its guard but BEFORE the last debrief (already reviewed) yet MECHANISM REVIEW named it — the freshness split is broken; a triaged recurrence must demote to the reviewed count, not stay in the loud line that C8 turned into wallpaper"
  elif ! printf '%s\n' "$mrs_out" | grep -q 'already reviewed at the last debrief'; then
    bad "mechanism-recurrence-surfaced" "C84 recurred before the last debrief but no 'already reviewed at the last debrief' line appeared — the demoted-recurrence count is dead, so stale recurrences vanish silently instead of collapsing to a count (fails toward silence, C13)"
  elif ! printf '%s' "$mrs_undated" | grep -q 'C83'; then
    bad "mechanism-recurrence-surfaced" "C83 has an undated graduation yet UNDATED GRADUATION did not name it — an uncheckable guard is being skipped silently, the blind spot this widening closed (C8 at seen 8)"
  elif printf '%s' "$mrs_undated" | grep -qE 'C81|C82'; then
    bad "mechanism-recurrence-surfaced" "UNDATED GRADUATION named C81 or C82, which carry dated graduations — the undated detector is misfiring on dated guards"
  else
    ok "mechanism-recurrence-surfaced: recurrence since the last debrief flagged loud, pre-guard/undated kept out of it, already-reviewed recurrence demoted to a count, and undated graduations surfaced to be dated"
  fi
fi

# --- fleet-config-drift -----------------------------------------------------------------
# All 7 instances share one bot.py but differ in context files, cards, and preset layers.
# Drift accumulates silently — a new context file added to 4 instances but not the other
# 3, or a card key present on 2 instances but not the rest. fleet-config-check.py catches
# this by majority rule: if 4+ instances have something, the ones that don't are flagged.
#
# The checker exits 1 when issues exist. The eval captures its output and reports it.
if ! fcd=$(python3 .claude/tools/fleet-config-check.py 2>&1); then
  fcd_msg=$(echo "$fcd" | grep -v '^fleet-config-check:')
  bad "fleet-config-drift" "$fcd_msg"
else
  ok "fleet-config-drift: all 7 instances consistent (file presence, card schema, preset layers)"
fi

echo
if [ "$skipped" -gt 0 ]; then
  echo "evals: ${pass} passed, ${fail} failed, ${skipped} skipped (skips never happen in CI — install requirements.lock to run everything locally)"
else
  echo "evals: ${pass} passed, ${fail} failed"
fi
[ "$fail" -eq 0 ]
