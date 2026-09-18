import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import run_flow as runtime
from fusion_flow.agent_runtime import AgentReply
from fusion_flow.workflow_execution import ExecutionPlanError
from fusion_flow.workflow_runner import ProgramInvocation, execute_workflow


ROOT = Path(__file__).resolve().parents[1]


class P0SelfContainedRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_q07_nested_workflow_request_is_rejected_before_agent_call(self):
        class ShouldNotRun:
            def supports_agent_steps(self):
                return True

            async def run_agent(self, _invocation):
                raise AssertionError("nested launcher request must fail before model invocation")

        async def unused_registry(_session_id):
            raise AssertionError("nested launcher request must fail before tool lookup")

        adapter = runtime._AgentSessionAdapter(
            ai_socket=None,
            get_tool_registry=unused_registry,
            agent_runtime=ShouldNotRun(),
            run_id="q07",
        )
        context = SimpleNamespace(
            dispatch=SimpleNamespace(invocation_id="nested"),
            step_id="nested",
            agent_config=None,
            terminal=False,
            output_ids=("report",),
        )
        with self.assertRaisesRegex(ExecutionPlanError, "nested Workflow launcher"):
            await adapter.complete(
                "调用 run_flow 再启动一个子 workflow，并在子 workflow 中读取 README.md",
                context,
            )

    async def _run_program_script(self, source: str, *, terminal: bool, output_ids: tuple[str, ...]):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            script = root / "program.py"
            script.write_text(source, encoding="utf-8")
            invocation = ProgramInvocation(
                name="program",
                argv=(str(script),),
                stdin="{}\n",
                cwd=root,
                binding_name="terminal" if terminal else "program",
                dispatch=SimpleNamespace(iteration_index=None, loop_id=None, invocation_id="program"),
                output_ids=output_ids,
                terminal=terminal,
            )
            with patch.object(
                runtime,
                "_resolve_program_contract",
                AsyncMock(return_value=(root, root, script)),
            ):
                return await runtime._complete_program_step_hermes(invocation)

    async def test_q22_nonzero_program_stops_with_exit_code_and_stderr(self):
        source = (
            "import sys\n"
            "sys.stderr.write('EXACT_PROGRAM_FAILURE\\n')\n"
            "raise SystemExit(7)\n"
        )
        with self.assertRaisesRegex(RuntimeError, "nonzero_exit") as caught:
            await self._run_program_script(source, terminal=False, output_ids=())
        message = str(caught.exception)
        self.assertIn("EXACT_PROGRAM_FAILURE", message)
        self.assertIn('"exit_code": 7', message)

    async def test_q28_program_terminal_accepts_text_true_as_boolean(self):
        result = await self._run_program_script(
            "print('true')\n",
            terminal=True,
            output_ids=("done",),
        )
        self.assertEqual(result, {"done": True})
        self.assertIs(type(result["done"]), bool)

    async def test_q29_program_terminal_rejects_numeric_two(self):
        result = await self._run_program_script(
            "print('2')\n",
            terminal=True,
            output_ids=("done",),
        )
        diagnostic = result["done"]["$fusion_flow/program_error"]
        self.assertEqual(diagnostic["kind"], "invalid_output_contract")
        self.assertIn("true or false", diagnostic["message"])
        with self.assertRaisesRegex(ValueError, "strict JSON boolean"):
            runtime._validate_terminal_step_outputs(
                result,
                step_id="terminal",
                output_ids=("done",),
            )

    async def test_q21_two_independent_programs_dispatch_in_parallel(self):
        source = r"""
const compile_result: Artifact;
const help_result: Artifact;
const compile_step: Step;
const help_step: Step;
const compile_program: Program, Executor;
const help_program: Program, Executor;

workflow q21_parallel {
  input_workflow(q21_parallel) == [];
  produces(compile_step) == [compile_result];
  produces(help_step) == [help_result];
  output_workflow(q21_parallel) == [compile_result, help_result];

  step_executor(compile_step) == compile_program;
  program_path(compile_program) == "./compile.py";
  step_name(compile_step) == "Compile";
  step_instruction(compile_step) == "Run compile command exactly once.";

  step_executor(help_step) == help_program;
  program_path(help_program) == "./help.py";
  step_name(help_step) == "Help";
  step_instruction(help_step) == "Run help command exactly once.";
}
"""
        active = 0
        max_active = 0
        lock = asyncio.Lock()

        async def run_program(invocation):
            nonlocal active, max_active
            async with lock:
                active += 1
                max_active = max(max_active, active)
            await asyncio.sleep(0.05)
            async with lock:
                active -= 1
            return {invocation.output_ids[0]: invocation.binding_name}

        result = await execute_workflow(
            source,
            inputs={},
            run_program=run_program,
            work_dir=ROOT,
            supported_executor_kinds=("Program",),
        )

        self.assertEqual(max_active, 2)
        self.assertEqual(result["compile_result"], "compile_step")
        self.assertEqual(result["help_result"], "help_step")

    async def test_q27_never_converging_loop_stops_after_three_epochs(self):
        source = (ROOT / "examples" / "react_loop.workflow").read_text(encoding="utf-8")
        calls = {"reason": 0, "env_step": 0, "update": 0, "terminal": 0}

        async def complete(_prompt, context):
            calls[context.step_id] += 1
            if context.step_id == "reason":
                return {"thought": "t", "action": "a"}
            if context.step_id == "env_step":
                return {"observation": "o", "done": False}
            if context.step_id == "update":
                return {"prompt": f"epoch-{calls['update']}"}
            raise AssertionError(context.step_id)

        async def run_program(invocation):
            calls["terminal"] += 1
            return {"loop_done": False}

        with self.assertRaises(BaseExceptionGroup) as caught:
            await execute_workflow(
                source,
                inputs={"prompt": "seed"},
                complete=complete,
                run_program=run_program,
                work_dir=ROOT,
                supported_executor_kinds=("Agent", "Program"),
                max_loop_epochs=3,
            )

        pending = [caught.exception]
        messages = []
        while pending:
            error = pending.pop()
            messages.append(str(error))
            pending.extend(getattr(error, "exceptions", ()))
        self.assertTrue(
            any("max_loop_epochs=3" in message for message in messages),
            messages,
        )

        self.assertEqual(calls["reason"], 3)
        self.assertEqual(calls["env_step"], 3)
        self.assertEqual(calls["update"], 3)
        self.assertEqual(calls["terminal"], 3)


