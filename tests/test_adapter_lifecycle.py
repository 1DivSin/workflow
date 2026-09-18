import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import anyio

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from fusion_flow.adapters.codex_app_server import CodexAppServerClient
from fusion_flow.adapters.hermes_acp import HermesACPClient
from fusion_flow.adapters.openclaw_cli import OpenClawCliRuntime
from fusion_flow.agent_runtime import AgentInvocation
import fusion_flow.adapters.openclaw_cli as openclaw


class AdapterLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_drains_stderr_and_failed_start_reaps_process(self):
        for cls in (CodexAppServerClient, HermesACPClient):
            with self.subTest(adapter=cls.__name__), tempfile.TemporaryDirectory() as raw:
                # A diagnostic flood must not block the initialize response.
                script = Path(raw) / "agent.py"
                script.write_text(
                    "import sys,json,time\nsys.stderr.write('x'*262144);sys.stderr.flush()\nr=json.loads(sys.stdin.readline())\nprint(json.dumps({'id':r['id'],'result':{}}),flush=True)\ntime.sleep(60)\n",
                    encoding="utf-8",
                )
                client = cls(command=(sys.executable, str(script)), env={**os.environ, "HOME": raw})
                try:
                    with anyio.fail_after(3):
                        await client.start()
                    process = client.proc
                    with anyio.fail_after(8):
                        await client.close()
                    self.assertIsNotNone(process.returncode)
                finally:
                    if client.proc is not None:
                        # Test-owned cleanup even if the implementation fails.
                        client.proc.kill()
                        await client.proc.communicate()

    async def test_initialize_error_cleans_up_without_caller_close(self):
        for cls in (CodexAppServerClient, HermesACPClient):
            with self.subTest(adapter=cls.__name__), tempfile.TemporaryDirectory() as raw:
                script = Path(raw) / "agent.py"
                script.write_text(
                    "import sys,json,time\nr=json.loads(sys.stdin.readline())\nprint(json.dumps({'id':r['id'],'error':{'message':'failed'}}),flush=True)\ntime.sleep(60)\n",
                    encoding="utf-8",
                )
                client = cls(command=(sys.executable, str(script)), env={**os.environ, "HOME": raw})
                try:
                    with self.assertRaises(RuntimeError):
                        await client.start()
                    self.assertIsNone(client.proc)
                finally:
                    if client.proc is not None:
                        client.proc.kill()
                        await client.proc.communicate()

    async def test_openclaw_cancel_reaps_child(self):
        with tempfile.TemporaryDirectory() as raw:
            script = Path(raw) / "agent.py"
            script.write_text(
                "import sys,time\nsys.stdin.read()\ntime.sleep(60)\n", encoding="utf-8"
            )
            adapter = OpenClawCliRuntime(command=(sys.executable, str(script)))
            original = openclaw.create_subprocess_exec
            processes = []

            async def spawn(*args, **kwargs):
                proc = await original(*args, **kwargs)
                processes.append(proc)
                return proc

            try:
                with patch.object(openclaw, "create_subprocess_exec", side_effect=spawn):
                    with self.assertRaises(TimeoutError), anyio.fail_after(0.5):
                        await adapter.run_agent(AgentInvocation("test", "program-test", Path(raw)))
                self.assertIsNotNone(processes[0].returncode)
            finally:
                for proc in processes:
                    if proc.returncode is None:
                        proc.kill()
                        await proc.communicate()
