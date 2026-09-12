# @genuineknowledge/method

Host-agnostic workflow runtime with shared provider routing and host adapters for Codex, OpenClaw, and Hermes.

## Requirements

- Node.js 18 or newer
- Python 3.11 or newer
- uv for isolated Python environments

## Installation

Clone the repository and install the Node dependencies:

~~~bash
git clone https://github.com/1DivSin/workflow.git
cd workflow
npm install
~~~

Create a Python environment and install the project:

~~~bash
uv venv --python 3.11
uv pip install -e .
~~~

Run the repository checks:

~~~bash
npm test
~~~

## Provider configuration

Copy the example configuration:

~~~bash
mkdir -p ~/.config/genuineknowledge
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

The runtime detects the selected host with PSI_WORKFLOW_HOST:

~~~bash
export PSI_WORKFLOW_HOST=codex      # or openclaw or hermes
python -m installer.cli detect
python -m installer.cli doctor
~~~

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

