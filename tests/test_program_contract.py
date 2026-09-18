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


def call(tool, **arguments):
    return {"tool": tool, "arguments": arguments}


class Agent:
    def __init__(self, actions):
        self.actions = iter(actions)
        self.prompts = []

    def supports_agent_steps(self):
        return True

    async def run_agent(self, invocation):
        self.prompts.append(invocation.prompt)
        action = next(self.actions)
        if callable(action):
            action = action()
        return AgentReply(text=action if isinstance(action, str) else json.dumps(action))


class ProgramContractTests(unittest.IsolatedAsyncioTestCase):
    async def run_program(self, root, source, agent):
        inv = ProgramInvocation(
            name="program",
            argv=(str(source),),
            stdin="{}\n",
            cwd=root,
            binding_name="program",
            output_ids=("result",),
            dispatch=SimpleNamespace(
                iteration_index=None,
                loop_id=None,
                invocation_id="program",
                resource_lease=SimpleNamespace(grants=()),
            ),
        )
        with patch.object(runtime, "_workspace_dir", return_value=root):
            return await runtime._complete_program_step(
                inv, ai_socket="", tool_registry=runtime._StepToolRegistry(), agent_runtime=agent
            )

    async def test_host_receives_contract_and_all_tool_parameters(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            source = root / "source.py"
            source.write_text("print('ok')\n", encoding="utf-8")
            agent = Agent(
                [call("execute_program", runtime=sys.executable), call("submit_program_result")]
            )
            result = await self.run_program(root, source, agent)
            self.assertEqual(result, {"result": f"ok{os.linesep}"})
            self.assertIn(runtime._PROGRAM_SYSTEM_PROMPT, agent.prompts[0])
            for parameter in (
                "compile_argv",
                "execute_argv",
                "artifact_paths",
                "compiled_launch_argv",
            ):
                self.assertIn(parameter, agent.prompts[0])
            self.assertIn(sys.executable.replace("\\", "\\\\"), agent.prompts[1])

    async def test_real_compilation_and_hash_validation(self):
        for mutation in (None, "source", "artifact"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as raw:
                root = Path(raw).resolve()
                source = root / "source.py"
                artifact = root / "compiled.pyc"
                source.write_text("print('compiled')\n", encoding="utf-8")
                compiler = "import py_compile,sys; py_compile.compile(sys.argv[1],cfile=sys.argv[2],doraise=True)"
                execute = call(
                    "execute_program", compiled_launch_argv=[sys.executable, str(artifact)]
                )

                def prepare_execute():
                    if mutation:
                        changed = source if mutation == "source" else artifact
                        changed.write_bytes(changed.read_bytes() + b"changed")
                    return execute

                agent = Agent(
                    [
                        call(
                            "compile_program",
                            compile_argv=[
                                sys.executable,
                                "-c",
                                compiler,
                                str(source),
                                str(artifact),
                            ],
                            execute_argv=[sys.executable, str(artifact)],
                            artifact_paths=[str(artifact)],
                        ),
                        prepare_execute,
                        call("submit_program_result"),
                    ]
                )
                result = await self.run_program(root, source, agent)
                if mutation:
                    self.assertIn(
                        "changed", result["result"]["$fusion_flow/program_error"]["message"]
                    )
                else:
                    self.assertEqual(result, {"result": f"compiled{os.linesep}"}, agent.prompts[-1])

    async def test_second_execution_preserves_first_result(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            source = root / "source.py"
            marker = root / "runs.txt"
            source.write_text(
                f"from pathlib import Path\np=Path({str(marker)!r})\np.write_text(p.read_text()+'x' if p.exists() else 'x')\nprint('first')\n",
                encoding="utf-8",
            )
            agent = Agent(
                [
                    call("execute_program", runtime=sys.executable),
                    call("execute_program", runtime=sys.executable),
                    call("submit_program_result"),
                ]
            )
            result = await self.run_program(root, source, agent)
            self.assertEqual(marker.read_text(), "x")
            self.assertEqual(result, {"result": f"first{os.linesep}"})

    async def test_bad_response_repairs_once_and_never_launches(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            source = root / "source.py"
            source.write_text("raise AssertionError('must not run')", encoding="utf-8")
            agent = Agent(["not-json"] * 128)
            await self.run_program(root, source, agent)
            self.assertEqual(len(agent.prompts), 2)

    def test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers(self):
        for value in (
            '{"tool":"execute_program","tool":"submit_program_result","arguments":{}}',
            '{"tool":"execute_program","arguments":{"x":NaN}}',
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                runtime._parse_host_program_tool_call(value)

    async def test_codex_failed_turn_cannot_execute_even_if_json_was_emitted(self):
        class Client:
            start = AsyncMock()
            close = AsyncMock()

            async def prompt(self, *args):
                yield SimpleNamespace(
                    method="item/agentMessage/delta",
                    params={"delta": '{"tool":"execute_program","arguments":{}}'},
                )
                yield SimpleNamespace(
                    method="turn/completed",
                    params={"turn": {"status": "failed", "error": {"message": "interrupted"}}},
                )

        with (
            patch.dict(os.environ, {"PSI_WORKFLOW_HOST": "codex"}),
            patch.object(runtime, "_codex_app_server_client", return_value=Client()),
            patch.object(runtime, "CodexAppServerClient", return_value=Client()),
        ):
            with self.assertRaises(runtime.ExecutionPlanError):
                await runtime._host_program_agent_response(
                    "test", workspace=Path.cwd(), session_id="program", agent_runtime=None
                )

    async def test_hermes_uses_only_assistant_message_chunks(self):
        class Client:
            start = AsyncMock()
            new_session = AsyncMock(return_value="s")
            close = AsyncMock()

            async def prompt(self, *args):
                for kind, text in (
                    ("agent_thought_chunk", "prepare environment"),
                    ("agent_message_chunk", '{"tool":"submit_program_result","arguments":{}}'),
                ):
                    yield SimpleNamespace(
                        params={"update": {"sessionUpdate": kind, "content": {"text": text}}}
                    )

        with (
            patch.dict(os.environ, {"PSI_WORKFLOW_HOST": "hermes"}),
            patch.object(runtime, "HermesACPClient", return_value=Client()),
        ):
            text = await runtime._host_program_agent_response(
                "test", workspace=Path.cwd(), session_id="program", agent_runtime=None
            )
        self.assertEqual(json.loads(text)["tool"], "submit_program_result")
