# @genuineknowledge/method

Host-agnostic workflow runtime with shared provider routing and host adapters for Codex, OpenClaw, and Hermes.

## Install Workflow

Prerequisites: uv and an installed host (Codex, Hermes, or OpenClaw).
Authenticate the host with its normal setup before running model-backed workflows.
For OpenClaw, use Node 26.1+ or 24.16+; the native integration is tested against 2026.9.4.
Replace `/path/to/project` with an existing workspace (quote Windows paths).
The Workflow runtime does not install or manage host runtimes. If Hermes is not already installed, install it separately with both MCP and ACP support as shown below.

### Recommended: install the runtime as a uv tool

Install once:

```sh
uv tool install git+https://github.com/1DivSin/workflow.git
```

This creates isolated, source-independent `dynamic-workflow`,
`dynamic-workflow-mcp`, and `dynamic-workflow-tool` entrypoints. Host
configuration records the absolute installed CLI path rather than the Python
interpreter that happened to run the installer.

To provision separate Codex and Hermes integrations in one run, repeat `--host`:

```sh
dynamic-workflow install --host codex --host hermes --workspace /path/to/project
```

This creates one host-specific registration, asset destination, and state directory per
host. Each frontend then starts its own MCP process; no shared shell-wide host selector
is required.


#### Codex

```sh
dynamic-workflow install --host codex --workspace /path/to/project
dynamic-workflow doctor --host codex --workspace /path/to/project
```

#### Hermes

If Hermes is already installed with MCP and ACP support, skip the first three commands.
Installing Hermes as its own uv tool exposes the `hermes` and `hermes-acp` executables on PATH; putting `hermes-agent` only inside Workflow's dependency environment does not.

```sh
uv tool install 'hermes-agent[mcp,acp]'
hermes --help
hermes-acp --check
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
When more than one host uses Workflow, run the install command once per host. Each
host gets its own MCP registration, asset destination, config, and state directory.
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

## Direct runtime host selection
For direct Python/runtime invocations, select the host with `PSI_WORKFLOW_HOST`.
Host installations should use the per-host commands above so each MCP process gets
its own selector.

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

### Program Agent execution

A Program is an Agent-backed executor. All hosts reuse the same `compile_program`,
`execute_program`, and `submit_program_result` functions in `run_flow.py`.
The psi runtime registers these as native tools. Standalone Codex, Hermes, and
OpenClaw use a text JSON bridge: the Agent returns one
`{"tool":"execute_program","arguments":{"runtime":"python"}}` request; the
workflow invokes that function and feeds the actual result back to the Agent.
The prompt includes the Program policy, function signatures, tool descriptions,
and execution contract. Subsequent turns include both earlier calls and results.
This bridge does not register new native tools in the host or rely on model-written
Artifact values. Native host tools may inspect and prepare the environment.

- Interpreted source: `execute_program(runtime=...)` builds the declared script argv
  and captures stdin, stdout, stderr, and exit status.
- Compiled source: `compile_program(compile_argv, execute_argv, artifact_paths)` runs
  the compiler and registers the source/artifact hashes and exact launch command.
  `execute_program(compiled_launch_argv=...)` verifies this registration before launch.
- `submit_program_result()` publishes captured output. In fidelity mode, repeated
  execution requests do not launch again or replace the first captured result.

Malformed or unknown bridge requests get one correction attempt. The entire
conversation has a bounded tool-round count. A host turn (including initialization)
uses `PSI_WORKFLOW_PROGRAM_AGENT_TIMEOUT`, defaulting to 90 seconds; Hermes retains
`PSI_WORKFLOW_HERMES_SESSION_TIMEOUT` as the fallback. Program subprocess execution
continues to use declared Step/workflow timeouts. Native transports drain stderr,
clean up on failed initialization/cancellation, and bound their shutdown wait.

Environment preparation is trusted workspace execution, not a sandbox. There is
no executable-name blacklist. The declared source, logical arguments, input bytes,
registered artifacts, and captured result remain the runtime contract. Host-native
approval settings still apply; this bridge does not bypass or forward approval UI.
Codex/Hermes currently start a native turn with replayed bridge history; an injected
AgentRuntime also receives a stable logical session ID. Tests use deterministic
Agent replies and real subprocesses/bytecode compilation; they do not certify live
model behavior or every host's environment-installation permissions.

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
