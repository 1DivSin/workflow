import importlib.util
import sys
import unittest
from pathlib import Path


class AgentBoundaryTests(unittest.TestCase):
    def test_invocation_rejects_empty_prompt(self):
        path = Path(__file__).parents[1] / "src" / "fusion_flow" / "agent_runtime.py"
        spec = importlib.util.spec_from_file_location("clean_agent_runtime", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        with self.assertRaises(ValueError):
            module.AgentInvocation("", "step-1", Path("."))


if __name__ == "__main__":
    unittest.main()
