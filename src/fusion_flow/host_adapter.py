"""Runtime adapters for Codex, OpenClaw and Hermes."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from contextvars import ContextVar
import os, shutil, subprocess

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

def _credential_env() -> dict[str, str]:
    path = Path(os.getenv('PSI_WORKFLOW_CREDENTIALS', str(Path.home() / '.config/genuineknowledge/agents.env')))
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                if value.strip(): values[key.strip()] = value.strip().strip(chr(34)).strip(chr(39))
    return values

def host_name() -> str:
    return os.getenv(HOST_ENV, "generic").strip().lower() or "generic"

def host_config(default: str | Path = ".") -> HostConfig:
    root = Path(default).expanduser().resolve()
    name = host_name()
    home = Path.home()
    bases = {"codex": Path(os.getenv("CODEX_HOME", str(home / ".codex"))),
             "openclaw": Path(os.getenv("OPENCLAW_HOME", str(home / ".openclaw"))),
             "hermes": Path(os.getenv("HERMES_HOME", str(home / ".hermes")))}
    base = bases.get(name, root / ".psi")
    exe = os.getenv(name.upper() + "_EXECUTABLE") if name in bases else None
    source_roots = {'codex': Path('/public/home/sychen/cxy/open_source_agents/codex/bin/codex.js'), 'openclaw': Path('/public/home/sychen/cxy/open_source_agents/openclaw/openclaw.mjs'), 'hermes': Path('/public/home/sychen/cxy/open_source_agents/hermes-agent')}
    source = source_roots.get(name)
    exe = exe or (shutil.which(name) if name in bases else None)
    if not exe and source and source.exists():
        exe = str(source)
    workspace = Path(os.getenv(WORKSPACE_ENV, os.getenv(name.upper() + "_WORKSPACE", str(root))))
    tools = Path(os.getenv(TOOLS_ENV, str(base / "tools")))
    state = Path(os.getenv(STATE_ENV, str(base / "state")))
    command = ((('node', exe) if name in ('codex', 'openclaw') else ('python3', '-m', 'hermes_cli.main')) if exe else (name,))
    env = {**_credential_env(), **os.environ, 'PSI_WORKFLOW_HOST': name, WORKSPACE_ENV: str(workspace), TOOLS_ENV: str(tools), STATE_ENV: str(state), 'PATH': '/public/home/sychen/.local/node-current/bin:' + os.getenv('PATH', '')}
    if name == 'hermes':
        env['PYTHONPATH'] = str(source_roots['hermes']) + os.pathsep + os.getenv('PYTHONPATH', '')
        venv = source_roots['hermes'] / '.venv' / 'bin' / 'python'
        if venv.exists(): command = (str(venv), '-m', 'hermes_cli.main')
    return HostConfig(name, exe, workspace, tools, state, command, env)

def workspace_dir(default): return host_config(default).workspace
def tools_dir(default): return host_config(default).tools_dir
def state_dir(default): return host_config(default).state_dir

def run_host(args=(), default=".") -> subprocess.CompletedProcess[str]:
    cfg = host_config(default)
    if not cfg.executable:
        raise FileNotFoundError(f"{cfg.name} executable not found; set {cfg.name.upper()}_EXECUTABLE")
    return subprocess.run((*cfg.command, *tuple(args)), cwd=cfg.workspace, env={**os.environ, **cfg.env}, text=True, capture_output=True, check=False)

def set_ai_socket_provider(provider): _ai_socket_provider.set(provider)
def ai_socket(default_provider): return (_ai_socket_provider.get() or default_provider)()
def set_agent_factory(factory): _agent_factory.set(factory)
def agent_handle(config, default_factory): return (_agent_factory.get() or default_factory)(config)
