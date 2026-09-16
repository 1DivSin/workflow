"""Run the documented installer and its MCP doctor in an isolated host home.

No model credentials are needed. This verifies installation/registration and a
real flow_manage tool call; it does not claim a live model or chat-UI test.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', choices=['codex','hermes','openclaw'], required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='workflow-install-') as raw:
        area = Path(raw)
        home, project = area/'home', area/'project'
        project.mkdir()
        (home/('.'+args.host)).mkdir(parents=True)
        for child in ('tmp', 'cache', 'local', 'appdata'):
            (area/child).mkdir()
        env = {k:v for k,v in os.environ.items() if not k.startswith(('CODEX_','HERMES_','OPENCLAW_','PSI_WORKFLOW_','DYNAMIC_WORKFLOW_'))}
        env.update(HOME=str(home), USERPROFILE=str(home), PYTHONPATH=str(ROOT/'src'),
                   PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1',
                   OPENCLAW_STATE_DIR=str(home/'.openclaw'), OPENCLAW_CONFIG_PATH=str(home/'.openclaw'/'openclaw.json'))
        env.update(TEMP=str(area/'tmp'), TMP=str(area/'tmp'), TMPDIR=str(area/'tmp'),
                   XDG_CACHE_HOME=str(area/'cache'), LOCALAPPDATA=str(area/'local'), APPDATA=str(area/'appdata'))
        command = [sys.executable,'-m','installer.cli','installer',str(ROOT),'--host',args.host,'--workspace',str(project)]
        if args.host == 'openclaw':
            command += ['--register-plugin','--accept-capabilities']
        subprocess.run(command, env=env, check=True, cwd=project, timeout=240)
        doctor = subprocess.run([sys.executable,'-m','installer.cli','doctor','--host',args.host,'--workspace',str(project)],
            env=env,cwd=project,text=True,encoding='utf-8',capture_output=True,timeout=120)
        print(doctor.stdout)
        if args.report:
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(doctor.stdout,encoding='utf-8')
        if doctor.returncode:
            raise RuntimeError(doctor.stderr or doctor.stdout)
        report = json.loads(doctor.stdout)
        assert report['ok'] and report['checks']['tool_call'], report


if __name__=='__main__':
    main()
