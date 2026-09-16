"""Runtime adapters for Codex, OpenClaw and Hermes."""
from __future__ import annotations
import os
import shlex
import shutil
import subprocess
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable
from contextvars import ContextVar
import os, shutil, subprocess
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
_agent_runtime_provider: ContextVar[Callable[[], "AgentRuntime | None"] | None] = ContextVar("agent_runtime", default=None)

def _credential_env() -> dict[str, str]:
    path = Path(os.getenv("PSI_WORKFLOW_CREDENTIALS", str(Path.home() / ".config/genuineknowledge/agents.env")))
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if value.strip(): values[key.strip()] = value.strip().strip('"').strip("'")
    return values

def host_name() -> str:
    return os.getenv(HOST_ENV, "").strip().lower()

def _split_command(value: str) -> tuple[str, ...]:
    return tuple(shlex.split(value, posix=os.name != "nt"))

def _host_command(name: str, executable: str | None) -> tuple[str, ...]:
    override = os.getenv({"codex": "CODEX_APP_SERVER_COMMAND", "hermes": "HERMES_ACP_COMMAND", "openclaw": "OPENCLAW_COMMAND"}[name], "").strip()
    if override:
        command = _split_command(override)
        if command: return command
    if executable is None: return ()
    return (executable, "app-server", "--stdio") if name == "codex" else (executable,)
def _workspace_override(default: str | Path) -> Path:
    name = host_name()
    raw = os.getenv(WORKSPACE_ENV) or (
        os.getenv(name.upper() + "_WORKSPACE") if name in {"codex", "openclaw", "hermes"} else None
    )
    return Path(raw or default).expanduser().resolve()

def host_config(default: str | Path = ".") -> HostConfig | None:
    root = Path(default).expanduser().resolve()
    name = host_name()
    if name not in {"codex", "openclaw", "hermes"}: return None
    home = Path.home()
    bases = {"codex": Path(os.getenv("CODEX_HOME", str(home / ".codex"))), "openclaw": Path(os.getenv("OPENCLAW_HOME", str(home / ".openclaw"))), "hermes": Path(os.getenv("HERMES_HOME", str(home / ".hermes")))}
    base = bases[name]
    override = os.getenv({"codex": "CODEX_EXECUTABLE", "openclaw": "OPENCLAW_EXECUTABLE", "hermes": "HERMES_EXECUTABLE"}[name], "").strip()
    command_override = os.getenv({"codex": "CODEX_APP_SERVER_COMMAND", "hermes": "HERMES_ACP_COMMAND", "openclaw": "OPENCLAW_COMMAND"}[name], "").strip()
    executable = override or (_split_command(command_override) or (None,))[0] or shutil.which(name)
    command = _host_command(name, executable)
    if not executable or not command: return None
    workspace = Path(os.getenv(WORKSPACE_ENV, os.getenv(f"{name.upper()}_WORKSPACE", str(root))))
    tools = Path(os.getenv(TOOLS_ENV, str(base / "tools")))
    state = Path(os.getenv(STATE_ENV, str(base / "state")))
    env = {**_credential_env(), **os.environ, HOST_ENV: name, WORKSPACE_ENV: str(workspace), TOOLS_ENV: str(tools), STATE_ENV: str(state)}
    try: env.update(provider_environment("default"))
    except (FileNotFoundError, RuntimeError): pass
    if os.getenv("HERMES_PYTHONPATH"): env["PYTHONPATH"] = os.getenv("HERMES_PYTHONPATH", "")
    return HostConfig(name, executable, workspace, tools, state, command, env)
    configured_exe = os.getenv(name.upper() + "_EXECUTABLE", "").strip() or None
    exe = configured_exe
    source_raw = os.getenv(name.upper() + "_SOURCE")
    source = Path(source_raw).expanduser() if source_raw else None
    exe = exe or shutil.which(name)
    if not exe and source and source.exists():
        exe = str(source)
    if not exe:
        return None
    workspace = _workspace_override(root)
    tools = Path(os.getenv(TOOLS_ENV, str(base / "tools")))
    state = Path(os.getenv(STATE_ENV, str(base / "state")))
    command = ((('node', exe) if name in ('codex', 'openclaw') else (exe,)) if exe else (name,))
    inherited_path = os.getenv("PATH", "")
    stable_path = inherited_path
    env = {**_credential_env(), **os.environ, HOST_ENV: name, WORKSPACE_ENV: str(workspace), TOOLS_ENV: str(tools), STATE_ENV: str(state), "PATH": stable_path}
    try:
        env.update(provider_environment('default'))
    except (FileNotFoundError, RuntimeError):
        pass
    if name == 'hermes':
        if source and source.is_dir():
            env['PYTHONPATH'] = str(source) + os.pathsep + os.getenv('PYTHONPATH', '')
            venv = source / '.venv' / 'bin' / 'python'
            if not configured_exe and venv.exists(): command = (str(venv), '-m', 'hermes_cli.main')
    return HostConfig(name, exe, workspace, tools, state, command, env)

def workspace_dir(default: str | Path = ".") -> Path:
    config = host_config(default)
    return config.workspace if config is not None else _workspace_override(default)

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
    if cfg is None: return None
    return subprocess.run((*cfg.command, *tuple(args)), cwd=cfg.workspace, env=cfg.env, text=True, capture_output=True, check=False)

def set_ai_socket_provider(provider): _ai_socket_provider.set(provider)
def ai_socket(default_provider=None):
    provider = _ai_socket_provider.get()
    return None if provider is None else provider()
def set_agent_factory(factory): _agent_factory.set(factory)
def agent_handle(config, default_factory=None):
    factory = _agent_factory.get()
    return None if factory is None else factory(config)


def set_agent_runtime_provider(provider: Callable[[], "AgentRuntime | None"] | None) -> None:
    _agent_runtime_provider.set(provider)


def agent_runtime(default: "AgentRuntime | None" = None) -> "AgentRuntime | None":
    provider = _agent_runtime_provider.get()
    if provider is not None:
        return provider()
    if host_name() == "openclaw":
        from .adapters.openclaw_cli import OpenClawCliRuntime
        return OpenClawCliRuntime()
    return default
