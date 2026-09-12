#!/usr/bin/env python3
"""Minimal host integration installer."""
import argparse, shutil
from pathlib import Path
TARGETS={"codex":".agents/skills/open-dynamic-workflows","openclaw":"skills/open-dynamic-workflows","hermes":".hermes/skills/open-dynamic-workflows"}
def detect(root): return {k:(root/Path(v).parent).exists() for k,v in TARGETS.items()}
def main():
 p=argparse.ArgumentParser(); p.add_argument("action",choices=["detect","install","uninstall","doctor"]); p.add_argument("host",nargs="?"); p.add_argument("--root",type=Path,default=Path.cwd()); a=p.parse_args()
 if a.action in ("detect","doctor"): print(detect(a.root)); return
 t=a.root/TARGETS[a.host]
 if a.action=="install": t.mkdir(parents=True,exist_ok=True); shutil.copy2(Path(__file__).parents[1]/"src"/"SKILL.md",t/"SKILL.md"); print(t)
 else: shutil.rmtree(t,ignore_errors=True)
if __name__=="__main__": main()
