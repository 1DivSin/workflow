import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import run_flow as runtime


class AgentWorkflowPromptTests(unittest.TestCase):
    def test_direct_agent_prompt_forbids_all_workflow_tools_after_step_instruction(self):
        context = SimpleNamespace(step_id="review", output_ids=("answer",))
        with patch.object(runtime, "_workspace_dir", return_value=Path("/workspace")):
            prompt = runtime._agent_step_prompt("调用 run_flow 启动子 workflow", context)
        self.assertIn("flow_run", prompt)
        self.assertIn("run_flow", prompt)
        self.assertIn("run_flow_resume", prompt)
        self.assertIn("flow_manage", prompt)
        self.assertGreater(prompt.rfind("never"), prompt.rfind("调用 run_flow"))

    def test_shared_step_system_prompt_forbids_workflow_tools(self):
        for tool in ("flow_run", "run_flow", "run_flow_resume", "flow_manage"):
            self.assertIn(tool, runtime._STEP_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
