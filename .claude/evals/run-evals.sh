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

# Incident 2026-07-05: watchdog.sh restarted the whole healthy fleet forever because
# bot.py stopped writing the .alive heartbeat. The repeating job must stay registered.
if grep -q 'run_repeating(_touch_alive' "$BOT"; then
  ok "heartbeat-alive: _touch_alive repeating job registered"
else
  bad "heartbeat-alive" "run_repeating(_touch_alive...) missing — watchdog.sh will judge every bot frozen and restart the fleet forever"
fi

# Incident v2026-07-05.8: PTB's run_polling() silently overrides signal.signal() handlers;
# shutdown logging must be wired via post_shutdown, not a plain signal handler.
if grep -q '\.post_shutdown(_on_shutdown)' "$BOT"; then
  ok "graceful-shutdown: post_shutdown hook wired"
else
  bad "graceful-shutdown" ".post_shutdown(_on_shutdown) missing — SIGTERM diagnostics (phantom-killer triage) are lost"
fi

# Incident: bare 'python' in a launcher crash-looped bots with ModuleNotFoundError when
# the venv wasn't on PATH. The supervisor must invoke the venv interpreter explicitly.
if grep -q 'venv/bin/python' telegram-companion-bot/run-bot.sh; then
  ok "venv-explicit-python: run-bot.sh launches via venv/bin/python"
else
  bad "venv-explicit-python" "run-bot.sh no longer uses the explicit venv interpreter"
fi

# Incident v2026-07-05.5: missing tzdata made ZoneInfo silently fall back, then a
# tz-aware reminder vs naive now() TypeError killed bots at startup. Keep it pinned.
if grep -q '^tzdata' telegram-companion-bot/requirements.txt; then
  ok "tzdata-pinned: tzdata present in requirements.txt"
else
  bad "tzdata-pinned" "tzdata missing from requirements.txt — Termux has no system tz database"
fi

# Tokens must never land in the repo. The risk-guard hook blocks `git add .env`, but a
# token pasted into a card, a doc, or a committed backup file would slip past it — this
# repo is pulled from over raw public URLs, so a leaked token is instantly public.
# Patterns: Telegram bot token (digits:35-char secret), OpenAI-style sk- key, AWS key ID.
leaks=$(git grep -InE '[0-9]{8,10}:[A-Za-z0-9_-]{35}([^A-Za-z0-9_-]|$)|\bsk-[A-Za-z0-9]{32,}|\bAKIA[0-9A-Z]{16}\b' -- . ':!.claude/evals/run-evals.sh' 2>/dev/null || true)
if [ -z "$leaks" ]; then
  ok "secret-scan: no token-shaped strings in tracked files"
else
  bad "secret-scan" "possible credential committed: $(echo "$leaks" | head -3 | tr '\n' ' ')"
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
    skip "bot-imports" "dependency missing in this environment ($import_exc). Run 'pip install -r telegram-companion-bot/requirements.txt' to make this check runnable — this is NOT a bot.py defect"
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
doc_unguarded=$(python3 - "$BOT" <<'PYEOF'
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
)
if [ -z "$doc_unguarded" ]; then
  ok "document-reply-leak-guard-optout: every DOCUMENT_MODEL reply site opts out of the reasoning-leak guard"
else
  bad "document-reply-leak-guard-optout" "reply_with_typing(model=DOCUMENT_MODEL) without leak_guard=False at line(s) $doc_unguarded — a card review trips every reasoning-leak marker, and DOCUMENT_MODEL passes no fallback, so the owner gets '❌ something broke on my end' instead of the review (see v2026-08-03.1)"
fi

