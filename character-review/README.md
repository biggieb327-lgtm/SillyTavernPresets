# character-review/ — card review inbox

**Inbox cards now live on Google Drive** (folder "Character Cards", ID
`1mG4SO8dcGhT4JNRFrRGzKn5KpX8KwC0x`, inside Claude Code / Bot Fleet). Drop
SillyTavern character cards (`chara_card_v2` or `chara_card_v3` JSON) there to
queue them for the monthly character content pass (`character-pass-monthly`
Routine, 14:00 UTC on the 15th — schedule and verbatim prompt in
`.claude/operating/routines.md`).

This git directory still holds `PROPOSALS-<YYYY-MM>.md` output files from each
pass, but inbox cards are no longer read from here.

The pass reviews inbox cards (from Drive), the live fleet cards/seeds, and
presets — the latest root SillyTavern presets (`TheAtelier_2.0.json`,
`UnifiedWritersRoom_V32.json`) plus `telegram-companion-bot/preset.txt`, the
fleet-wide texting voiceprint — all against the `edit-cards-and-presets` rules.
It gleans card-writing ideas from Reddit (every external idea cited with its
thread URL) and writes its suggestions to `PROPOSALS-<YYYY-MM>.md` on the
`claude/character-review` branch — never to `main`, and never as a direct edit
to any card or preset. `preset.txt` proposals carry a before/after quote and a
fleet-wide-blast-radius note.

**Nothing is applied without owner approval.** To accept a proposal, apply it in
an interactive session under the `edit-cards-and-presets` skill, then delete the
processed card from the Drive folder.
