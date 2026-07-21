# MCP and subscription setup

The game maker uses saved Codex subscription authentication through the Python Codex SDK. Do not add an `OPENAI_API_KEY` for this path.

## Global generation tools

Three MCP servers are registered in the operator's global Codex configuration:

| Server | Purpose | Credential |
| --- | --- | --- |
| Exa | Web research and asset discovery | `EXA_API_KEY` |
| Lyria | One Lyria 3 Clip music loop | Google Cloud ADC and project configuration |
| Chrome DevTools | Headless browser testing | None |

Inspect registrations without printing credentials:

```bash
codex mcp list
codex mcp get exa
codex mcp get lyria
codex mcp get chrome-devtools
```

The Python harness enables those registrations in each generated workspace. It does not copy their commands or credentials into the repository.

## Credentials

Keep credentials in the shell environment or an operator-managed Codex environment file:

```bash
export EXA_API_KEY="..."
export GOOGLE_CLOUD_PROJECT="codex-503104"
export GOOGLE_CLOUD_LOCATION="us-central1"
```

Local Lyria access uses Google Application Default Credentials:

```bash
gcloud auth application-default login
```

A non-interactive worker may instead point `GOOGLE_APPLICATION_CREDENTIALS` at a separately managed service-account file. Never place that file in this repository or a generated game workspace.

Restart Codex processes after changing environment variables so newly launched MCP servers inherit them.

## Workspace-local delivery tool

The harness automatically adds a fourth MCP server to every game workspace. `delivery-validator` is launched with the backend's active Python executable and exposes only `validate_delivery`.

The registration is:

- Required to initialize.
- Bound to the generated workspace as its working directory.
- Read-only and idempotent.
- Automatically approved.
- The tester is instructed to report against the package without calling it.

It has no credentials and accepts no path argument.

## Verification

Verify saved Codex authentication and installed runtime:

```bash
codex doctor
codex --version
```

Run backend tests:

```bash
uv sync --project src/backend
uv run --project src/backend python -m unittest discover -s src/backend/tests -v
```

Run an isolated real-tool rehearsal with an unused date and temporary directory:

```bash
uv run --project src/backend python -m src.backend.cli \
  --artifact-only --real-smoke --date 2099-01-01 \
  --data-dir /tmp/vibe-check-codex-smoke
```

The rehearsal requests real Exa, Lyria, Chrome, native tester, and delivery-validator calls. It keeps its workspace and event logs locally but leaves the catalog and object store untouched.
