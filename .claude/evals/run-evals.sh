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

echo
if [ "$skipped" -gt 0 ]; then
  echo "evals: ${pass} passed, ${fail} failed, ${skipped} skipped (skips never happen in CI — install requirements.txt to run everything locally)"
else
  echo "evals: ${pass} passed, ${fail} failed"
fi
[ "$fail" -eq 0 ]
