from __future__ import annotations
import json, os
from dataclasses import dataclass
from pathlib import Path
@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key_env: str
    model: str
def _config_path() -> Path:
    return Path(os.getenv('PSI_WORKFLOW_PROVIDER_CONFIG', str(Path.home()/'.config/genuineknowledge/providers.json'))).expanduser()
def load_providers(path: str|Path|None=None) -> dict[str, Provider]:
    p=Path(path).expanduser() if path else _config_path()
    if not p.exists(): return {}
    raw=json.loads(p.read_text(encoding='utf-8')); urls=raw.get('baseURLs',{}); keys=raw.get('apiKeys',{}); models=raw.get('models',{}); out={}
    for role, model in models.items():
        if not isinstance(model,str) or not model: continue
        route=model.split(':',1)[0] if ':' in model else 'default'; key=keys.get(route,keys.get('default','OPENAI_API_KEY'))
        if isinstance(key,str) and key.startswith('$'): key=key[1:]
        base_url = os.path.expandvars(str(urls.get(route, urls.get('default', '')))).rstrip('/')
        out[role]=Provider(route,base_url,str(key),model.split(':',1)[1] if ':' in model else model)
    return out
def select_provider(role='default', *, path=None) -> Provider:
    providers=load_providers(path)
    if role in providers: return providers[role]
    if 'default' in providers: return providers['default']
    raise FileNotFoundError('No provider route configured')
def provider_environment(role='default', *, path=None) -> dict[str,str]:
    p=select_provider(role,path=path); key=os.getenv(p.api_key_env,'')
    if not key: raise RuntimeError(f'Missing provider credential environment variable: {p.api_key_env}')
    return {'OPENAI_BASE_URL':p.base_url,'OPENAI_API_KEY':key,'OPENAI_MODEL':p.model}

