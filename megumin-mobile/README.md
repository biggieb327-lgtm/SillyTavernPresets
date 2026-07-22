# Megumin Suite — Anti-Positivity-Bias, Mobile Edition (Tavo)

A stripped-down, extension-free port of the anti-positivity / anti-slop rules from
[Arif-salah/Megumin-Suite](https://github.com/Arif-salah/Megumin-Suite) V9 so they work on
mobile clients like **Tavo** (and any client that only gives you a system-prompt / jailbreak
text box).

## Why the original is "desktop only"

The full Megumin Suite is a SillyTavern **extension**, not just a preset. Its preset prompts are
full of `[[macro]]` placeholders (`[[banlist]]`, `[[Direct]]`, `[[DN]]`, `[[storytracker]]`,
`[[cyoa]]`, `[[npc_dossier]]`, …) plus regex scripts and an image pipeline. Those macros are
resolved and the regex post-processing is applied **by the extension at runtime**. On a mobile
client with no extension, the macros are never filled in — they'd render as literal `[[...]]`
junk in the prompt and do nothing.

## What this port keeps (the part you asked for)

Everything here is the **self-contained** text from V9 that needs no extension — which happens
to be exactly the anti-positivity-bias core:

- **No positivity bias** — the world says no when it should; no rewarding {{user}} for
  confidence alone; kill the "says something bold → everyone respects him" pivot; no softening
  outcomes; no auto-impressive dialogue; NPCs can dislike/betray/beat {{user}} without the story
  punishing them.
- **Character agency** — characters have their own goals and only know what they witnessed;
  never write for {{user}}.
- **Prose variety (anti-slop)** — rotate the entry point instead of narrating first every turn;
  no repeating beats from the last two turns.
- **The hard banlist** — the verbatim list of banned AI-slop phrases/patterns.

## What was dropped (extension-only, not "anti positivity")

`[[macro]]` toggles, the Dynamic Ban List (needs the extension to scan chat), regex scripts,
CYOA / story-tracker / info-block / NPC-dossier / inner-chatter blocks, the image-gen pipeline,
memory management, and the forced `<think>` reasoning wrapper (dropped to keep this port
self-contained). Note: Tavo *does* have a regex feature (Settings → Regex → Edit regex, with
Find/Replace, Placement, Timing, etc.), so if a model still leaks raw `<think>` or `[OOC:]`
blocks you can strip them there rather than rely on the prompt alone — see
`../StripOOCPreamble.json` in the repo root for a ready-made strip pattern and its field values.

## How to use in Tavo

**Recommended — paste the system prompt:**
1. Open `Megumin-AntiPositivity-Mobile.systemprompt.txt`.
2. Copy the whole thing.
3. In Tavo, create a new preset / system prompt (Settings → Presets, or the jailbreak/system-prompt
   field) and paste it in.
4. `{{char}}` / `{{user}}` are standard placeholders Tavo fills in automatically.

**Alternative — import the JSON:** if your client can import a SillyTavern chat-completion preset,
use `Megumin-AntiPositivity-Mobile.json`. It's a clean, valid preset with the same rules split
across the main system prompt and the post-history slot (no macros, no regex, no extension deps).

## Tuning

- If replies feel too harsh or the model refuses too much, loosen the CORE section wording.
- The banlist is aggressive; delete any line whose phrasing you actually want to keep.
- Temperature in the JSON is set to a neutral `0.9` — adjust to taste.

_Credit: rules distilled from Megumin Suite V9 by Arif-salah. This is an unofficial mobile port._