# The operating machinery itself: hooks must parse, settings.json must be valid JSON.
hook_bad=""
for h in .claude/hooks/*.sh telegram-companion-bot/*.sh; do
  bash -n "$h" 2>/dev/null || hook_bad="$hook_bad $h"
done
if [ -z "$hook_bad" ]; then
  ok "shell-scripts-parse: all hook + bot shell scripts pass bash -n"
else
  bad "shell-scripts-parse" "syntax errors in:$hook_bad"
fi
if [ -f .claude/settings.json ]; then
  if python3 -m json.tool .claude/settings.json >/dev/null 2>&1; then
    ok "settings-valid-json: .claude/settings.json parses"
  else
    bad "settings-valid-json" ".claude/settings.json is invalid JSON — every hook silently dies"
  fi
fi

# The repo went private 2026-07-28, so every raw.githubusercontent.com URL 404s. On
# 2026-07-29 a runnable `curl -fsSL <raw-base>/deploy/vps-sync.sh` was handed to the
# operator straight out of CLAUDE.md's Deployment block — it failed twice over, once on
# the literal placeholder and once because the URL is dead. Docs are where deploy
# commands get copied from, so a stale one is an outage waiting for someone to trust it.
# Runnable = the line starts with curl/wget or assigns a BASE/REPO var. Annotated
# history is fine: mark the block DEAD, Historical, or Superseded within 3 lines above.
raw_stale=$(python3 - <<'PY'
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
)
if [ -z "$raw_stale" ]; then
  ok "no-live-raw-urls: no runnable raw.githubusercontent command left unannotated"
else
  bad "no-live-raw-urls" "raw URLs 404 (private repo) but these still read as runnable: $raw_stale"
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
unrendered=$(python3 - "$BOT" "$api_only" <<'PYEOF'
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
)
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
env_drift=$(python3 - "$BOT" "$(dirname "$BOT")/.env.example" <<'PYEOF'
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
)
if [ -z "$env_drift" ]; then
  ok "env-vars-documented: .env.example accounts for every var bot.py reads"
else
  bad "env-vars-documented" "$env_drift"
fi

# Routine prompts must not instruct a fired session to use tooling it cannot have.
# 2026-07-29: ops-brief-daily's CI check and hygiene-check-weekly's CI + Routine-sync
# checks had been silently un-runnable. Fired sessions carry NO MCP tools, and in this
# environment the GitHub REST API is MCP-only — the agent proxy 403s api.github.com with
# or without a token. The prompts' documented fallback was an unauthenticated WebFetch of
# api.github.com annotated "(public repo)", which also broke when the repo went private
# on 2026-07-28. Both failed safe (skipped, never green) so nothing ever alerted.
# Removing hygiene check #4 also removed the only automatic Routine-drift detector, so
# this eval guards the file instead.
routine_dead=$(python3 - <<'PYEOF'
import re, pathlib
p = pathlib.Path('.claude/operating/routines.md')
if not p.exists():
    print("routines.md missing"); raise SystemExit
src = p.read_text()
problems = []
# Scope every check to the "### Verbatim prompt" fenced blocks. Prose OUTSIDE them
# documents these dead paths on purpose (why they were removed) and must stay legal —
# a file-wide match would flag the fix's own changelog.
for sec in re.split(r'\n## ', src):
    name = sec.split('\n', 1)[0].strip()
    for block in re.findall(r'### Verbatim prompt\n\n```\n(.*?)\n```', sec, re.S):
        if 'api.github.com' in block:
            problems.append(f'{name}: prompt calls api.github.com (MCP-only; proxy 403s it)')
        if '(public repo)' in block:
            problems.append(f'{name}: prompt claims "(public repo)" (private since 2026-07-28)')
        if re.search(r'if the claude-code-remote MCP list_triggers tool is available', block):
            problems.append(f'{name}: prompt calls list_triggers (fired sessions carry no MCP)')
print(" | ".join(problems))
PYEOF
)
if [ -z "$routine_dead" ]; then
  ok "routine-prompts-runnable: no Routine prompt depends on MCP-only or private-repo access"
else
  bad "routine-prompts-runnable" "$routine_dead"
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
skill_index=$(python3 - <<'PYEOF'
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

print(" | ".join(problems))
PYEOF
)
if [ -z "$skill_index" ]; then
  ok "skill-index-integrity: skill-router's table and .claude/skills/ agree, both directions"
else
  bad "skill-index-integrity" "$skill_index"
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
runtime_pin=$(python3 - <<'PYEOF'
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
)
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
md_refs=$(python3 - <<'PYEOF'
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
)
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
roadmap_stale=$(python3 - <<'PYEOF'
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
)
if [ -z "$roadmap_stale" ]; then
  ok "roadmap-claims-current: no doc calls a shipped ROADMAP item unshipped"
else
  bad "roadmap-claims-current" "$roadmap_stale"
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
exercised=$(python3 - <<'PYEOF'
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
)
if [ -z "$exercised" ]; then
  ok "handlers-exercised: the handlers that shipped broken are driven by tests, not grepped"
else
  bad "handlers-exercised" "$exercised"
fi

echo
if [ "$skipped" -gt 0 ]; then
  echo "evals: ${pass} passed, ${fail} failed, ${skipped} skipped (skips never happen in CI — install requirements.txt to run everything locally)"
else
  echo "evals: ${pass} passed, ${fail} failed"
fi
[ "$fail" -eq 0 ]
