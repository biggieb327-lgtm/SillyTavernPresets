# character-review/ — card review inbox

Drop SillyTavern character cards (`chara_card_v2` JSON) in this folder to queue
them for the character content pass.

**The `character-pass-monthly` Routine that used to run this pass is retired here
(2026-08-22)** — the scheduled work moved to ChatGPT, so nothing picks the inbox up on a
schedule any more. Ask for a pass when you want one; the `character-reviewer` agent holds
the same contract the Routine acted under. Its old schedule and verbatim prompt are kept
in `.claude/operating/routines.md` (historical).

The pass reviews inbox cards, the live fleet cards/seeds, and presets — the
latest root SillyTavern presets (`TheAtelier_2.0.json`, `UnifiedWritersRoom_V32.json`)
plus `telegram-companion-bot/preset.txt`, the fleet-wide texting voiceprint — all
against the `edit-cards-and-presets` rules. It gleans card-writing ideas from
Reddit (every external idea cited with its thread URL) and writes its suggestions
to `PROPOSALS-<YYYY-MM>.md` on the `claude/character-review` branch — never to
`main`, and never as a direct edit to any card or preset. `preset.txt` proposals
carry a before/after quote and a fleet-wide-blast-radius note.

**Nothing is applied without owner approval.** To accept a proposal, apply it in
an interactive session under the `edit-cards-and-presets` skill, then delete the
processed card from this folder.
