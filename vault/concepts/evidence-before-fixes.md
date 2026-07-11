# Evidence before fixes

**Idea:** collect the cheapest discriminating observation before proposing any fix;
if the error is opaque, make the failure self-describing first (instrument, deploy,
reproduce), then fix.

- Origin: three rounds of speculative fixes once lost to a single pasted log line
  ([raw/2026-07-11-claude-md.md]).
- Realized as the debugging protocol: exact error text first; differential
  diagnosis across the six bots (the broken one's delta is usually the answer);
  a bot that can't answer `/errors` is a startup crash — go to bot.log
  ([raw/2026-07-11-claude-md.md]).
- Canonical example: any restart storm — read `watchdog.log`'s stated reason
  before any other theory; the watchdog once masqueraded as a platform bug for a
  full session ([raw/2026-07-11-operational-log.md]).
