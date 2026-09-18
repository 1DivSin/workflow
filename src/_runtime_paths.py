from pathlib import Path
import os

def _resolved(raw: str, fallback: Path) -> Path:
    return Path(raw or fallback).expanduser().resolve()

def workspace_dir(explicit=''):
    return str(_resolved(explicit or os.environ.get('PSI_WORKFLOW_WORKSPACE', ''), Path.cwd()))

def agent_dir(explicit=''):
    return str(_resolved(explicit or os.environ.get('PSI_WORKFLOW_AGENT', ''), Path(__file__).resolve().parent))

def resolve_workspace(raw=''): return Path(workspace_dir(raw))
def resolve_agent(raw=''): return Path(agent_dir(raw))
def resolve_under(root, path):
    candidate = Path(path or '.').expanduser()
    return candidate if candidate.is_absolute() else Path(root).expanduser().resolve() / candidate
def resolve_user_path(path, workspace_raw=''): return resolve_under(workspace_dir(workspace_raw), path)
