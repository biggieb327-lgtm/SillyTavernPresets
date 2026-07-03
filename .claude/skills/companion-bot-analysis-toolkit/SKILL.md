---
name: companion-bot-analysis-toolkit
description: >
  First-principles proof-and-analysis toolkit for telegram-companion-bot: eight
  investigation methods, each a runnable recipe with a worked example from real
  project history. Load this when: investigating ANY non-trivial bug (especially
  one that only reproduces on the owner's Termux/Android device); about to assert
  "the cause is X" or "this mechanism works" and you need to PROVE it first;
  testing a single bot.py function in isolation (bot.py cannot be imported);
  checking whether a regex actually matches a real message; building a synthetic
  fixture (audio, JSON, text) to exercise an algorithm offline; deciding which
  code version is actually running on the device; reasoning from an absent log
  line; reconstructing what prompt the model actually saw; or integrating a new
  external API from a reference implementation. Do NOT use for: picking the FIRST
  command for a reported symptom (companion-bot-debugging-playbook has the
  symptom-to-first-command map); the shipping evidence checklist before a commit
  (companion-bot-validation-and-qa); interpreting /diag, /status, or log-tag
  output in isolation (companion-bot-diagnostics); recall-quality investigations
  (companion-bot-memory-campaign); or proactive timing/tone tuning
  (companion-bot-proactive-tuning-campaign).
---

# Companion-bot analysis toolkit

Investigation methodology for telegram-companion-bot (2026-07-02). The product is one
~8,900-line `telegram-companion-bot/bot.py` running six Telegram companion instances on a
Termux/Android phone that you can NEVER touch. All device evidence arrives as owner-pasted
output. There is no test suite and no CI.

**The core rule: "prove it" means reproducing the mechanism in an isolated executable check
before asserting it.** A hypothesis you have not executed is a guess. Every method below
converts a claim into something that runs and returns evidence.

Pick the method by what you're proving:

| You need to prove... | Method |
|---|---|
| Which hypothesis explains a device-only bug | 1. Remote hypothesis bisection |
| A regex/condition does (or does not) fire on real input | 2. Regex/behavior falsification |
| A bot.py function behaves as claimed | 3. AST-extraction dry run |
| An algorithm handles a specific input property | 4. Synthetic-fixture proof |
| Which code version is actually running | 5. Deployed-vs-repo differential |
| A subsystem did NOT fire | 6. Log-absence reasoning |
| What the model actually saw in its prompt | 7. Prompt-assembly audit |
| A new API integration's contract | 8. API-contract verification |

Method 5 comes FIRST in any device investigation: never debug logic until you have proven
which code runs.

---

## 1. Remote hypothesis bisection

**WHEN:** The bug only reproduces on the device. You cannot run anything there yourself;
the owner runs commands and pastes output.

**RECIPE:**

1. Write down the competing hypotheses explicitly (H1, H2, ...).
2. For the hypothesis you can split cheapest, design ONE command whose output is
   *guaranteed to differ* depending on whether the hypothesis is true or false. If you
   cannot state in advance what output means true and what means false, the command is
   not a discriminator — redesign it.
3. Send the owner exactly one command per message, with the two expected outputs and
   what each implies.
4. Branch on the pasted result. Eliminate, don't accumulate: a hypothesis stays alive
   only until a discriminator kills it.

Command-authoring constraints (violating these wastes an owner round-trip):

- **Zero dollar signs.** The owner's chat client strips `$...$` spans as math markup, so
  `$(...)`, `$HOME`, `$1` silently vanish before the shell sees them. Use `~`, literal
  paths, and backtick-free constructions.
- **Single purpose.** One command, one bit of evidence. No `&&` chains that hide which
  step produced the output.
- If pasted output looks impossible, suspect paste corruption before suspecting the
  device: have the owner re-run the command piped through `cat -A` to reveal what the
  shell actually received.

**WORKED EXAMPLE A — the nohup→setsid fix (commit a080f99).** Symptom: watchdog loop died
after reboot. Bisection chain, one command per step: (1) wake-lock timing hypothesis —
discriminator showed wake-lock was acquired, eliminated; (2) does the boot script even
finish? — a completion echo appended to the script appeared in the log, so the script ran
to the end, eliminated "script dies early"; (3) is the deployed script the same as the
repo's? — grep for a marker line in the deployed copy, matched, eliminated stale deploy;
(4) the decisive split: have the owner launch the watchdog loop *directly* in a shell
vs *wrapped* the way the boot script does. Direct survived; wrapped died. That isolated
the wrapper: `nohup` does not create a new session, so Android killed the whole process
group when the parent went away. Fix: `setsid`. Verified live with a `pgrep` for the
watchdog process after reboot.

**WORKED EXAMPLE B — exoneration is a valid outcome (commit 6a8061f).** Symptom: "she
texted me out of nowhere mid-conversation." Prime suspects were the follow-up scheduler
and the heartbeat. Discriminators (log-tag greps around the timestamp) EXONERATED both —
their tags were absent at the incident time — before a third grep found the event-reminder
path guilty. The method's value was proving two plausible suspects innocent with evidence,
not just finding the culprit. Fix: defer event-reminder nudges during an active
conversation.

**FAILURE MODE of the method:** Sending a multi-step or `$`-containing command. The chat
client mangles it, the owner pastes garbage or partial output, and you branch on corrupted
evidence — worse than no evidence. Also: a "discriminator" whose output you would explain
away either way is not a discriminator; it's confirmation bias with extra steps.

---

## 2. Regex/behavior falsification

**WHEN:** A hypothesis has the shape "pattern P matched (or failed to match) message M" or
"condition C was true for input I." This is the cheapest kill in the toolkit — one
`python3 -c` line.

**RECIPE:** Copy the REAL pattern from the source (do not retype it — retyping introduces
the exact transcription errors you're testing for) and run it against the REAL input text
from the incident:

```bash
python3 - <<'EOF'
import re
# Pasted verbatim from bot.py:7785 — keep in sync with the source.
_FOLLOWUP_RE = re.compile(
    r"\b(hold on|hold up|brb|be right back"
    r"|give me a (sec|second|minute|min)"
    r"|wait a (sec|second|minute|min)"
    r"|gimme a (sec|second|minute)|just a (sec|second|minute)"
    r"|back in a (sec|second|minute|bit)"
    r"|give me a moment|one moment)\b",
    re.IGNORECASE,
)
msg = "the exact incident message text, pasted verbatim"
print(repr(_FOLLOWUP_RE.search(msg)))
EOF
```

`None` kills "the regex triggered it." A match object confirms the mechanism and gives
you the matched span. Either way you have proof, not opinion.

**WORKED EXAMPLE:** During a follow-up misfire investigation, the plausible hypothesis was
that `_FOLLOWUP_RE` had matched the bot's outgoing message and scheduled the rogue
follow-up. Executing the real pattern against the real message returned `None` — hypothesis
dead in one step, hours of reading the scheduler saved. (Note the gate at bot.py:7366 also
requires `FOLLOWUP_ENABLED`, a job queue, and vibe != "in-person" — a regex match alone is
necessary, not sufficient. Falsify the whole condition if the regex passes.)

**FAILURE MODE of the method:** Testing a paraphrase — a retyped pattern or a "roughly
what he said" message. The bug is often IN the exact characters (a stray space, a
curly quote, a `\b` boundary against punctuation). Verbatim source, verbatim input, or
the test proves nothing.

---

## 3. AST-extraction dry run

**WHEN:** You need to execute one function from bot.py. `import bot` is impossible: module
import runs dotenv loading, file reads, and network setup at top level. This is the house
pattern for unit-testing anything in an un-importable module.

**RECIPE:** Parse the file, extract the target function's exact source segment, `exec` it
in a controlled namespace, call it with hand-built inputs of known expected output.

Full runnable skeleton — executed successfully against the real bot.py on 2026-07-02
(target `describe_voice_profile`, bot.py:6886), printed
`AST dry run PASS: emotion=warm, pitch=low`:

```python
import ast

SRC_PATH = "telegram-companion-bot/bot.py"   # un-importable module
TARGET = "describe_voice_profile"            # function under test

src = open(SRC_PATH).read()
tree = ast.parse(src)
seg = next(ast.get_source_segment(src, n) for n in tree.body
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == TARGET)

ns = {}          # controlled namespace: add stub deps here if exec raises NameError
exec(seg, ns)
fn = ns[TARGET]

# Hand-built inputs with KNOWN expected outputs
assert fn(None) is None
assert fn({}) is None
assert fn({"emotion": [{"label": "warm"}], "pitch": [{"label": "low"}]}) == "emotion=warm, pitch=low"
assert fn({"vocalStyle": [{}]}) == "style=?"
print("AST dry run PASS:", fn({"emotion": [{"label": "warm"}], "pitch": [{"label": "low"}]}))
```

Adaptation notes:

- The `next(...)` only walks `tree.body` — top-level functions. For a method or nested
  function, walk with `ast.walk(tree)` instead.
- When the extracted function references module globals (`os`, a config constant, a
  helper), the `exec`'d call raises `NameError`. Add exactly those names to `ns` as
  imports or stubs — stubbing is a feature: you control every dependency's behavior.
- Async functions: extract the same way, drive with `asyncio.run(fn(...))`, and stub
  awaited dependencies with async stubs.

**WORKED EXAMPLE:** The run above. Four asserts covered the None/empty guards, the happy
path, and the `'?'` fallback for a label-less entry — chosen because each maps to a
distinct branch in the 10-line function.

**FAILURE MODE of the method:** Under-stubbing that silently succeeds: a stub returning
`None` or `MagicMock()` lets the function "pass" while exercising none of its real logic.
Every stub's return value must be a realistic value you chose deliberately, and every
assert must check an output you computed by hand BEFORE running. Also: the extracted
segment tests the REPO's function — pair with Method 5 before claiming anything about
device behavior.

---

## 4. Synthetic-fixture proof

**WHEN:** You need to prove an algorithm handles an input property (a pause in audio, a
malformed field, an edge-case date) and no real input with that property is at hand — or
real inputs are too entangled to isolate the property.

**RECIPE:**

1. List the capabilities you're claiming the algorithm has ("detects pauses", "measures
   pitch variation", "survives zero-length input").
2. Build a fixture where each claimed capability maps to a feature the fixture
   EXPLICITLY contains, with known ground truth ("there is exactly one 0.8 s silent gap
   starting at 2.0 s").
3. Run the real algorithm (via Method 3 if it lives in an un-importable module) against
   the fixture and check the output against the ground truth per feature.
4. If a feature is not detected, determine whether the algorithm is wrong or the fixture
   is unrealistic in the dimension the algorithm measures — read the algorithm's actual
   thresholds before blaming the code.

**WORKED EXAMPLE — the modulated sine WAV (2026-07-02, acoustic tone analysis from commit
bae2dcb).** To prove `acoustic_ears.analyze_acoustic` offline, the fixture was a generated
sine-wave WAV with a deliberate silent gap. First attempt: constant-amplitude sine + gap —
analyze reported ZERO pauses. The algorithm was not broken. The pause floor is RELATIVE:
`floor = max(thresh, quiet + 6)` (acoustic_ears.py:95), where `quiet` is the 5th-percentile
voiced RMS (line 57). A constant-amplitude sine has quiet ≈ loud, so quiet + 6 dB sits
above the signal and even true silence never crosses a floor computed from a dynamic range
of zero. The fixture needed amplitude modulation to give the recording a realistic dynamic
range; with modulation, the gap was detected exactly where placed.

**Generalize the subtlety:** fixtures must be realistic in the dimensions the algorithm
measures, not just the dimension you're testing. Sample rate, dynamic range, field
distributions, text length — if the algorithm computes a statistic over dimension D, a
degenerate D in your fixture invalidates the test even when D "isn't what you're testing."

**FAILURE MODE of the method:** A degenerate fixture producing a false negative you then
"fix" in correct code (or a false positive that ships a broken claim). When a fixture test
fails, the first suspect is the fixture; read the algorithm's thresholds and confirm the
fixture actually presents the feature ABOVE threshold before concluding anything.

---

## 5. Deployed-vs-repo differential

**WHEN:** Before ANY logic debugging of device behavior. Stale deploys are the owner's
single costliest failure class: hours have been lost debugging repo code that was not
running. Also whenever a "fixed" bug recurs, or a log line doesn't match repo source.

**RECIPE:** Prove which code runs, by content, not by assumption. Device layout: the git
clone lives at `~/stp-deploy`, the RUNNING copy at `~/telegram-bot/bot.py` (helper scripts
and per-character files deploy manually). Owner-runnable, zero-dollar commands:

```bash
cmp ~/stp-deploy/telegram-companion-bot/bot.py ~/telegram-bot/bot.py
```

Silence = identical; a differ-line = stale deploy, stop and redeploy before debugging.
When `cmp` says identical but you need to know WHICH revision that is, grep for a marker
line unique to the commit you care about:

```bash
grep -c "some literal string your fix added" ~/telegram-bot/bot.py
```

`1` = fix is deployed; `0` = it is not. Pick a marker with no regex metacharacters and no
dollar signs. Remember `cmp` proves file identity, not process identity — a bot restarted
before the copy still runs old code from memory; confirm restart time with the owner.

**WORKED EXAMPLE:** After repeated stale-deploy incidents, `update-all.sh` itself was
hardened to cmp-verify: line 33 runs
`if ! cmp -s "$DEPLOY/telegram-companion-bot/bot.py" "$BOT_SRC/bot.py"; then` after the
copy, so the deploy script now refuses to report success on a mismatched bot.py. That
turned this method's manual check into an automatic gate — but ONLY for bot.py; helper
scripts, character files, and `.env`s still deploy manually and still need the manual
differential.

**FAILURE MODE of the method:** Comparing the wrong pair — repo-vs-clone (`~/stp-deploy`)
when the running copy is `~/telegram-bot/bot.py`, or checking a helper script through the
bot.py-only auto-check. And the restart gap above: file identity ≠ running-process
identity.

---

## 6. Log-absence reasoning

**WHEN:** You need to prove a subsystem did NOT fire — e.g., to exonerate a suspect in a
misfire investigation (see Method 1, Example B). Negative evidence is admissible here
because subsystems print bracketed tags (`[heartbeat]`, `[followup]`, `[garmin]`,
`[memories]`, ...) on every action.

**RECIPE:** An EMPTY grep for the subsystem's tag over the window when the symptom
occurred proves the subsystem didn't fire — IF AND ONLY IF three preconditions hold.
Verify all three before trusting the absence:

1. **Logging was enabled and the process was writing** — confirm by grepping for ANY
   line from the same process in the same window. A silent log proves the log was
   silent, not that the subsystem was.
2. **The window wasn't rotated away** — check the log file's first timestamp predates
   the incident.
3. **The tag string matches the RUNNING version** — tags get reworded across commits;
   grep for the tag in `~/telegram-bot/bot.py` (Method 5) before treating its absence in
   the log as meaningful. Grepping a new tag against logs from old code proves nothing.

Then send the owner the single zero-dollar grep, with the incident timestamp bounds:

```bash
grep "[followup]" ~/nora-bot/bot.log
```

(Owner pastes; you filter by timestamp on your side rather than composing a fragile
time-range command.)

**WORKED EXAMPLE:** The 6a8061f investigation (Method 1, Example B) rested entirely on
this method: empty tag greps at the incident time exonerated the follow-up and heartbeat
subsystems; the event-reminder tag WAS present, convicting it.

**FAILURE MODE of the method:** Trusting absence without the preconditions. Each has
burned someone generally: rotated logs make everything "absent"; a crashed process logs
nothing for any subsystem; a renamed tag makes an active subsystem invisible. An absence
claim without all three preconditions verified is not evidence.

---

## 7. Prompt-assembly audit

**WHEN:** "The character acted weird" — wrong tone, safety refusal, out-of-character
content, mentioning something she shouldn't know. Model behavior can only be explained
from what the model actually saw. Reconstruct it; never speculate from the card alone.

**RECIPE:**

1. Read `assemble_messages` (bot.py:3170,
   `assemble_messages(chat_id, latest_user_content, image_data_url=None, inner_voice=None, query_vec=None, episode_override=_UNSET)`)
   and walk its body top to bottom, listing every block it appends and each block's gate
   condition.
2. For the incident, determine which conditional blocks were ACTIVE: mood label, vibe,
   lorebook triggers, memory/episode recall, inner voice, safety injection. Get gate
   states from logs or diagnostic output (companion-bot-diagnostics has the commands),
   not from guessing defaults.
3. Write out the reconstructed message list in order. Ordering is load-bearing and
   deliberate — the safety injection is appended LAST by design so it wins recency
   against everything above it. If your reconstruction's order differs from the code's,
   your reconstruction is wrong.
4. Locate the weird behavior's cause in a specific block or juxtaposition. If a
   sub-model is involved (safety classifier, appraiser), reconstruct ITS input too —
   sub-models see a different, smaller prompt.

**WORKED EXAMPLE — safety false positive (fixed in 18d4162).** The character abruptly
went safety-mode on an innocuous exchange. Auditing the classifier's input — not the main
prompt — showed the safety classifier received the bare message "All of it." with ZERO
conversation context. Contextless, "All of it." is genuinely ambiguous and the classifier
flagged it. The main model was never the problem; the sub-model's assembled input was.
Fix: include a recent-history snippet in the classifier's input so it judges in context.

**FAILURE MODE of the method:** Auditing the wrong prompt. The main character prompt,
the safety classifier's input, and the appraiser's input are three different assemblies;
diagnosing sub-model behavior from the main prompt (or vice versa) produces confident
nonsense. Second trap: reconstructing from the card + preset "as documented" instead of
from the code path — gated blocks you forgot about (a triggered lorebook entry, an active
vibe) are exactly where weirdness hides.

---

## 8. API-contract verification from a reference implementation

**WHEN:** Integrating a new external API, especially before live credentials exist, or
when docs are thin/wrong. Instead of deriving the contract from documentation, extract it
from code that is KNOWN to work against the real service.

**RECIPE:**

1. Obtain a working reference implementation for the same endpoint (an open-source
   client, a sibling project, vendor sample code that is confirmed-running).
2. Extract VERBATIM: endpoint URL, auth scheme and header format, request payload shape
   (every field name, nesting, and encoding), and response shape (where the actual data
   lives, error envelope). Copy strings; do not paraphrase field names.
3. Adapt to house conventions WITHOUT touching the contract: requests go through
   `_session`, blocking calls are wrapped in `asyncio.to_thread`, failures raise and the
   caller logs/swallows per existing patterns.
4. Validate every pure-function part offline before keys exist: payload construction,
   response parsing, header formatting — via Method 3 with captured or reference-derived
   sample responses as fixtures.
5. First live call is a smoke test with the smallest possible input, run before wiring
   into the bot path.

**WORKED EXAMPLE — the 2026-07-01 Inworld swap (ed15b25, faea119, bae2dcb).** NanoGPT STT
and TTS were replaced with Inworld in one day. References: AI_Ears' `hear_core.py` for the
STT contract, pipecat's `inworld/tts.py` for the TTS contract. Endpoint, `Authorization:
Basic <key>` auth, and payload shapes (`voiceId`, `modelId`,
`audioConfig.audioEncoding: "OGG_OPUS"` — see `_synth_inworld`, bot.py:6899) were lifted
verbatim from the references, then adapted to `_session` + `asyncio.to_thread`. Response
parsing (including `describe_voice_profile` over the STT `voiceProfile` dict) was
validated offline against reference-shaped sample data before live keys were exercised.

**FAILURE MODE of the method:** "Improving" the contract during adaptation — renaming a
field to house style, "simplifying" nesting, swapping the auth scheme for the one you
expected. The reference works BECAUSE of its exact strings; any deviation is an untested
guess. Adapt transport and error-handling conventions; never adapt the wire format.
Second trap: a reference that itself targets a different API version — confirm the
reference actually runs today before extracting from it.

---

## Provenance and maintenance

- Written 2026-07-02 from this repo's real history; every commit hash cited
  (a080f99, 6a8061f, 18d4162, ed15b25, faea119, bae2dcb) verified against `git log`.
- Line references verified same day: `assemble_messages` bot.py:3170, `_FOLLOWUP_RE`
  bot.py:7785 (gate at 7366), `describe_voice_profile` bot.py:6886, pause floor
  acoustic_ears.py:95, deploy cmp update-all.sh:33 — re-grep before trusting; bot.py
  moves.
- The Method 3 skeleton was executed against the live repo on 2026-07-02 and passed;
  if `ast.get_source_segment` or the namespace-exec pattern stops working, fix the
  skeleton here, not just in your scratch file.
- When an investigation teaches a NEW method (not a new instance of these eight), add it
  here with a worked example and its own failure mode; instances of existing methods go
  to companion-bot-failure-archaeology instead.
