import os,shutil,json
from pathlib import Path
def detect_host(root='.'): 
 r=Path(root).resolve(); forced=os.getenv('PSI_WORKFLOW_HOST',''); names=[forced] if forced else ['codex','openclaw','hermes']
 for n in names:
  if n in ('codex','openclaw','hermes') and (shutil.which(n) or (Path.home()/('.'+n)).exists() or forced==n):
   h=Path(os.getenv(n.upper()+'_HOME',str(Path.home()/('.'+n)))); return {'name':n,'workspace':str(Path(os.getenv(n.upper()+'_WORKSPACE',str(r)))),'state_dir':str(h/'state'),'tools_dir':str(h/'tools'),'available':True}
 return {'name':'generic','workspace':str(r),'state_dir':str(r/'.psi/state'),'tools_dir':str(r/'.psi/tools'),'available':False}
