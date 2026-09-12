import argparse,json
from .detect import detect_host
from .installer import install
from .uninstaller import uninstall
from .doctor import diagnose
def main():
 p=argparse.ArgumentParser(prog='method-installer'); s=p.add_subparsers(dest='c',required=True)
 s.add_parser('detect')
 i=s.add_parser('installer'); i.add_argument('source',nargs='?',default='.'); i.add_argument('--destination')
 u=s.add_parser('uninstaller'); u.add_argument('--target'); u.add_argument('--purge-state',action='store_true')
 d=s.add_parser('doctor'); d.add_argument('--root',default='.')
 a=p.parse_args()
 if a.c=='detect': print(json.dumps(detect_host(),indent=2))
 elif a.c=='installer': print('installed to',install(a.source,destination=a.destination))
 elif a.c=='uninstaller':
  for x in uninstall(target=a.target,purge_state=a.purge_state): print('removed',x)
 else: print(json.dumps(diagnose(a.root),indent=2))
if __name__=='__main__': main()
