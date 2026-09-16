# @genuineknowledge/method

Host-agnostic workflow runtime with shared provider routing and host adapters for Codex, OpenClaw, and Hermes.

## Requirements

- Python 3.12 or newer
- uv
- Node.js 18 or newer (only for npm packaging or JavaScript checks)

## Installation

For an Agent host, installation is a host concern: bundle this skill and let the host run the Python runtime with `uv run`. End users only describe the workflow in natural language.

For local development, clone the repository and let uv create the isolated environment:

~~~bash
git clone https://github.com/1DivSin/workflow.git
cd workflow
uv sync
~~~

Run commands through the project environment:

~~~bash
uv run python -m installer.cli installer .
~~~

`npm install` is only needed for npm packaging or JavaScript checks; it does not install the Python runtime.

Run the repository checks:

~~~bash
python -m compileall -q src installer
npm test
~~~

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

The runtime can be invoked directly from Python:

~~~bash
python - <<'PY'
import asyncio, json
from src.run_flow import run_flow

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
python -m installer.cli installer .
python -m installer.cli uninstaller
~~~

The host adapter reads the shared provider configuration and passes the resolved endpoint, model, and credential environment to the selected host. Secrets must never be committed.

## Development checks

~~~bash
python -m compileall -q src installer
npm test
~~~
