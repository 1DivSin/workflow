from pathlib import Path
import os
def workspace_dir(explicit=''): return explicit or os.environ.get('PSI_WORKFLOW_WORKSPACE', str(Path.cwd()))
def agent_dir(explicit=''): return explicit or os.environ.get('PSI_WORKFLOW_AGENT', str(Path(__file__).resolve().parent))
def resolve_workspace(raw=''): return Path(workspace_dir(raw))
def resolve_agent(raw=''): return Path(agent_dir(raw))
def resolve_under(root,path):
 p=Path(path or '.')
 return p if p.is_absolute() else Path(root)/p
def resolve_user_path(path, workspace_raw=''): return resolve_under(workspace_dir(workspace_raw), path)
