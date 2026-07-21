# Daily game generator

## Product

`vibe-check` produces one shared browser game for each calendar day in `America/New_York`. A game should be understandable immediately, finish in roughly 30–120 seconds, and support unlimited replay. The same published game is served to every player.

The existing frontend remains the product shell. Its landing page can show the current game and the historical catalog, but screenshot generation and screenshot cards are deferred. Generated games run only after a player opens one; the catalog does not execute every game.

There are no player accounts, scores, streaks, completion records, local history, concept-deduplication rules, human approval, fallback games, or automatic generation retries.

## Current architecture

The generation worker and FastAPI service are separate Python entrypoints. FastAPI only serves catalog data and stored artifacts. It does not hold a generation request open.

```text
Daily scheduler
    |
    v
Python GenerationOrchestrator
    |
    +-- durable release-date claim
    +-- isolated workspace
    +-- one CodexSdkMaker thread
    |       |
    |       +-- game implementation and local build
    |       +-- Exa research
    |       +-- built-in image generation
    |       +-- Lyria music generation
    |       +-- headless Chrome testing
    |       +-- one read-only adversarial tester subagent
    |       +-- repair and delivery-validator MCP
    |
    +-- read dist/metadata.json
    +-- copy source workspace and dist/ build
    +-- save game/session metadata
    +-- publish when the release date is due
```

The backend stays intentionally shallow:

```text
src/backend/
  main.py                 FastAPI routes
  cli.py                  worker and one-shot entrypoint
  generation/             Codex session, pipeline, and scheduler
  data/                   catalog and object-storage adapters
  delivery/               delivery contract and validator MCP
  prompts/                durable maker and tester instructions
  tests/                  boundary-focused tests
```

The top-level modules compose the packages; they do not contain another service
layer or generic repository/adapter hierarchy.

The harness deliberately has a weak host and a strong maker. Python owns lifecycle and persistence. Codex owns the difficult semantic questions: whether the game is understandable, enjoyable, finishable, replayable, and production-ready.

### Why the Codex SDK

The worker uses `openai-codex` directly instead of spawning `codex exec`. The SDK starts the bundled Codex runtime, reuses the user's saved Codex subscription authentication, creates a thread, streams notifications, and closes the runtime cleanly.

The outer OpenAI Agents SDK is not used. That pattern is useful when a separate API-backed coordinator owns a larger multi-agent graph, but this application needs one Codex coding session with one native Codex subagent. Adding an API coordinator would create another model/authentication layer without improving this flow. LangGraph and Deep Agents are likewise unnecessary because Python is not implementing an agent loop or graph.

The configured targets are:

```text
maker:  gpt-5.6-luna / xhigh / workspace-write
tester: gpt-5.6-sol  / xhigh / read-only
```

The maker runs with deny-all interactive approvals. MCP tools that must run autonomously are configured with approved tool policies. An unavailable model or tool fails the session; there is no silent substitution.

## Responsibility boundaries

### Python host

Python owns:

- Release dates, internal IDs, and one durable claim per date.
- Session status and failure recording.
- Workspace creation and retention.
- Starting exactly one SDK thread and recording its event stream.
- Reading delivered catalog metadata.
- Copying source and build trees to storage.
- Marking games ready or published.
- Serving catalog records and object files through FastAPI.

Python does not:

- Select or judge a game concept.
- Run a deterministic finish or replay playthrough.
- Capture catalog screenshots.
- Reject frameworks, dependencies, or implementation languages.
- Inspect browser behavior or runtime network requests.
- Parse delivery information from Codex's final prose.
- Call the delivery validator after Codex finishes.
- Retry a failed release or publish a fallback.

The host still rejects unsafe local object keys and symlinked trees. Those are storage-boundary protections, not game-quality tests.

### Maker

The maker owns the complete creative and engineering loop:

1. Consider multiple appropriately scoped ideas and select one.
2. Choose any useful implementation stack.
3. Build a playable game and package its runtime files.
4. Use Exa and generated assets when helpful.
5. Generate a Lyria music loop and add local/procedural effects as appropriate.
6. Play and diagnose the game in headless desktop Chrome.
7. Spawn `adversarial_tester` exactly once after a playable build exists.
8. Save and evaluate the tester's report.
9. Repair and retest the game.
10. Call `validate_delivery` until it reports `valid: true`.

The maker may install dependencies inside its isolated workspace. It cannot publish, select release IDs, or write the product database.

### Adversarial tester

The native Codex subagent is independently configured in each workspace. It receives `gpt-5.6-sol`, `xhigh`, and a read-only sandbox. It can use Exa, Chrome, and source inspection, but cannot edit the game, install fixes, generate assets, publish, or spawn another agent.

It tests the game as a black box first, then reads code to diagnose observed behavior. It returns one evidence-based report to the maker. The main maker decides how to act on that report while remaining responsible for the final game.

## Delivery contract

Every maker workspace receives a root `AGENTS.md` before the SDK session starts. This durable instruction survives a long session and context compaction better than relying only on the initial prompt.

The publishable package is:

```text
dist/
  index.html       required browser entrypoint
  metadata.json    required catalog metadata
  game/            optional code, styles, WASM, or data
  assets/          optional images, fonts, and visual resources
  audio/           optional music and sound effects
```

Only `index.html` and `metadata.json` must physically exist. The three directories are optional namespaces because object stores do not preserve meaningful empty directories. No other top-level `dist/` entries are allowed. Arbitrary nested files are allowed within the namespaces.

