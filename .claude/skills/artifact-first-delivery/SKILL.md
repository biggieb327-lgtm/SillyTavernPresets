---
name: artifact-first-delivery
description: Deliver work as durable artifacts (files, commits, runnable scripts), never as chat-only output. Use whenever producing a deliverable of any kind.
---

The deliverable is the file, not the message about the file.

1. Every deliverable lands somewhere durable: a committed file, a script, an eval, a changelog entry. If the session ended right now, the work must still exist.
2. Chat output is a pointer: what was produced, where it lives (`path:line`), and the evidence it works. Never paste a wall of content into chat that should be a file.
3. Anything meant to be true tomorrow goes in a file that's read tomorrow — CLAUDE.md, an agent contract, a hook, an eval. A promise made only in conversation does not exist. The test: **which file enforces this tomorrow?**
4. In this repo, work isn't delivered until pushed — deploys pull from `main` via raw GitHub URLs, and the session container is ephemeral.