Q13_SOURCE = r"""
const layers: Artifact;
const focus: Artifact;
const review: Artifact;
const approval: Artifact;
const summary: Artifact;

const extract: Step;
const choose: Step;
const deepen: Step;
const approve: Step;
const summarize: Step;

const extractor: Program, Executor;
const chooser: Human, Executor;
const deepener: Agent, Executor;
const approver: Human, Executor;
const summarizer: Agent, Executor;

workflow q13 {
  input_workflow(q13) == [];

  produces(extract) == [layers];

  consumes(choose) == [layers];
  produces(choose) == [focus];

  consumes(deepen) == [layers, focus];
  produces(deepen) == [review];

  consumes(approve) == [review];
  produces(approve) == [approval];

  consumes(summarize) == [layers, review, approval];
  produces(summarize) == [summary];

  output_workflow(q13) == [summary];

  step_executor(extract) == extractor;
  program_path(extractor) == "./flows/q13/bin/extract.py";
  step_name(extract) == "Extract";
  step_instruction(extract) == "Extract four layers exactly once.";

  step_executor(choose) == chooser;
  step_name(choose) == "Choose";
  step_instruction(choose) == "FIRST_HUMAN: 优先评审哪一层？";

  step_executor(deepen) == deepener;
  step_name(deepen) == "Deepen";
  step_instruction(deepen) == "Deepen only the selected layer.";

  step_executor(approve) == approver;
  step_name(approve) == "Approve";
  step_instruction(approve) == "SECOND_HUMAN: 是否接受这份边界评审作为后续依据？";

  step_executor(summarize) == summarizer;
  step_name(summarize) == "Summarize";
  step_instruction(summarize) == "Produce final summary only after approval.";
}
"""

Q14_SOURCE = r"""
const human_text: Artifact;
const report: Artifact;
const ask: Step;
const analyze: Step;
const reviewer: Human, Executor;
const analyst: Agent, Executor;

workflow q14 {
  input_workflow(q14) == [];
  produces(ask) == [human_text];
  consumes(analyze) == [human_text];
  produces(analyze) == [report];
  output_workflow(q14) == [report];

  step_executor(ask) == reviewer;
  step_name(ask) == "Ask";
  step_instruction(ask) == "FREE_TEXT_HUMAN: 请给出一条你最在意的 ontology 校验边界，后续报告将逐字引用。";

  step_executor(analyze) == analyst;
  step_name(analyze) == "Analyze";
  step_instruction(analyze) == "Quote the Human text verbatim.";
}
"""

