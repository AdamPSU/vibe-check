# vibe-check

Reclaim ownership of vibe-coded / AI-assisted repos: public GitHub path → visible grounding → short voice Socratic exam → system-layer spider web.

**Status:** minimal frontend scaffold and FastAPI stub.
**Track:** OpenAI Build Week — Education.

## App structure

- `src/frontend/` — Next.js app managed with Bun
- `src/backend/` — small FastAPI stub

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

## Wiki

See [`wiki/`](wiki/) for locked product decisions:

- [Product hub](wiki/vibe-check.md)
- [Core loop](wiki/core-loop.md)
- [Spider axes](wiki/spider-axes.md)
- [v1 scope](wiki/v1-scope.md)
- [Build Week](wiki/build-week.md)
