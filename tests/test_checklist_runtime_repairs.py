import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import run_flow as runtime
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
