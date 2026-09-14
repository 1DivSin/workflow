"""Runtime adapters for Codex, OpenClaw and Hermes."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from contextvars import ContextVar
import os
import shutil
import subprocess
from .providers import provider_environment

if TYPE_CHECKING:
    from .agent_runtime import AgentRuntime

HOST_ENV = "PSI_WORKFLOW_HOST"
WORKSPACE_ENV = "PSI_WORKFLOW_WORKSPACE"
TOOLS_ENV = "PSI_WORKFLOW_TOOLS_DIR"
STATE_ENV = "PSI_WORKFLOW_STATE_DIR"

@dataclass(frozen=True)
class HostConfig:
    name: str
    executable: str | None
    workspace: Path
    tools_dir: Path
    state_dir: Path
    command: tuple[str, ...]
    env: dict[str, str]

_ai_socket_provider: ContextVar[Callable[[], str | None] | None] = ContextVar("ai_socket", default=None)
_agent_factory: ContextVar[Callable[[object], object] | None] = ContextVar("agent_factory", default=None)
_agent_runtime_provider: ContextVar[Callable[[], "AgentRuntime | None"] | None] = ContextVar(
    "agent_runtime", default=None
)

def _credential_env() -> dict[str, str]:
    path = Path(os.getenv('PSI_WORKFLOW_CREDENTIALS', str(Path.home() / '.config/genuineknowledge/agents.env')))
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if value.strip():
                    values[key.strip()] = value.strip().strip(chr(34)).strip(chr(39))
    return values

def host_name() -> str:
    return os.getenv(HOST_ENV, "").strip().lower()

def host_config(default: str | Path = ".") -> HostConfig | None:
    root = Path(default).expanduser().resolve()
    name = host_name()
    home = Path.home()
    if name not in {"codex", "openclaw", "hermes"}:
        return None
    bases = {"codex": Path(os.getenv("CODEX_HOME", str(home / ".codex"))),
             "openclaw": Path(os.getenv("OPENCLAW_HOME", str(home / ".openclaw"))),
             "hermes": Path(os.getenv("HERMES_HOME", str(home / ".hermes")))}
    base = bases[name]
    exe = os.getenv(name.upper() + "_EXECUTABLE")
    source_roots = {'codex': Path('/public/home/sychen/cxy/open_source_agents/codex/bin/codex.js'), 'openclaw': Path('/public/home/sychen/cxy/open_source_agents/openclaw/openclaw.mjs'), 'hermes': Path('/public/home/sychen/cxy/open_source_agents/hermes-agent')}
    source = source_roots.get(name)
    exe = exe or shutil.which(name)
    if not exe and source and source.exists():
        exe = str(source)
    if not exe:
        return None
    workspace = Path(os.getenv(WORKSPACE_ENV, os.getenv(name.upper() + "_WORKSPACE", str(root))))
    tools = Path(os.getenv(TOOLS_ENV, str(base / "tools")))
    state = Path(os.getenv(STATE_ENV, str(base / "state")))
    command = ((('node', exe) if name in ('codex', 'openclaw') else ('python3', '-m', 'hermes_cli.main')) if exe else (name,))
    inherited_path = os.getenv("PATH", "")
    path_parts = ["/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin"]
    node_bin = Path("/public/home/sychen/.local/node-current/bin")
    if node_bin.is_dir():
        path_parts.insert(0, str(node_bin))
    if name == "hermes":
        hermes_bin = Path("/public/home/sychen/cxy/open_source_agents/hermes-agent/.venv/bin")
        if hermes_bin.is_dir():
            path_parts.insert(0, str(hermes_bin))
    if inherited_path:
        path_parts.append(inherited_path)
    stable_path = os.pathsep.join(dict.fromkeys(path_parts))
    env = {**_credential_env(), **os.environ, HOST_ENV: name, WORKSPACE_ENV: str(workspace), TOOLS_ENV: str(tools), STATE_ENV: str(state), "PATH": stable_path}
    try:
        env.update(provider_environment('default'))
    except (FileNotFoundError, RuntimeError):
        pass
    if name == 'hermes':
        env['PYTHONPATH'] = str(source_roots['hermes']) + os.pathsep + os.getenv('PYTHONPATH', '')
        venv = source_roots['hermes'] / '.venv' / 'bin' / 'python'
        if venv.exists():
            command = (str(venv), '-m', 'hermes_cli.main')
    return HostConfig(name, exe, workspace, tools, state, command, env)

def workspace_dir(default):
    config = host_config(default)
    return None if config is None else config.workspace

def tools_dir(default):
    config = host_config(default)
    return None if config is None else config.tools_dir

def state_dir(default):
    config = host_config(default)
    return None if config is None else config.state_dir

def host_available(default=".") -> bool:
    return host_config(default) is not None

def run_host(args=(), default=".") -> subprocess.CompletedProcess[str] | None:
    cfg = host_config(default)
    if cfg is None:
        return None
    if not cfg.executable:
        return None
    return subprocess.run((*cfg.command, *tuple(args)), cwd=cfg.workspace, env={**os.environ, **cfg.env}, text=True, capture_output=True, check=False)

def set_ai_socket_provider(provider): _ai_socket_provider.set(provider)
def ai_socket(default_provider=None):
    provider = _ai_socket_provider.get()
    if provider is None:
        return None if default_provider is None else default_provider()
    return provider()

def set_agent_factory(factory): _agent_factory.set(factory)
def agent_handle(config, default_factory=None):
    factory = _agent_factory.get()
    return None if factory is None else factory(config)


def set_agent_runtime_provider(provider: Callable[[], "AgentRuntime | None"] | None) -> None:
    """Set the host Agent Runtime provider for the current execution context."""

    _agent_runtime_provider.set(provider)


def agent_runtime(default: "AgentRuntime | None" = None) -> "AgentRuntime | None":
    """Return an injected runtime, or the built-in OpenClaw CLI adapter."""

    provider = _agent_runtime_provider.get()
    if provider is not None:
        return provider()
    if host_name() == "openclaw":
        from .adapters.openclaw_cli import OpenClawCliRuntime

        return OpenClawCliRuntime()
    return default

