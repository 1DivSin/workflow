import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class InstallCliTests(unittest.TestCase):
    def test_doctor_fails_before_installation(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root/'.codex').mkdir()
            env = dict(os.environ, USERPROFILE=raw, HOME=raw, CODEX_HOME=str(root/'.codex'),
                PSI_WORKFLOW_STATE_DIR=str(root/'missing-state'), PYTHONPATH=str(ROOT/'src'))
            result = subprocess.run([sys.executable,'-m','installer.cli','doctor','--host','codex'],
                env=env,cwd=root,text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(json.loads(result.stdout)['ok'])

    def test_explicit_host_installs_complete_skill_without_environment_copy(self):
        for host in ('codex', 'hermes', 'openclaw'):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                source, home, workspace = root/'source', root/'home', root/'project'
                (source/'src'/'grammar').mkdir(parents=True)
                (source/'.venv').mkdir()
                (source/'src'/'SKILL.md').write_text('---\nname: workflow\ndescription: test\n---\nRead grammar/FusionFlow.g4\n',encoding='utf-8')
                (source/'src'/'grammar'/'FusionFlow.g4').write_text('grammar FusionFlow;',encoding='utf-8')
                (source/'.venv'/'sentinel').write_text('do not copy')
                workspace.mkdir()
                for name in ('codex','hermes','openclaw'):
                    (home/('.'+name)).mkdir(parents=True)
                env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYTHONPATH=str(ROOT/'src'), PYTHONDONTWRITEBYTECODE='1')
                for name in list(env):
                    if name.startswith(('CODEX_', 'HERMES_', 'OPENCLAW_', 'PSI_WORKFLOW_')):
                        env.pop(name)
                result = subprocess.run([sys.executable,'-m','installer.cli','installer',str(source),'--host',host,'--workspace',str(workspace)],env=env,cwd=root,text=True,capture_output=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                record = json.loads((home/('.'+host)/'state'/'genuineknowledge-method.json').read_text())
                skill = Path(record['skill_dir'])
                self.assertTrue((skill/'grammar'/'FusionFlow.g4').is_file())
                self.assertFalse((Path(record['target'])/'.venv').exists())
                self.assertEqual(record['host'],host)

if __name__=='__main__':
    unittest.main()
