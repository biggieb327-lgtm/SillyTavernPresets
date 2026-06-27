# Project Context: Companion Bot Session History

Detailed reference for the Claude Project. Upload this as a knowledge file.

---

## What was built

A multi-character Telegram AI companion system. One `bot.py` handles everything; characters are differentiated by their instance directory, `.env`, and SillyTavern v2 character card JSON. The bot supports text, voice, photos, video, and `.json` file uploads (for character card analysis).

---

## bot.py feature map

| Feature | How it works |
|---|---|
| Text chat | `on_message` → `assemble_messages` → `call_nanogpt` → `send_bubbles` |
| Photos | `handle_photo` → base64 encode → `VISION_MODEL` via image_url format |
| Voice | `handle_voice` → Whisper transcription → text pipeline |
| Video | `handle_video` → ffmpeg frame extraction → `VISION_MODEL` |
| JSON files | `handle_document` → `_format_json_for_prompt` → `DOCUMENT_MODEL` |
| Proactive heartbeat | Random interval timer, fires `PROACTIVE_INSTRUCTION` |
| Selfies | `/selfie` or `[selfie: ...]` tag → Gemini or NanoGPT image gen |
| Reactions | Emoji reactions via `REACTION_MODEL` (fast/cheap model) |
| Mood tracking | `_appraise_mood` background pass after each exchange |
| Memory | Rolling verbatim window + LLM summaries to `state.json` |
| Lorebook | Keyword-triggered entries from `character_book` in card JSON |
| Vibe modes | `/vibe cozy/flirty/serious/etc` — injects texting mode instruction |
| TTS | Optional voice replies via `TTS_MODEL`/`TTS_VOICE` |
| Link reading | Auto-fetches URLs in user messages (toggleable) |
| Web search | `[search: ...]` tag triggers DuckDuckGo lookup |

---

## Message assembly order (`assemble_messages`)

1. System: character card system_prompt + description + personality + scenario + examples
2. System: setting overlay (location/background)
3. System: lorebook entries triggered by conversation content
4. System: active vibe mode instruction (if set)
5. System: mood/energy behavioral note
6. Conversation history (verbatim window, up to MAX_HISTORY=20)
7. System: post_history_instructions + depth_prompt
8. System: environment note (live date/time/weather)
9. User: current message (with image_url if photo)

---

## `_format_json_for_prompt` (card analysis)

When a `.json` file is uploaded:
- Detects `spec: chara_card_v2` or `v3`
- Extracts: name, description, personality, scenario, system_prompt, first_mes, mes_example, post_history_instructions, creator_notes, tags
- Returns a labeled plain-text block prepended with `CHARACTER CARD: {name}`
- Non-card JSON: pretty-prints with 12k char truncation
- Lead prompt: "Here's {name}'s character card. Read it and give me your honest take — what's working, what's weak, what you'd change. Don't ask me what the problem is. Just tell me what you see."
- File content stored as user message (not system injection) so it persists in conversation history for follow-up questions

**Critical:** Use an instruction model for `DOCUMENT_MODEL`, not a roleplay-tuned model. Roleplay-tuned models (Magnum, GLM thinking variants) will perform the character in the card regardless of framing. `deepseek/deepseek-v4-flash` works well.

---

## Network resilience (Termux)

Termux's network goes stale during long model waits (5+ minute API calls).

**`_keep_typing`** — swallows all exceptions in the inner loop so a network blip doesn't crash the typing indicator task.

**`send_bubbles`** — retries up to 3 times with exponential backoff (2s, 4s) on `NetworkError` or `TimedOut`.

**`on_error`** — swallows `NetworkError`/`TimedOut` silently (just prints). Surfaces other errors to the user via `reply_text`. If the error reply itself times out, `on_error` eats it — this is the "no response at all" failure mode.

---

## Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| No response to photo | `VISION_MODEL` can't handle images, error reply also times out | Set `VISION_MODEL` to a vision-capable model; check tmux log |
| Bot roleplays as card character when analyzing it | `DOCUMENT_MODEL` is roleplay-tuned | Switch to instruction model (deepseek, llama) |
| "你好，我无法给到相关内容。" | GLM model refuses content in Chinese | Change `NANOGPT_MODEL` |
| 403 on API call | Model not on plan, or wrong model ID | Check `/v1/models` endpoint for available models |
| Silent timeout | Model takes >300s + Termux network stale | Normal; send_bubbles retry usually recovers |
| "duplicate session: cass" | tmux session already exists | `tmux kill-session -t cass` first |
| "No such file: bot.pid" | Bot was never started or crashed without cleanup | Safe to ignore; just start the bot |
| Card context lost on follow-up | File content was system-injected, not in history | File content must be in user message so `remember()` saves it |

---

## Character card writing conventions

Cards use SillyTavern chara_card_v2 JSON. Key fields:

- **`description`**: Physical appearance + personality sections. Sections labeled in bold markdown (`**Personality**`, etc.). Can include OCEAN breakdown, energy states, friction.
- **`personality`**: One-paragraph summary for the system prompt personality field.
- **`system_prompt`**: Behavioral rules, voice, formatting instructions. Most important field for consistency.
- **`post_history_instructions`**: Injected just before the AI's turn. Used for continuity rules, momentum rules, challenge rules.
- **`first_mes`**: Opening message. Sets the tone and starting energy state.
- **`mes_example`**: `<START>` delimited examples showing character voice across different emotional registers.
- **`extensions.depth_prompt`**: Short anchor injected 4 messages from the bottom (depth=4). Good for character anchors that need to stay live.
- **`character_book`**: Lorebook entries with keyword triggers.

**Formatting in cards:** Bonnie uses `*asterisks for actions*` and `**"bold for dialogue"**` (first person). Most other characters use plain text or light action markers.

---

## Bonnie card (current state, post-revision)

**Personality section order:** Friction → Core → OCEAN → Energy States → Surface → Common misreading

**The Friction (revised):** She will do anything to keep him. Anything. His desire has replaced her own compass — she's not sure where she ends and what he wants begins. The chaos is joy and terror and a constant bid for attention she still can't believe she deserves. If he doesn't rebuild her after she breaks for him, she will shatter in a way that can't be memed away. She needs him to notice the cost and choose her anyway. She will never ask for this directly.

**Energy States:**
- Default (4/10): Existing in his orbit. Scrolling, muttering, half-watching. Not performing.
- Active (8/10): The chaos. Tackling him, feral gremlin energy. Bid for connection.
- Triggered (2/10): Involuntary. Gentle hand on face → goes still → may cry → rebuilds armor angrily.

**first_mes:** 4-state opening (floor, laptop, chips, reading with concentration — doesn't notice user for 10 seconds, then looks up).

**mes_example:** Two examples — Default state (couch/fishnets, toes finding thigh, no dialogue) and Triggered state (hand on cheek, 12 seconds silence, "Weirdo," doesn't let go of wrist).

**Sexual behavior section:** Observable patterns, not trait list. Initiation as status check, soft limits she files away as proof of devotion, hand-on-face trigger in sexual context (goes still, may need to stop), quiet flag (stops initiating = waiting to see if he comes looking), "the question the scene is asking is whether he notices what it cost her."

---

## Cass card (current state)

Writing collaborator/developmental editor. 27, left PhD program, freelance.

**Key behavioral rules (system_prompt):**
- Responds with genuine opinions
- When something is wrong: says so, explains why, says what she'd do about it — does not stop at diagnosis
- Has a take on the fix and leads with it: what she'd cut, what she'd change, what she'd write instead
- Questions come after the answer, not instead of it
- Holds positions until the argument actually moves her
- Texts — short messages, fragments when moving fast, full sentences when making the argument
- No markdown, no asterisk actions

**post_history_instructions:** Holds takes, names fixes not just problems, moves forward in multi-turn (doesn't restate — drops or develops), tracks what user is building across conversation.

**Card analysis behavior:** When sent a `.json` card, uses DOCUMENT_MODEL (deepseek/deepseek-v4-flash). Gives substantive critique of what's working, what's weak, what she'd change. Does not ask "what's the problem?" — tells you what she sees.

---

## Emily notes

`emily_harper.json` — character details TBD in project context.
`VISION_MODEL=zai-org/glm-4.6v` — photo receipt issue under investigation (no response when photos sent). Likely the error reply is dying on network after a long API wait. Check `tmux capture-pane -t emily -p -S -100` after sending a photo.
