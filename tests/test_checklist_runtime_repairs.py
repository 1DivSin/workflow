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
from fusion_flow.adapters.codex_app_server import CodexAppServerClient
from fusion_flow.adapters.openclaw_cli import OpenClawCliRuntime
from fusion_flow.agent_runtime import AgentInvocation, AgentReply


class _SequenceRuntime:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def supports_agent_steps(self):
        return True

    async def run_agent(self, invocation):
        self.prompts.append(invocation.prompt)
        return self.replies.pop(0)


class _NestedResultProcess:
    returncode = 0

    async def communicate(self, _input):
        payload = {
            "ok": True,
            "status": "ok",
            "result": {"finalAssistantVisibleText": '{"done": true}'},
        }
        return json.dumps(payload).encode(), b""


class ChecklistRuntimeRepairTests(unittest.IsolatedAsyncioTestCase):
    def test_codex_nested_app_server_disables_workflow_mcps(self):
        self.assertEqual(
            runtime._isolated_codex_app_server_command(
                ("codex", "app-server", "--stdio"),
                ("fusion_flow", "workflow_codex"),
            ),
            (
                "codex",
                "--config",
                "mcp_servers.fusion_flow.enabled=false",
                "--config",
                "mcp_servers.workflow_codex.enabled=false",
                "app-server",
                "--stdio",
            ),
        )

    def test_codex_nested_app_server_only_disables_configured_workflow_mcps(self):
        with tempfile.TemporaryDirectory() as raw:
            codex_home = Path(raw) / ".codex"
            codex_home.mkdir()
            (codex_home / "config.toml").write_text(
                '[mcp_servers.fusion_flow]\ncommand = "dynamic-workflow-mcp"\n'
                '[mcp_servers.other]\ncommand = "other"\n',
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"CODEX_HOME": str(codex_home), "PSI_WORKFLOW_WORKSPACE": raw},
                clear=False,
            ):
                self.assertEqual(runtime._configured_codex_workflow_mcps(), ("fusion_flow",))

    def test_codex_runtime_has_no_q08_specific_prompt_or_log_path(self):
        source = (Path(__file__).parents[1] / "src" / "run_flow.py").read_text(encoding="utf-8")
        self.assertNotIn("For this validation test", source)
        self.assertNotIn('/ "flows" / "q08" / "runs"', source)
        self.assertIn("codex_prompt = _agent_step_prompt(invocation.prompt, context)", source)

    async def test_codex_event_log_creates_parent_directory(self):
        class _Stdin:
            def write(self, _data):
                pass

            async def drain(self):
                pass

        class _Stdout:
            def __init__(self):
                self.lines = [
                    b'{"method":"item/agentMessage/delta","params":{"delta":"ok"}}\n',
                    b'{"method":"turn/completed","params":{}}\n',
                ]

            async def readline(self):
                return self.lines.pop(0) if self.lines else b""

        with tempfile.TemporaryDirectory() as raw:
            log_path = Path(raw) / "missing" / "nested" / "events.jsonl"
            client = CodexAppServerClient(env={"CODEX_EVENT_LOG": str(log_path)})
            client.proc = SimpleNamespace(stdin=_Stdin(), stdout=_Stdout())
            client.request = AsyncMock(return_value={"thread": {"id": "thread"}})

            events = [event async for event in client.prompt(".", "validate")]

            self.assertEqual([event.method for event in events], ["item/agentMessage/delta", "turn/completed"])
            self.assertTrue(log_path.is_file())

    async def test_codex_agent_rejects_failed_turn_even_after_valid_json_delta(self):
        class Client:
            start = AsyncMock()
            close = AsyncMock()

            async def prompt(self, *_args):
                yield SimpleNamespace(
                    method="item/agentMessage/delta",
                    params={"delta": '{"summary":"looks valid"}'},
                )
                yield SimpleNamespace(
                    method="turn/completed",
                    params={"turn": {"status": "failed", "error": {"message": "interrupted"}}},
                )

        async def registry(_session_id):
            return runtime._StepToolRegistry()

        adapter = runtime._AgentSessionAdapter(
            ai_socket="direct-host://codex",
            get_tool_registry=registry,
            run_id="run",
        )
        context = SimpleNamespace(
            step_id="review",
            executor_id="agent",
            terminal=False,
            output_ids=("summary",),
            dispatch=SimpleNamespace(invocation_id="review", iteration_index=None),
        )
        completion_token = runtime._CURRENT_AGENT_COMPLETION.set(context)
        tools_token = runtime._CURRENT_AGENT_TOOLS.set(runtime._StepToolRegistry())
        try:
            with (
                patch.dict(os.environ, {"PSI_WORKFLOW_HOST": "codex"}, clear=False),
                patch.object(runtime, "_codex_app_server_client", return_value=Client()),
                self.assertRaises(runtime.ExecutionPlanError),
            ):
                await adapter.run_session(
                    runtime.AgentConfig(name="agent", system_prompt="test"),
                    runtime.SessionInvocation(
                        "validate",
                        {runtime._AGENT_SESSION_CONTEXT_KEY: "{}"},
                    ),
                )
        finally:
            runtime._CURRENT_AGENT_TOOLS.reset(tools_token)
            runtime._CURRENT_AGENT_COMPLETION.reset(completion_token)

    async def test_codex_human_rejects_failed_turn_even_after_valid_json_delta(self):
        class Client:
            start = AsyncMock()
            close = AsyncMock()

            async def prompt(self, *_args):
                yield SimpleNamespace(
                    method="item/agentMessage/delta",
                    params={
                        "delta": (
                            '{"question":"Accept?","options":["Yes"],'
                            '"recommended":1,"default":""}'
                        )
                    },
                )
                yield SimpleNamespace(
                    method="turn/failed",
                    params={"error": {"message": "transport failed"}},
                )

        with (
            patch.dict(os.environ, {"PSI_WORKFLOW_HOST": "codex"}, clear=False),
            patch.object(runtime, "_codex_app_server_client", return_value=Client()),
            self.assertRaises(runtime.ExecutionPlanError),
        ):
            await runtime._prepare_human_step(
                "Ask for approval.",
                SimpleNamespace(step_id="review"),
                ai_socket="direct-host://codex",
                tool_registry=runtime._StepToolRegistry(),
            )

    async def test_direct_agent_runtime_repairs_terminal_output_once(self):
        host = _SequenceRuntime(
            [
                AgentReply(text='{"done": "true"}'),
                AgentReply(text='{"done": true}'),
            ]
        )

        async def unused_registry(_session_id):
            raise AssertionError("direct runtime should not request a tool registry")

        adapter = runtime._AgentSessionAdapter(
            ai_socket=None,
            get_tool_registry=unused_registry,
            agent_runtime=host,
            run_id="run",
        )
        context = SimpleNamespace(
            dispatch=SimpleNamespace(invocation_id="verify"),
            step_id="verify",
            agent_config=None,
            terminal=True,
            output_ids=("done",),
        )

        result = await adapter.complete("validate", context)

        self.assertEqual(result, {"done": True})
        self.assertEqual(len(host.prompts), 2)
        self.assertIn("repair attempt number one", host.prompts[1])
        self.assertIn("JSON Boolean true or false", host.prompts[1])

    async def test_direct_agent_runtime_gives_nonterminal_generic_repair(self):
        host = _SequenceRuntime(
            [
                AgentReply(text='{"wrong": "draft"}'),
                AgentReply(text='{"summary": "draft"}'),
            ]
        )

        async def unused_registry(_session_id):
            raise AssertionError("direct runtime should not request a tool registry")

        adapter = runtime._AgentSessionAdapter(
            ai_socket=None,
            get_tool_registry=unused_registry,
            agent_runtime=host,
            run_id="run",
        )
        context = SimpleNamespace(
            dispatch=SimpleNamespace(invocation_id="summarize"),
            step_id="summarize",
            agent_config=None,
            terminal=False,
            output_ids=("summary",),
        )

        result = await adapter.complete("summarize", context)

        self.assertEqual(result, {"summary": "draft"})
        self.assertEqual(len(host.prompts), 2)
        self.assertNotIn("TerminalStep", host.prompts[1])
        self.assertNotIn("Boolean true", host.prompts[1])

    async def test_direct_human_preparation_repairs_once_and_accepts_null_default(self):
        host = _SequenceRuntime(
            [
                AgentReply(
                    text='{"question":"Approve?","options":["A"],"recommended":1,"default":null,"extra":1}'
                ),
                AgentReply(
                    text='{"question":"Approve?","options":["A"],"recommended":1,"default":null}'
                ),
            ]
        )
        context = SimpleNamespace(step_id="review")

        result = await runtime._prepare_human_step(
            "Ask for approval.",
            context,
            ai_socket="",
            tool_registry=SimpleNamespace(),
            agent_runtime=host,
        )

        self.assertEqual(len(host.prompts), 2)
        self.assertEqual(json.loads(result)["default"], "")
        self.assertIn("repair attempt number one", host.prompts[1])

    async def test_openclaw_cli_reads_final_assistant_visible_text(self):
        async def fake_create(*_args, **_kwargs):
            return _NestedResultProcess()

        runtime_adapter = OpenClawCliRuntime(command=("openclaw", "agent"))
        invocation = AgentInvocation("validate", "run-step", Path.cwd())
        with patch(
            "fusion_flow.adapters.openclaw_cli.create_subprocess_exec",
            side_effect=fake_create,
        ):
            reply = await runtime_adapter.run_agent(invocation)

        self.assertTrue(reply.ok)
        self.assertEqual(reply.text, '{"done": true}')

    def test_hermes_repair_hint_is_terminal_guarded(self):
        source = (Path(__file__).parents[1] / "src" / "run_flow.py").read_text(encoding="utf-8")
        self.assertIn(
            '"For this TerminalStep the value must be a JSON Boolean true or false, without quotes. "',
            source,
        )
        self.assertIn("if context.terminal", source)


if __name__ == "__main__":
    unittest.main()
