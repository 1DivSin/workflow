import shutil,json
from pathlib import Path
from .detect import detect_host
def install(source,host=None,destination=None):
 h=host or detect_host(); s=Path(source).resolve(); d=Path(destination or Path(h['tools_dir'])/'genuineknowledge-method'); d.parent.mkdir(parents=True,exist_ok=True)
 if d.exists(): shutil.rmtree(d)
 shutil.copytree(s,d,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.git')); Path(h['state_dir']).mkdir(parents=True,exist_ok=True); (Path(h['state_dir'])/'genuineknowledge-method.json').write_text(json.dumps({'target':str(d),'host':h['name']},indent=2)); return d