`metadata.json` contains:

```json
{
  "title": "A nonempty game title",
  "description": "A nonempty catalog description"
}
```

Additional fields are allowed but ignored. Dates, IDs, storage keys, expected duration, finish descriptions, screenshots, versions, and publication state belong to the host and are intentionally absent.

Codex's final assistant message is an audit summary only. It is saved as `maker-final-response.txt`, but publication metadata comes exclusively from `dist/metadata.json`.

### Delivery validator MCP

Each workspace also receives a project-scoped MCP registration for a local `delivery-validator` stdio server. It exposes one read-only, idempotent tool:

```text
validate_delivery() -> {
  valid: boolean,
  errors: string[],
  checked: string[]
}
```

The tool accepts no path. Its process working directory is bound to the current workspace, preventing the model from asking it to validate an unrelated directory. It checks:

- `dist/` exists.
- `dist/index.html` and `dist/metadata.json` are files.
- Metadata is valid JSON with nonempty string `title` and `description` fields.
- Optional namespaces are directories when present.
- No unexpected top-level entry exists.

The MCP server is required to initialize, and `AGENTS.md` requires the maker to call it and repair all reported errors before ending. The Python orchestrator deliberately does not call the validator or inspect the event stream to enforce that call. Missing or unreadable files can still fail naturally when Python consumes metadata or copies the tree, but this is not a duplicated host validation pass.

## Session lifecycle and failures

There is one autonomous session per release date:

1. The scheduler promotes games whose date has arrived.
2. It checks today and tomorrow for missing releases.
3. The catalog atomically claims a generation session for the release date.
4. The orchestrator creates a unique workspace.
5. The SDK maker runs one ephemeral thread and one turn.
6. SDK notifications are appended to `codex-events.jsonl` as they arrive.
7. On success, the host reads metadata, stores the workspace and build, and records the game as ready or published.
8. On failure, the session is marked failed and the exception is retained as its category and summary.

A failed date remains claimed. The scheduler will not retry it. A worker restart marks previously running sessions failed. There is no generation timeout, repeated steering, progress nudge, fallback artifact, or human recovery gate.

The scheduler runs continuously and sleeps until the next Eastern midnight after each pass. A production deployment should run it as a dedicated worker process, not inside the FastAPI web process.

## Persistence

### Postgres

`generation_sessions` stores:

- Internal session and game IDs.
- Unique release date.
- Running, completed, or failed status.
- Start/end timestamps.
- Failure category and summary.

`games` stores:

- Internal game ID and unique release date.
- Title and description.
- Ready or published status.
- Source and build object keys.
- Nullable screenshot key reserved for later catalog work.
- Creation and publication timestamps.

The release-date uniqueness constraints are the production concurrency claim. Local development uses an atomic JSON catalog with equivalent behavior.

### Object storage

The current local adapter copies two immutable trees:

```text
{game_id}/source/    complete retained maker workspace
{game_id}/build/     contents of dist/
```

The source tree includes prompts generated into the workspace, MCP/agent configuration, SDK JSONL events, the final response, source code, build tooling, and tester reports. A production object-store adapter can preserve the same keys without changing orchestration.

### Observability

Two append-only streams exist locally:

- `events.jsonl` records host lifecycle events such as session start, ready, and failure.
- Each workspace's `codex-events.jsonl` records public SDK notification method and payload objects as they arrive.

These are operator/postmortem artifacts. Players never see generation progress. The SDK stream makes long sessions diagnosable without steering them: operators can determine whether Codex is reasoning, running commands, calling MCP tools, spawning the tester, or completing the turn.

## Commands

Install the backend environment and run tests:

```bash
uv sync --project src/backend
uv run --project src/backend python -m unittest discover -s src/backend/tests -v
```

Run one generation:

```bash
uv run --project src/backend python -m src.backend.cli \
  --date 2026-07-21 --data-dir var/daily-games
```

Run the worker loop:

```bash
uv run --project src/backend python -m src.backend.cli \
  --loop --data-dir var/daily-games
```

Run an isolated real-tool rehearsal without catalog or object-store writes:

```bash
uv run --project src/backend python -m src.backend.cli \
  --artifact-only --real-smoke --date 2099-01-01 \
  --data-dir /tmp/vibe-check-codex-smoke
```

`--real-smoke` requires `--artifact-only`. The workspace and host event log remain available under the supplied temporary data directory, but no game/session catalog record or stored object is created.

## Security and deployment boundaries

- Provider secrets stay in the operator environment or global Codex MCP configuration, never in the repository or generated workspace.
- The SDK uses saved Codex subscription authentication; this path requires no `OPENAI_API_KEY`.
- Publication and database credentials are never exposed as agent tools.
- Generated code executes inside the Codex workspace-write sandbox.
- The tester remains read-only.
- Production 24/7 hosting, distributed worker leasing, production object storage, alerting, screenshot capture, mobile support, and cross-browser support remain deployment/product follow-ups.

## References

- [Codex SDK](https://developers.openai.com/codex/sdk)
- [Codex subagents](https://developers.openai.com/codex/subagents)
- [Codex MCP](https://developers.openai.com/codex/mcp)
- [Codex and the Agents SDK](https://developers.openai.com/codex/guides/agents-sdk)
- [Model Context Protocol Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp)
- [Google Cloud GenMedia Lyria MCP](https://googlecloudplatform.github.io/vertex-ai-creative-studio/experiments/mcp-genmedia/mcp-lyria-go/)
