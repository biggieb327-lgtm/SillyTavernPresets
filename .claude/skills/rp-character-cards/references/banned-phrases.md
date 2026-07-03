# Banned Phrase List

Mandatory scan on every build before delivery. These phrases are banned in all card text fields (description, personality, scenario, mes_example, first_mes, alternate greetings, post_history_instructions, lorebook content). The validation script checks them mechanically; this file exists for the judgment call on near-misses and for writing substitutions.

## Spatial-charisma metaphors

Banned: "takes up space," "fills the room," "fills every room," "commands the room," "owns the room," "dominates the space," and any spatial metaphor standing in for charisma or presence.

Substitution rule: describe what specifically happens. Who stops talking, who moves their chair, what the character does with their hands, who they look at first. Presence is rendered through other people's concrete reactions, not through room-physics.

## LLM-slop lexicon

Banned outright: "fresh meat," "breath hitching," "breath catching," "breath hitches," "husky," "ozone," "asset," "shivers down spine," "pupils blown wide," "pupils dilated," "nails biting," "vise," "vice" (grip sense), "structural integrity," "deep curve," "furnace," "throaty," "calloused," "guttural," "slick," "unadulterated," "jaw clenched," "barely above a whisper," "musk," "predatory," "velvet," "electric," "visceral," "something shifted," "luminous," "the weight of," "architecture" (as psychological metaphor).

## Abstract-glaze constructions

Banned as a pattern: constructions that gesture at significance without rendering anything ("something in the air changed," "an unspoken understanding," "a tension neither could name"). Replace with a concrete observable: an action, a line of dialogue, a specific sensory detail.

## Substitution method

Don't delete-and-leave-a-hole. Each banned phrase was doing a job; identify the job and do it with specifics:

- "predatory smile" → describe the specific mouth/eye behavior and what it makes the observer do
- "voice barely above a whisper" → give the actual volume behavior and why ("dropped her voice so he had to lean in")
- "the weight of his stare" → what the stared-at character does in response

## DS4-mode additions (only when `--ds4` applies)

- Em-dashes in narration (allowed inside dialogue quotes)
- Ellipses anywhere
- Similes/metaphors/comparisons in narration (Camera Lens Rule)
- Female voice descriptors: "low," "deep," "husky," "throaty," "gravelly" → use soft, warm, quiet, clear, bright, airy, gentle
