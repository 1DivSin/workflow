import shutil,sys
from .detect import detect_host
def diagnose(root='.'): 
 h=detect_host(root); return {'ok':sys.version_info>=(3,11) and bool(shutil.which('node')),'host':h}
