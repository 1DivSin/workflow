import shutil,json
from pathlib import Path
from .detect import detect_host
def uninstall(host=None,target=None,purge_state=False):
 h=host or detect_host(); m=Path(h['state_dir'])/'genuineknowledge-method.json'
 if not target and m.exists(): target=json.loads(m.read_text()).get('target')
 p=Path(target or Path(h['tools_dir'])/'genuineknowledge-method'); removed=[]
 if p.exists(): shutil.rmtree(p); removed.append(p)
 if purge_state and m.exists(): m.unlink(); removed.append(m)
 return removed
