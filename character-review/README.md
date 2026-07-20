# character-review/ — card review inbox

Drop SillyTavern character cards (`chara_card_v2` JSON) in this folder to queue
them for the monthly character content pass (`character-pass-monthly` Routine,
14:00 UTC on the 15th — schedule and verbatim prompt in
`.claude/operating/routines.md`).

The pass reviews inbox cards and the live fleet cards/seeds against the
`edit-cards-and-presets` rules, gleans card-writing ideas from Reddit (every
external idea cited with its thread URL), and writes its suggestions to
`PROPOSALS-<YYYY-MM>.md` on the `claude/character-review` branch — never to
`main`, and never as direct edits to any card.

**Nothing is applied without owner approval.** To accept a proposal, apply it in
an interactive session under the `edit-cards-and-presets` skill, then delete the
processed card from this folder.
