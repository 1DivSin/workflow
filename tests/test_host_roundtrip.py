"""Human checkpoint tests with a deterministic model boundary, not live chat UI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '''
const decision: Artifact;
const ask: Step;
const reviewer: Human, Executor;
workflow approval {
  input_workflow(approval) == [];
  produces(ask) == [decision];
  output_workflow(approval) == [decision];
  step_executor(ask) == reviewer;
  step_name(ask) == "Review";
  step_instruction(ask) == "Ask the user to approve or reject.";
}
'''
WORKER = '''
import asyncio, json, sys
from fusion_flow.agent_runtime import AgentReply
from fusion_flow.host_adapter import set_agent_runtime_provider
from run_flow import run_flow, run_flow_resume
class FixedModel:
    def supports_agent_steps(self): return True
    async def run_agent(self, invocation):
        return AgentReply(text=json.dumps({"question":"Approve?", "options":["approve","reject"], "recommended":1,"default":""}))
set_agent_runtime_provider(lambda: FixedModel())
function = run_flow if sys.argv[1] == "run" else run_flow_resume
print(asyncio.run(function(**json.loads(sys.argv[2]))))
'''

class HostRoundTripTests(unittest.TestCase):
    def test_human_wait_and_resume_survive_process_restart(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw)
            (root/'flows').mkdir()
            (root/'flows'/'approval.workflow').write_text(SOURCE,encoding='utf-8')
            env=dict(os.environ, PYTHONPATH=str(ROOT/'src'), PYTHONDONTWRITEBYTECODE='1',
                PSI_WORKFLOW_HOST='openclaw', OPENCLAW_EXECUTABLE=sys.executable,
                PSI_WORKFLOW_WORKSPACE=raw, PSI_WORKFLOW_STATE_DIR=str(root/'state'))
            def call(action, params):
                result=subprocess.run([sys.executable,'-c',WORKER,action,json.dumps(params)],env=env,cwd=root,
                    capture_output=True,text=True,encoding='utf-8',timeout=40)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                return json.loads(result.stdout)
            waiting=call('run',{'flow_path':'flows/approval.workflow'})['$fusion_flow/control']
            self.assertEqual(waiting['status'],'waiting_for_human')
            answer={'run_id':waiting['run_id'],'request_id':waiting['request']['request_id'],'human_response_json':'"approve"'}
            self.assertEqual(call('resume',answer),{'decision':'approve'})
            self.assertEqual(call('resume',answer),{'decision':'approve'})

if __name__=='__main__': unittest.main()