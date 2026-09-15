import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_flow
from fusion_flow.workflow_runner import ProgramInvocation
from fusion_flow.workflow_execution import DispatchContext


class HostProgramTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_host_captures_real_exit7_and_executes_once(self):
        for host in ('codex', 'hermes', 'openclaw'):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                script = root / 'fail.py'
                script.write_text("from pathlib import Path\nimport sys\np=Path('count')\np.write_text(p.read_text()+'x' if p.exists() else 'x')\nsys.stderr.write('EXACT_PROGRAM_FAILURE\\n')\nsys.exit(7)\n")
                invocation = ProgramInvocation('worker', ('fail.py',), '{}\n', root, 'fail_step', DispatchContext())
                with patch.dict(os.environ, {'PSI_WORKFLOW_HOST': host}), patch.object(run_flow, '_workspace_dir', return_value=root):
                    with self.assertRaises(RuntimeError) as err:
                        await run_flow._complete_program_step(invocation, ai_socket=None, tool_registry=None)
                self.assertIn('"exit_code": 7', str(err.exception))
                self.assertIn('EXACT_PROGRAM_FAILURE', str(err.exception))
                self.assertIn('nonzero_exit', str(err.exception))
                self.assertIn('fail_step', str(err.exception))
                self.assertIn(str(script), str(err.exception))
                self.assertEqual((root / 'count').read_text(), 'x')

    async def test_script_path_is_resolved_against_cwd_and_arguments_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            nested = root / 'nested'
            nested.mkdir()
            (nested / 'args.py').write_text('import sys, os\nprint(os.getcwd()+"|"+sys.argv[1]+"|"+sys.stdin.read(), end="")\n')
            invocation = ProgramInvocation('worker', ('args.py', 'one two'), 'stdin', nested, 'step', DispatchContext(), output_ids=('out',))
            with patch.object(run_flow, '_workspace_dir', return_value=root):
                result = await run_flow._complete_program_step_host(invocation)
            self.assertEqual(result, {'out': str(nested)+'|one two|stdin'})

    async def test_terminal_invalid_bool_is_not_coerced_to_success(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'invalid.py').write_text('print(2)\n')
            invocation = ProgramInvocation('worker', ('invalid.py',), '', root, 'validate', DispatchContext(loop_id='loop', epoch=0), output_ids=('done',), terminal=True)
            with patch.object(run_flow, '_workspace_dir', return_value=root), self.assertRaisesRegex(RuntimeError, 'invalid_output_contract'):
                await run_flow._complete_program_step_host(invocation)

    async def test_unknown_language_fails_before_execution(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'code.unknown').write_text("raise AssertionError('must not execute as Python')")
            invocation = ProgramInvocation('worker', ('code.unknown',), '', root, 'step', DispatchContext())
            with patch.object(run_flow, '_workspace_dir', return_value=root), self.assertRaisesRegex(RuntimeError, 'unsupported_program_runtime'):
                await run_flow._complete_program_step_host(invocation)


class ProgramEntrypointTests(unittest.TestCase):
    def test_real_run_flow_stops_with_persisted_failure_on_each_host(self):
        source = '''const fail_step: Step;
const fail_program: Program, Executor;
workflow failure {
 input_workflow(failure) == [];
 produces(fail_step) == [];
 output_workflow(failure) == [];
 step_executor(fail_step) == fail_program;
 step_name(fail_step) == "Exact Program Failure";
 step_instruction(fail_step) == "Execute once and preserve the failure.";
 max_attempts(fail_step) == 1;
 program_path(fail_program) == "./flows/failure/fail.py";
}
'''
        for host in ('codex', 'hermes', 'openclaw'):
            with self.subTest(host=host), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                bundle = root / 'flows/failure'
                bundle.mkdir(parents=True)
                (bundle / 'failure.workflow').write_text(source)
                (bundle / 'fail.py').write_text("from pathlib import Path\nimport sys\np=Path('flows/failure/count')\np.write_text(p.read_text()+'x' if p.exists() else 'x')\nsys.stderr.write('EXACT_PROGRAM_FAILURE\\n')\nsys.exit(7)\n")
                env = dict(os.environ, PSI_WORKFLOW_HOST=host, PSI_WORKFLOW_WORKSPACE=d,
                           PSI_WORKFLOW_STATE_DIR=str(root / '.workflow-state'))
                result = subprocess.run([sys.executable, '-c',
                    "import anyio, run_flow; print(anyio.run(run_flow.run_flow, 'flows/failure/failure.workflow'))"],
                    cwd=root, env=env, text=True, capture_output=True, timeout=30)
                diagnostics = result.stdout + result.stderr
                self.assertIn('EXACT_PROGRAM_FAILURE', diagnostics)
                self.assertIn('nonzero_exit', diagnostics)
                self.assertEqual((bundle / 'count').read_text(), 'x')
                reports = list(bundle.glob('runs/*/step-timings.json'))
                self.assertEqual(len(reports), 1)
                report = json.loads(reports[0].read_text())
                self.assertEqual(report['status'], 'failed')
                self.assertEqual(len(report['steps']), 1)
                self.assertEqual(len(report['steps'][0]['attempts']), 1)


if __name__ == '__main__':
    unittest.main()
