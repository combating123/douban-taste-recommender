# CineScope AI Observatory Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement these plans in order. Each child plan uses checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current monolithic dashboard with the approved CineScope AI observatory while preserving existing crawler and recommendation behavior throughout migration.

**Architecture:** Four independently testable plans are executed in sequence. The first establishes SQLite and local trusted media delivery, the second adds recommendation sessions and the Command Lens domain model, the third builds the modular five-space UI, and the fourth performs live browser acceptance and switches the new experience to the default.

**Tech Stack:** Python 3.10+, standard-library HTTP server, SQLite, Pillow, native HTML/CSS/ES Modules, `unittest`, Codex browser/computer-use acceptance.

## Global Constraints

- Do not overwrite or discard pre-existing uncommitted modifications.
- Douban Cookie remains in browser `sessionStorage` and request memory only; never persist or echo it.
- Do not read browser profiles or browser Cookie databases.
- Do not accept or persist proxy subscription URLs; only local HTTP proxy endpoints are allowed.
- Anime means animated series; animated films must not enter that channel.
- Series recommendations downrank costume drama unless the current request explicitly opts in.
- A wrong external image is worse than a designed fallback.
- The browser must never expose a broken image state.
- Keep a one-command local runtime with no Node runtime dependency.
- Use TDD, run focused tests before full suites, and commit each independently reviewable task.

## Execution Order

1. [`2026-07-10-cinescope-foundation-media.md`](2026-07-10-cinescope-foundation-media.md)
2. [`2026-07-10-cinescope-recommendation-intelligence.md`](2026-07-10-cinescope-recommendation-intelligence.md)
3. [`2026-07-10-cinescope-experience-ui.md`](2026-07-10-cinescope-experience-ui.md)
4. [`2026-07-10-cinescope-verification-rollout.md`](2026-07-10-cinescope-verification-rollout.md)

Each plan must leave the application runnable and the full pre-existing test suite green before the next plan starts.
