import ast
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import run_flow as runtime
from fusion_flow.agent_runtime import AgentReply
from fusion_flow.workflow_runner import ProgramInvocation


class _PreparingRuntime:
    def __init__(self, prepare):
        self.prepare = prepare
        self.prompts = []
        self.calls = 0

    def supports_agent_steps(self):
        return True

    async def run_agent(self, invocation):
        self.prompts.append(invocation.prompt)
        self.calls += 1
        self.prepare(invocation.workspace)
        action = (
            {"tool": "execute_program", "arguments": {"runtime": sys.executable}}
            if self.calls == 1
            else {"tool": "submit_program_result", "arguments": {}}
        )
        return AgentReply(text=json.dumps(action))


class _InvalidRuntime:
    def __init__(self):
        self.calls = 0

    def supports_agent_steps(self):
        return True

    async def run_agent(self, _invocation):
        self.calls += 1
        return AgentReply(text="not-json")


class _ProgramToolRuntime:
    def __init__(self):
        self.calls = 0
        self.prompts = []

    def supports_agent_steps(self):
        return True

    async def run_agent(self, invocation):
        self.calls += 1
        self.prompts.append(invocation.prompt)
        action = (
            {"tool": "execute_program", "arguments": {"runtime": sys.executable}}
            if self.calls == 1
            else {"tool": "submit_program_result", "arguments": {}}
        )
        return AgentReply(text=json.dumps(action))


class _SequenceProgramRuntime:
    def __init__(self, actions):
        self.actions = list(actions)
        self.prompts = []

    def supports_agent_steps(self):
        return True

    async def run_agent(self, invocation):
        self.prompts.append(invocation.prompt)
        return AgentReply(text=json.dumps(self.actions.pop(0)))


class ProgramDispatchTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).parents[1] / "src" / "run_flow.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_program_dispatch_has_no_direct_host_shortcuts(self):
        names = {
            node.name
            for node in self.tree.body
            if isinstance(node, ast.AsyncFunctionDef)
        }
        self.assertNotIn("_complete_program_step_openclaw", names)
        self.assertNotIn("_complete_program_step_hermes", names)
        self.assertNotIn("_complete_host_program_step", names)

        node = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_complete_program_step"
        )
        rendered = ast.unparse(node)
        self.assertIn("_run_host_program_tool_loop", rendered)
        self.assertIn("compile_program", rendered)
        self.assertIn("execute_program", rendered)
        self.assertIn("submit_program_result", rendered)
        self.assertNotIn("sys.executable", rendered)

    async def test_program_agent_can_prepare_dependency_before_execution(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            script = root / "program.py"
            script.write_text(
                "import prepared_dependency\nprint(prepared_dependency.VALUE)\n",
                encoding="utf-8",
            )

            def prepare(workspace):
                (workspace / "prepared_dependency.py").write_text(
                    'VALUE = "ready"\n',
                    encoding="utf-8",
                )

            host = _PreparingRuntime(prepare)
            invocation = ProgramInvocation(
                name="program",
                argv=(str(script),),
                stdin="{}\n",
                cwd=root,
                binding_name="program",
                dispatch=SimpleNamespace(
                    iteration_index=None,
                    loop_id=None,
                    invocation_id="program",
                    resource_lease=SimpleNamespace(grants=()),
                ),
                output_ids=("result",),
            )
            with patch.object(
                runtime,
                "_resolve_program_contract",
                AsyncMock(return_value=(root, root, script)),
            ):
                result = await runtime._complete_program_step(
                    invocation,
                    ai_socket="",
                    tool_registry=SimpleNamespace(),
                    agent_runtime=host,
                )

        self.assertEqual(result, {"result": f"ready{os.linesep}"})
        self.assertEqual(len(host.prompts), 2)
        contract_prompt = host.prompts[0]
        contract = json.loads(contract_prompt.split("Program contract:\n", 1)[1])
        self.assertEqual(contract["script_path"], str(script))
        self.assertIn("strict JSON tool calls", contract_prompt)

    async def test_invalid_program_agent_response_never_falls_back_to_direct_execution(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            marker = root / "executed.txt"
            script = root / "program.py"
            script.write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n"
                "print('unexpected')\n",
                encoding="utf-8",
            )
            invocation = ProgramInvocation(
                name="program",
                argv=(str(script),),
                stdin="{}\n",
                cwd=root,
                binding_name="program",
                dispatch=SimpleNamespace(
                    iteration_index=None,
                    loop_id=None,
                    invocation_id="program",
                    resource_lease=SimpleNamespace(grants=()),
                ),
                output_ids=("result",),
            )
            host = _InvalidRuntime()
            with patch.object(
                runtime,
                "_resolve_program_contract",
                AsyncMock(return_value=(root, root, script)),
            ):
                result = await runtime._complete_program_step(
                    invocation,
                    ai_socket="",
                    tool_registry=SimpleNamespace(),
                    agent_runtime=host,
                )

        self.assertFalse(marker.exists())
        self.assertEqual(host.calls, runtime._STEP_MAX_TURNS)
        diagnostic = result["result"]["$fusion_flow/program_error"]
        self.assertEqual(diagnostic["phase"], "agent")
        self.assertEqual(diagnostic["kind"], "invalid_tool_call")

    async def test_host_program_agent_compiles_and_executes_registered_artifact(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source.txt"
            compiler = root / "compiler.py"
            artifact = root / "compiled.py"
            source.write_text("source", encoding="utf-8")
            compiler.write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "Path(sys.argv[2]).write_text(\"print('compiled tool path')\\n\", encoding=\"utf-8\")\n",
                encoding="utf-8",
            )
            invocation = ProgramInvocation(
                name="program",
                argv=(str(source),),
                stdin="{}\n",
                cwd=root,
                binding_name="program",
                dispatch=SimpleNamespace(
                    iteration_index=None,
                    loop_id=None,
                    invocation_id="program",
                    resource_lease=SimpleNamespace(grants=()),
                ),
                output_ids=("result",),
            )
            host = _SequenceProgramRuntime(
                [
                    {
                        "tool": "compile_program",
                        "arguments": {
                            "compile_argv": [sys.executable, str(compiler), str(source), str(artifact)],
                            "execute_argv": [sys.executable, str(artifact)],
                            "artifact_paths": [str(artifact)],
                        },
                    },
                    {
                        "tool": "execute_program",
                        "arguments": {"compiled_launch_argv": [sys.executable, str(artifact)]},
                    },
                    {"tool": "submit_program_result", "arguments": {}},
                ]
            )
            with patch.object(
                runtime,
                "_resolve_program_contract",
                AsyncMock(return_value=(root, root, source)),
            ):
                result = await runtime._complete_program_step(
                    invocation,
                    ai_socket="",
                    tool_registry=SimpleNamespace(),
                    agent_runtime=host,
                )

        self.assertEqual(result, {"result": f"compiled tool path{os.linesep}"})
        self.assertEqual(len(host.prompts), 3)
        self.assertIn("registered", host.prompts[1])

    async def test_host_program_agent_uses_structured_execution_tools(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            script = root / "program.py"
            script.write_text("print('tool path')\n", encoding="utf-8")
            invocation = ProgramInvocation(
                name="program",
                argv=(str(script),),
                stdin="{}\n",
                cwd=root,
                binding_name="program",
                dispatch=SimpleNamespace(
                    iteration_index=None,
                    loop_id=None,
                    invocation_id="program",
                    resource_lease=SimpleNamespace(grants=()),
                ),
                output_ids=("result",),
            )
            host = _ProgramToolRuntime()
            with patch.object(
                runtime,
                "_resolve_program_contract",
                AsyncMock(return_value=(root, root, script)),
            ):
                result = await runtime._complete_program_step(
                    invocation,
                    ai_socket="",
                    tool_registry=SimpleNamespace(),
                    agent_runtime=host,
                )

        self.assertEqual(result, {"result": f"tool path{os.linesep}"})
        self.assertEqual(host.calls, 2)
        self.assertIn("compile_program", host.prompts[0])
        self.assertIn("execute_program", host.prompts[0])
        self.assertIn("submit_program_result", host.prompts[0])


if __name__ == "__main__":
    unittest.main()
