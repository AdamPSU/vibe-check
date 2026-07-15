---
title: V1 Scope
description: What ships in the Build Week v1 core vs what is explicitly stretch.
date: 2026-07-14
tags: [vibe-check, scope, mvp, stretch]
---

What ships in the Build Week v1 core vs what is explicitly stretch.

## v1 core (in)

| Item | Decision |
|---|---|
| Name | vibe-check |
| Track | Education |
| Repo access | Public GitHub only |
| URL shape | `/{owner}/{repo}` (host TLD TBD) |
| Grounding | Codex SDK + Exa + GPT-5.6; live tool calls on loading UI |
| Interview | Voice-only Realtime; agent opens; Socratic; dynamic questions |
| Duration | ~1 minute soft timer (demo); finish current question |
| Output | System-layer spider; unprobed = not assessed |
| Scoring | End-only model judgment |
| Stuck handling | One scaffold then move on |
| Persistence | localStorage |
| Failures | Retry 1–2× then hard fail |

## Stretch (not v1 core)

These may be desirable later; they are **not** required for the first ship:

- Peer comparison / leaderboard
- Accounts / cross-device history
- Private repos / OAuth
- Text interview mode
- Multi-repo portfolio
- Long courses / multi-week curricula
- (Related social ideas such as dense peer graphs)

## Explicitly deferred (unknown)

Do not invent product requirements for:

- Exact adaptive vs fixed question policy beyond “dynamic Socratic”
- Full ingest file heuristics
- Interview screen chrome layout
- Post-spider drill / study-plan product
- Debrief tone details
- Separate precision meter UI
- Final production domain TLD
