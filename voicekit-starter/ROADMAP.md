# VoiceKit Starter — Roadmap

> **Last updated:** 2026-09-08
> **Current version:** 0.2.1
> **Status:** Functional core, no tests, no CI

---

## Vision

Become the **go-to open-source tool for author voice profiling** — more rigorous than prompt-wrapper alternatives, more accessible than academic stylometry, and the foundation for a broader "voice-native" writing toolchain.

---

## Phase 1: Foundation (Weeks 1-2)

**Goal:** Make the project trustworthy and contributor-friendly.

### 1.1 Testing
- [ ] Unit tests for `schemas.py` (schema validation, repair logic)
- [ ] Unit tests for `core.py` (profile building, generation, judging)
- [ ] CLI integration tests (end-to-end with mocked LLM)
- [ ] Test fixtures: sample corpora (short, medium, edge cases)
- [ ] Target: 80%+ coverage on core logic

### 1.2 CI/CD
- [ ] GitHub Actions: test matrix (Python 3.10, 3.11, 3.12)
- [ ] GitHub Actions: lint (ruff, mypy)
- [ ] GitHub Actions: publish to PyPI on tag
- [ ] Pre-commit hooks for local dev

### 1.3 Documentation
- [ ] Expand README with troubleshooting section
- [ ] Add `CONTRIBUTING.md` with dev setup
- [ ] Add `CHANGELOG.md`
- [ ] API reference (auto-generated from docstrings)
- [ ] Example gallery: 3-5 real-world use cases

### 1.4 Bug Fixes & Polish
- [ ] Add progress indicators for long-running extractions
- [ ] Better error messages for common failures (rate limits, context length)
- [ ] Validate input file types before processing
- [ ] Add `--verbose` flag for debugging

---

## Phase 2: Core Features (Weeks 3-6)

**Goal:** Close the gap with commercial alternatives (Sembra, Noren, Jasper).

### 2.1 Batch Processing
- [ ] `batch-build` command: process multiple authors in one run
- [ ] Parallel processing with configurable concurrency
- [ ] Progress bar + ETA
- [ ] Resume interrupted batches

### 2.2 Profile Comparison
- [ ] `compare-profiles` command: diff two profiles
- [ ] Visual output (side-by-side tables)
- [ ] Similarity scoring (0-100)
- [ ] Export comparison as markdown

### 2.3 Voice Evolution Tracking
- [ ] `track-evolution` command: analyze how voice changes over time
- [ ] Time-series analysis (if corpus has dates)
- [ ] Drift detection (alert when voice shifts significantly)
- [ ] Visualization (ASCII charts or HTML export)

### 2.4 Enhanced Generation
- [ ] Multi-register generation in one command
- [ ] Batch generation from a CSV/JSON brief
- [ ] Template system for common document types
- [ ] Interactive mode (chat-like refinement)

### 2.5 Profile Management
- [ ] `list-profiles` command: show all profiles in a directory
- [ ] `merge-profiles` command: combine multiple corpora for same author
- [ ] `validate-profile` command: check profile completeness
- [ ] Profile versioning (track changes to a profile over time)

---

## Phase 3: Advanced Features (Weeks 7-12)

** Goal:** Differentiate from competitors and enable new use cases.

### 3.1 Multi-Author Support
- [ ] Detect multiple authors in a single corpus
- [ ] Separate profiles per author
- [ ] Author attribution for anonymous text
- [ ] Collaborative voice (blend multiple authors)

### 3.2 Semantic Analysis (Propose-Prove Pattern)
- [ ] Implement the "Propose-Prove" pattern from Sembra research
- [ ] LLM proposes candidate markers → verify against actual text
- [ ] Reduce hallucinated voice traits
- [ ] Confidence scores per field

### 3.3 API Server
- [ ] REST API wrapper around core functions
- [ ] FastAPI-based
- [ ] OpenAPI docs
- [ ] Rate limiting + API key auth
- [ ] Docker image for easy deployment

### 3.4 Web UI
- [ ] Simple React/Vue frontend
- [ ] Upload writing samples → view profile
- [ ] Profile visualization (radar chart of voice dimensions)
- [ ] Draft generator with live preview
- [ ] Judge with side-by-side comparison

### 3.5 Integrations
- [ ] Obsidian plugin (read/write profiles from vault)
- [ ] Notion integration (store profiles in databases)
- [ ] VS Code extension (generate in editor)
- [ ] CLI alias for common shells

---

## Phase 4: Ecosystem (Weeks 13+)

**Goal:** Build a platform, not just a tool.

### 4.1 Plugin System
- [ ] Custom profile dimensions (plugins can add fields)
- [ ] Custom generators (plugins can add output formats)
- [ ] Custom judges (plugins can add evaluation criteria)
- [ ] Plugin registry/marketplace

### 4.2 Community
- [ ] Discord server for users
- [ ] Profile sharing (opt-in, anonymized)
- [ ] Benchmark dataset (public domain corpora)
- [ ] Annual "voice profiling" challenge

### 4.3 Research
- [ ] Publish methodology paper
- [ ] Compare against academic stylometry tools
- [ ] Contribute to open-source NLP projects
- [ ] Partner with writing communities

---

## Competitive Landscape

| Tool | Strengths | Weaknesses | Our Advantage |
|---|---|---|---|
| **Sembra** | Propose-Prove pattern, brand focus | Closed source, expensive | Open source, author-focused |
| **Noren** | Easy setup, good UI | Limited customization | Full control, local processing |
| **Jasper** | Marketing integration | Generic, expensive | Specialized, privacy-focused |
| **Custom prompts** | Free, flexible | No validation, unreliable | Schema validation, repair retries |

---

## Success Metrics

- **Phase 1:** 100+ stars, 10+ contributors, CI green
- **Phase 2:** 500+ stars, 50+ PRs merged, PyPI downloads 1k+/month
- **Phase 3:** 2000+ stars, API in production, web UI live
- **Phase 4:** 5000+ stars, active community, research citations

---

## Immediate Next Steps

1. **Create GitHub Issues** for Phase 1 items
2. **Set up project board** with this roadmap
3. **Write first test** (schema validation)
4. **Add CI workflow** (GitHub Actions)
5. **Expand README** with troubleshooting

---

*This roadmap is a living document. Update it as the project evolves.*
