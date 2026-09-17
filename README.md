# @genuineknowledge/method

Host-agnostic workflow runtime with shared provider routing and host adapters for Codex, OpenClaw, and Hermes.

## Install Workflow

Prerequisites: uv and an installed host (Codex, Hermes, or OpenClaw).
Authenticate the host with its normal setup before running model-backed workflows.
For OpenClaw, use Node 26.1+ or 24.16+; the native integration is tested against 2026.9.4.
Replace `/path/to/project` with an existing workspace (quote Windows paths).

### Recommended: install the runtime as a uv tool

Install once:

```sh
uv tool install git+https://github.com/1DivSin/workflow.git
```

This creates isolated, source-independent `dynamic-workflow`,
`dynamic-workflow-mcp`, and `dynamic-workflow-tool` entrypoints. Host
configuration records the absolute installed CLI path rather than the Python
interpreter that happened to run the installer.

#### Codex

```sh
dynamic-workflow install --host codex --workspace /path/to/project
dynamic-workflow doctor --host codex --workspace /path/to/project
```

#### Hermes

```sh
dynamic-workflow install --host hermes --workspace /path/to/project
dynamic-workflow doctor --host hermes --workspace /path/to/project
```

#### OpenClaw

The install command explicitly accepts the three tools declared in the bundled plugin manifest.

```sh
dynamic-workflow install --host openclaw --workspace /path/to/project --register-plugin --accept-capabilities
dynamic-workflow doctor --host openclaw --workspace /path/to/project
```

The original checkout is not required after this installation. Python and
runtime dependencies are owned by uv's isolated tool environment; the host only
keeps skill/plugin assets and stable CLI launch commands.

### Source/development mode

For development, keep the checkout and pass it explicitly:

```sh
git clone https://github.com/1DivSin/workflow.git workflow
cd workflow
uv sync --python 3.12
uv run dynamic-workflow install . --host codex --workspace /path/to/project
```

When a source path is supplied, the registered runtime intentionally uses:

```text
uv run --project /path/to/workflow dynamic-workflow-mcp
```

and OpenClaw uses the corresponding `dynamic-workflow-tool` command. This mode
is convenient for editing the runtime in place, but the source checkout must
remain available.

Start a new host session after installation so the skill/tools are rediscovered.
Codex uses `mcp_servers.fusion_flow` in `config.toml`; Hermes uses the same server
name in its `config.yaml`; OpenClaw registers the native plugin's three tools.
`doctor` reads the written configuration, launches the actual MCP process,
checks `tools/list`, and calls `flow_manage`. OpenClaw also loads the native plugin
through `plugins inspect --runtime` and verifies its registered tools.
Any failed check returns a nonzero exit code.

### What CI proves

The installation workflow runs on Linux and Windows for all three hosts. Its
installation smoke test creates an isolated `uv tool install` deployment,
registers the host from the installed `dynamic-workflow` CLI, and launches the
actual `dynamic-workflow-mcp` entrypoint. This verifies that the installed
integration does not depend on the repository checkout's `.venv`, interpreter,
or `PYTHONPATH`.

The suite also runs parser/runtime regression tests, the OpenClaw subprocess
bridge test, and the Human checkpoint/restart test. The Human test injects a
deterministic question generator; it exercises the real workflow parser,
scheduler, persisted checkpoint and resume logic. It does not claim a live LLM
or chat UI test, and CI needs no model API keys.

`uv run python scripts/check_install.py --host codex` (or `hermes` / `openclaw`)
repeats the packaged installation check locally without changing your normal
host config.

## Provider configuration

Copy the example configuration:

~~~bash
mkdir -p ~/.config/genuineknowledge
export OPENAI_BASE_URL=https://your-provider.example/v1
# Optional DeepSeek route: set DEEPSEEK_BASE_URL and DEEPSEEK_API_KEY, then use deepseek:model in models
cp config/providers.example.json ~/.config/genuineknowledge/providers.json
chmod 600 ~/.config/genuineknowledge/providers.json
~~~

Keep credentials outside the repository. Set the key named by the provider configuration:

~~~bash
export OPENAI_API_KEY="your-key"
~~~

The example routes planning, default, and fallback to an OpenAI-compatible endpoint. Override the configuration location with:

~~~bash
export PSI_WORKFLOW_PROVIDER_CONFIG="$HOME/.config/genuineknowledge/providers.json"
~~~

The provider loader supports baseURLs, apiKeys, and models roles. A model such as provider:model selects baseURLs.provider; models without a prefix use baseURLs.default.

## Host adapters

Select the runtime host with PSI_WORKFLOW_HOST:

~~~bash
export PSI_WORKFLOW_HOST=codex      # Codex app-server
export PSI_WORKFLOW_HOST=hermes     # Hermes ACP
export PSI_WORKFLOW_HOST=openclaw   # OpenClaw gateway
~~~

The runtime can be invoked directly from Python during development:

~~~bash
uv run python - <<'PY'
import asyncio, json
from run_flow import run_flow

result = asyncio.run(run_flow(
    "flows/q08/q08.workflow",
    json.dumps({"state": {"epoch": 0}}),
    max_loop_epochs=3,
))
print(result)
PY
~~~

### Codex app-server

Codex steps use the JSONL app-server transport. Set the executable explicitly when it is not on PATH:

~~~bash
export CODEX_APP_SERVER_COMMAND="/path/to/codex app-server --stdio"
~~~

The adapter waits for turn/completed and extracts only item/agentMessage/delta events. This prevents thread metadata and command execution events from being mistaken for the Agent final response. Agent TerminalStep output is checked as strict JSON Boolean data; invalid output enters a bounded repair path.

### Hermes ACP

Set the Hermes ACP executable:

~~~bash
export HERMES_ACP_COMMAND="/path/to/hermes-acp"
export PSI_WORKFLOW_HERMES_SESSION_TIMEOUT=90
~~~

Hermes Program steps execute the declared script deterministically with the workflow stdin and cwd. Agent TerminalStep and Human preparation responses are parsed against their strict JSON contracts, with bounded repair for invalid Agent output.

### Diagnostics

For Codex event diagnostics, set an event log path through the adapter environment:

~~~bash
export CODEX_EVENT_LOG="/tmp/codex-events.jsonl"
~~~

The log records event methods, parameter keys, and Agent message deltas without recording command output. A run stores artifacts and timing data under its workflow run directory. Do not commit run directories or files containing private repository contents.

Install and remove the host integration with:

~~~bash
dynamic-workflow install --host codex --workspace /path/to/project
dynamic-workflow uninstall --host codex --workspace /path/to/project
~~~

The same three workflow tools can be registered through any MCP-compatible host
by launching the installed stdio entrypoint:

~~~bash
dynamic-workflow-mcp
~~~

For source development, use:

~~~bash
uv run --project . dynamic-workflow-mcp
~~~

The host adapter reads the shared provider configuration and passes the resolved endpoint, model, and credential environment to the selected host. Secrets must never be committed.

## Development checks

~~~bash
uv run python -m compileall -q src
uv run pytest tests -q
npm test
~~~
