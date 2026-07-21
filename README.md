# vibe-check

Reclaim ownership of vibe-coded / AI-assisted repos: public GitHub path → visible grounding → short voice Socratic exam → system-layer spider web.

**Status:** local one-session daily-game pipeline and scheduler implemented and tested; hosted worker deployment and provider wiring remain.
**Track:** OpenAI Build Week — Education.

## App structure

- `src/frontend/` — Next.js app managed with Bun
- `src/backend/` — small FastAPI stub
- `src/backend/prompts/` — canonical Codex maker and adversarial-tester system prompts

## Run locally

Frontend:

```bash
cd src/frontend
bun install
bun dev
```

Backend:

```bash
uv sync --project src/backend
uv run --project src/backend uvicorn src.backend.main:app --reload
```

The backend exposes `GET /health`.

For the continuous local scheduler, which promotes the current release and
pre-generates the next date in America/New_York:

```bash
PYTHONPATH=. uv run --project src/backend python -m src.backend.generator \
  --loop --mode demo --data-dir var/daily-games
```

Run one complete local generation session, including real headless Chrome
validation, artifact retention, and catalog publication:

```bash
PYTHONPATH=. uv run --project src/backend python -m src.backend.generator \
  --date 2026-07-21 \
  --mode demo \
  --data-dir var/daily-games
```

Use `--mode codex` to invoke the installed Codex CLI with the configured maker
and tester models. The demo mode is deterministic and requires no provider
credentials; it is the end-to-end test fixture, not a fallback game.

Run the backend tests with:

```bash
PYTHONPATH=. uv run --project src/backend python -m unittest discover -s src/backend/tests -v
```

## Wiki

See [`wiki/`](wiki/) for locked product decisions:

- [Product hub](wiki/vibe-check.md)
- [Core loop](wiki/core-loop.md)
- [Spider axes](wiki/spider-axes.md)
- [v1 scope](wiki/v1-scope.md)
- [Build Week](wiki/build-week.md)

The current daily-game-generator design is documented in
[`docs/daily-game-generator.md`](docs/daily-game-generator.md).
