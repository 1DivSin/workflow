import json, subprocess, sys
p=json.load(sys.stdin)
sha=p["inputs"]["item"]
r=subprocess.run(["git","-C","/public/home/sychen/cxy/open_source_agents/psi-agent","show","--format=fuller","--stat","--name-status",sha],capture_output=True,text=True)
sys.stdout.write(r.stdout)
sys.stderr.write(r.stderr)
sys.exit(r.returncode)