WORKER = r"""
import asyncio
import json
import sys
from fusion_flow.agent_runtime import AgentReply
from fusion_flow.host_adapter import set_agent_runtime_provider
from run_flow import run_flow, run_flow_resume

class FixedModel:
    def supports_agent_steps(self):
        return True

    async def run_agent(self, invocation):
        prompt = invocation.prompt
        if "Step: choose" in prompt:
            return AgentReply(text=json.dumps({
                "question": "优先评审哪一层？",
                "options": ["A shared", "B api", "C rawdata", "D onto"],
                "recommended": 3,
                "default": ""
            }, ensure_ascii=False))
        if "Step: approve" in prompt:
            return AgentReply(text=json.dumps({
                "question": "是否接受这份边界评审作为后续依据？",
                "options": ["接受", "退回补证据"],
                "recommended": 1,
                "default": None
            }, ensure_ascii=False))
        if "Step: ask" in prompt:
            return AgentReply(text=json.dumps({
                "question": "请给出一条你最在意的 ontology 校验边界，后续报告将逐字引用。",
                "options": [],
                "recommended": 0,
                "default": ""
            }, ensure_ascii=False))
        if "Step: deepen" in prompt:
            return AgentReply(text=json.dumps({"review": "rawdata-boundary-review"}, ensure_ascii=False))
        if "Step: summarize" in prompt:
            return AgentReply(text=json.dumps({"summary": "final-summary"}, ensure_ascii=False))
        if "Step: analyze" in prompt:
            marker = "缺失 evidence 引用时 strict 模式必须阻断。"
            if marker not in prompt:
                raise RuntimeError("Human free text was not preserved in Agent input")
            return AgentReply(text=json.dumps({"report": marker}, ensure_ascii=False))
        raise RuntimeError("unexpected prompt: " + prompt)

set_agent_runtime_provider(lambda: FixedModel())
fn = run_flow if sys.argv[1] == "run" else run_flow_resume
print(asyncio.run(fn(**json.loads(sys.argv[2]))))
"""


class P0HumanCheckpointRuntimeTests(unittest.TestCase):
    def _call(self, root: Path, action: str, params: dict):
        env = dict(
            os.environ,
            PYTHONPATH=str(ROOT / "src"),
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONUTF8="1",
            PYTHONIOENCODING="utf-8",
            PSI_WORKFLOW_HOST="hermes",
            HERMES_EXECUTABLE=sys.executable,
            PSI_WORKFLOW_WORKSPACE=str(root),
            PSI_WORKFLOW_STATE_DIR=str(root / "state"),
        )
        result = subprocess.run(
            [sys.executable, "-c", WORKER, action, json.dumps(params, ensure_ascii=False)],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_q13_two_human_resumes_do_not_rerun_program(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            flow_dir = root / "flows" / "q13"
            bin_dir = flow_dir / "bin"
            bin_dir.mkdir(parents=True)
            (flow_dir / "q13.workflow").write_text(Q13_SOURCE, encoding="utf-8")
            (bin_dir / "extract.py").write_text(
                "from pathlib import Path\n"
                "p=Path(__file__).with_name('count.txt')\n"
                "n=int(p.read_text() if p.exists() else '0')+1\n"
                "p.write_text(str(n))\n"
                "print('shared/api/rawdata/onto')\n",
                encoding="utf-8",
            )

            first = self._call(root, "run", {"flow_path": "flows/q13/q13.workflow"})["$fusion_flow/control"]
            self.assertEqual(first["status"], "waiting_for_human")
            self.assertEqual(first["request"]["question"], "优先评审哪一层？")
            self.assertEqual((bin_dir / "count.txt").read_text(), "1")

            second = self._call(
                root,
                "resume",
                {
                    "run_id": first["run_id"],
                    "request_id": first["request"]["request_id"],
                    "human_response_json": '"C rawdata"',
                },
            )["$fusion_flow/control"]
            self.assertEqual(second["status"], "waiting_for_human")
            self.assertNotEqual(first["request"]["request_id"], second["request"]["request_id"])
            self.assertEqual(second["request"]["question"], "是否接受这份边界评审作为后续依据？")
            self.assertEqual((bin_dir / "count.txt").read_text(), "1")

            final = self._call(
                root,
                "resume",
                {
                    "run_id": second["run_id"],
                    "request_id": second["request"]["request_id"],
                    "human_response_json": '"接受"',
                },
            )
            self.assertEqual(final, {"summary": "final-summary"})
            self.assertEqual((bin_dir / "count.txt").read_text(), "1")

    def test_q14_free_text_is_preserved_as_string(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            flow_dir = root / "flows" / "q14"
            flow_dir.mkdir(parents=True)
            (flow_dir / "q14.workflow").write_text(Q14_SOURCE, encoding="utf-8")

            waiting = self._call(root, "run", {"flow_path": "flows/q14/q14.workflow"})["$fusion_flow/control"]
            text = "缺失 evidence 引用时 strict 模式必须阻断。"
            final = self._call(
                root,
                "resume",
                {
                    "run_id": waiting["run_id"],
                    "request_id": waiting["request"]["request_id"],
                    "human_response_json": text,
                },
            )
            self.assertEqual(final, {"report": text})


if __name__ == "__main__":
    unittest.main()
