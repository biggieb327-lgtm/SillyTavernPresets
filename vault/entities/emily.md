# Emily — character instance

The integration-heavy instance: vision, live traffic, and voice
([raw/2026-07-11-characters.md]).

- Instance: `~/emily-bot/`, card `emily_harper.json`; seed dir `emily/`
  ([raw/2026-07-11-claude-md.md]).
- WSDOT traffic: `/traffic`, `/incidents`, live-location alerts — needs
  `WSDOT_API_KEY` + `TRAFFIC_RADIUS_MILES` + `TRAFFIC_POLL_MINUTES`
  ([raw/2026-07-11-claude-md.md]).
- Inworld voice: TTS voice and model must come from the same engine — an Inworld
  voice ID sent to an OpenAI-style model 400s; `INWORLD_API_KEY` switches engines
  ([raw/2026-07-11-claude-md.md]).
- Vision replies need the multimodal VISION_MODEL; the chat default rejects images
  with 400 ([raw/2026-07-11-bot-py-facts.md]).
- Geographic canon is western Washington (traffic integration implies it); keep
  card/seed geography real, same rule as Priya ([raw/2026-07-11-characters.md] —
  UNCERTAIN: her exact home city isn't stated in the captured notes).
