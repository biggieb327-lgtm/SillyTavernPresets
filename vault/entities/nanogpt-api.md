# NanoGPT API — the LLM provider

OpenAI-compatible API at `https://nano-gpt.com/api/v1`; every character reply,
summary, and analysis call goes through it ([raw/2026-07-11-claude-md.md]).

- Model slots with hard constraints: chat `zai-org/glm-5:thinking`; fallback must
  be roleplay-capable; DOCUMENT_MODEL must be an instruction model (a roleplay
  model performs the card it's analyzing); VISION_MODEL must be multimodal
  ([raw/2026-07-11-bot-py-facts.md]).
- Retry ladder: 2 attempts/model, 2s/4s backoff, 150s primary budget, then
  fallback model ([raw/2026-07-11-claude-md.md]).
- Streaming quirks paid for in incidents: error bodies must be force-read before
  raise_for_status; SSE mojibake needed manual UTF-8 decoding; models rejecting
  streams are cached in `_no_stream_models`
  ([raw/2026-07-11-operational-log.md], [raw/2026-07-11-bot-py-facts.md]).
- UNCERTAIN: pricing/quota behavior is not documented in the repo; degradation
  alerts (fallback rate + monthly spend) exist per ROADMAP 1.4 but thresholds are
  configured on-device ([raw/2026-07-11-roadmap-audit.md]).
